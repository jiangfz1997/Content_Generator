import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict, Any

import yaml
from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import load_prompt
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.state import GlobalState
from app.services.llm_service import llm_service
from app.services.primitive_registry import primitive_registry
from app.utils.callbacks import make_callbacks


@lru_cache(maxsize=1)
def _load_animation_presets() -> Dict[str, Dict]:
    """Load animation_presets.yaml once and cache it."""
    path = settings.PROJECTILE_ANIM_PRESETS_PATH
    if not path.exists():
        print(f"[ProjectileFactory] ⚠️  animation_presets.yaml not found at {path}, using empty presets")
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("presets", {})


def _animation_preset_catalog() -> str:
    """Format the preset table as a short string for injection into the LLM prompt."""
    presets = _load_animation_presets()
    if not presets:
        return "  (no presets configured)"
    lines = []
    for name, meta in presets.items():
        lines.append(f"  - \"{name}\": {meta.get('description', '')}")
    return "\n".join(lines)


class GeneratedProjectileStats(BaseModel):
    speed: float = Field(description="Travel speed in units/sec. Typical: 8.0 (slow), 14.0 (normal), 20.0 (fast)")
    lifetime: float = Field(description="Seconds before despawn. Typical: 1.5–4.0")
    penetration: int = Field(description="0 = stops on first hit, 99 = infinite penetration")
    collider_radius: Optional[float] = Field(
        default=None,
        description=(
            "Explosion detection radius in world units. "
            "Set ONLY for explosive/AoE projectiles: 1.5–3.0. "
            "Leave null for all normal projectiles (bullet, arrow, bolt, orb) — they use the engine default 0.1."
        ),
    )

    @model_validator(mode="after")
    def clamp_values(self):
        self.speed = max(1.0, self.speed)
        self.lifetime = max(0.5, min(10.0, self.lifetime))
        self.penetration = max(0, self.penetration)
        return self


class GeneratedProjectile(BaseModel):
    reasoning: str = Field(description="Brief reasoning for the stat choices and on_hit payload selection. MAX 20 words.")
    id: str = Field(description="Projectile ID in snake_case with 'projectile_' prefix, e.g. 'projectile_dark_bolt'")
    name: str = Field(description="Short display name, e.g. 'Dark Bolt'")
    stats: GeneratedProjectileStats
    animation_preset: str = Field(
        description=(
            "Animation preset name. Must be one of the available presets listed in the prompt. "
            "Choose based on the projectile's shape and elemental theme."
        )
    )
    on_hit_payloads: List[str] = Field(
        description=(
            "List of existing payload IDs that trigger when this projectile hits something. "
            "Copy IDs CHARACTER-FOR-CHARACTER from the Payload Catalog. "
            "Example: ['payload_dot_poison', 'payload_knockback']. "
            "NEVER invent payload IDs."
        )
    )

    @model_validator(mode="after")
    def validate_fields(self):
        # Clamp animation_preset to known values; fall back to first available
        known_presets = list(_load_animation_presets().keys())
        if known_presets and self.animation_preset not in known_presets:
            print(f"[ProjectileFactory] Unknown animation_preset '{self.animation_preset}', "
                  f"falling back to '{known_presets[0]}'")
            self.animation_preset = known_presets[0]

        # Remove any on_hit payload IDs that don't exist in the library
        known_payloads = set(primitive_registry.get_all_payloads().keys())
        valid, invalid = [], []
        for pid in self.on_hit_payloads:
            (valid if pid in known_payloads else invalid).append(pid)
        if invalid:
            print(f"[ProjectileFactory] Removed invalid on_hit payload IDs: {invalid}")
        self.on_hit_payloads = valid
        return self


class ProjectileFactoryAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "projectile_factory.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)
        self.chain = (
            self.prompt
            | llm_service.get_structured_model("projectile_factory", GeneratedProjectile)
        )

    async def generate_node(self, state: GlobalState, config: RunnableConfig | None = None) -> dict:
        concept = state.get("design_concept", {})
        if not isinstance(concept, dict):
            print("[ProjectileFactory] design_concept is not a dict, skipping.")
            return {}

        spec = concept.get("new_projectile_spec")
        if not spec:
            print("[ProjectileFactory] No new_projectile_spec found, skipping.")
            return {}

        proj_id      = spec.get("id", "projectile_unknown")
        description  = spec.get("description", "")
        speed_hint   = spec.get("speed_hint", 14.0)
        lifetime_hint = spec.get("lifetime_hint", 3.0)
        on_hit_hint  = spec.get("on_hit_hint", "")

        # Build available payload catalog for on_hit selection
        all_payloads = primitive_registry.get_all_payloads()
        payload_catalog = "\n".join(
            f"- {pid}: {data.get('description', '')}"
            for pid, data in all_payloads.items()
        )

        # If a new payload is being created in parallel, pre-register it as a stub so
        # the LLM can reference it and validate_on_hit_payloads won't strip it.
        pending_payload_spec = concept.get("new_payload_spec") or {}
        pending_pid  = pending_payload_spec.get("id", "")
        pending_desc = pending_payload_spec.get("description", "")
        if pending_pid and pending_pid not in all_payloads:
            payload_catalog += f"\n- {pending_pid}: {pending_desc}"
            primitive_registry.add_payload(pending_pid, {"id": pending_pid, "description": pending_desc, "sequence": []})

        animation_catalog = _animation_preset_catalog()
        print(f"[ProjectileFactory] Generating new projectile: {proj_id} | desc={description[:80]}")

        MAX_ATTEMPTS = 3
        last_error = None
        result = None
        invoke_args = {
            "projectile_id":    proj_id,
            "description":      description,
            "speed_hint":       speed_hint,
            "lifetime_hint":    lifetime_hint,
            "on_hit_hint":      on_hit_hint,
            "payload_catalog":  payload_catalog,
            "animation_catalog": animation_catalog,
        }
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = await self.chain.ainvoke(
                    invoke_args,
                    config={"callbacks": make_callbacks("ProjectileFactory", state.get("session_id", "default"), config)},
                )
                break
            except Exception as e:
                last_error = e
                print(f"❌ [ProjectileFactory] Attempt {attempt}/{MAX_ATTEMPTS} failed for '{proj_id}': {e}")

        if result is None:
            print(f"❌ [ProjectileFactory] All {MAX_ATTEMPTS} attempts failed for '{proj_id}' "
                  f"(desc='{description}'). Last error: {last_error}")
            return {}

        final_id = result.id

        # Build the projectile JSON (matches Unity ProjectileSchema)
        stats_dict: Dict[str, Any] = {
            "speed":    result.stats.speed,
            "lifetime": result.stats.lifetime,
            "penetration": result.stats.penetration,
        }
        if result.stats.collider_radius is not None:
            stats_dict["collider_radius"] = result.stats.collider_radius

        projectile_dict = {
            "id":   final_id,
            "name": result.name,
            "stats": stats_dict,
            "animation": {"preset": result.animation_preset},
            "abilities": {
                "on_hit": result.on_hit_payloads
            },
        }

        # Select projectile icon + shader color (independent of weapon artist)
        try:
            from app.agents.projectile_artist.graph import projectile_artist_agent
            icon_data = await projectile_artist_agent.select_icon(
                projectile_id=final_id,
                name=result.name,
                description=description,
                on_hit_payloads=result.on_hit_payloads,
                speed=result.stats.speed,
                lifetime=result.stats.lifetime,
            )
            projectile_dict["icon"]         = icon_data["icon"]
            projectile_dict["visual_stats"] = icon_data["visual_stats"]
            projectile_dict["icon_b64"]     = icon_data.get("icon_b64")
        except Exception as e:
            print(f"[ProjectileFactory] Artist failed (no icon assigned): {e}")

        # Backup to disk (per-session subfolder)
        session_id = state.get("session_id", "default")
        session_dir = settings.SESSIONS_DIR / session_id / "projectiles"
        save_path: Path = session_dir / f"{final_id}.json"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(projectile_dict, f, indent=2, ensure_ascii=False)
            print(f"[ProjectileFactory] Backup saved: {save_path}")
        except Exception as e:
            print(f"[ProjectileFactory] Failed to save projectile file: {e}")

        # Persist to MongoDB + update in-memory cache
        try:
            from app.services.mongo_service.projectiles_services import projectile_mongo_service
            await projectile_mongo_service.save_generated_projectile(session_id, projectile_dict)
            primitive_registry.add_projectile(final_id, projectile_dict)
        except Exception as e:
            print(f"[ProjectileFactory] DB save failed (cache still updated): {e}")

        print(f"[ProjectileFactory] Done. Reasoning: {result.reasoning}")
        existing = state.get("pending_projectile_ids") or []
        return {
            "pending_projectile_ids": existing + [final_id],
        }


projectile_factory_agent = ProjectileFactoryAgent()
