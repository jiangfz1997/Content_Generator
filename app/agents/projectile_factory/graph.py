import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import load_prompt

from app.core.config import settings
from app.core.state import GlobalState
from app.services.llm_service import llm_service
from app.services.primitive_registry import primitive_registry
from app.utils.callbacks import make_callbacks


class GeneratedProjectileStats(BaseModel):
    speed: float = Field(description="Travel speed in units/sec. Typical: 8.0 (slow), 14.0 (normal), 20.0 (fast)")
    lifetime: float = Field(description="Seconds before despawn. Typical: 1.5–4.0")
    penetration: int = Field(description="0 = stops on first hit, 99 = infinite penetration")
    collider_radius: Optional[float] = Field(
        default=None,
        description="Collision radius override. Leave null for default (0.1). Use larger values for AoE projectiles."
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
    on_hit_payloads: List[str] = Field(
        description=(
            "List of existing payload IDs that trigger when this projectile hits something. "
            "Copy IDs CHARACTER-FOR-CHARACTER from the Payload Catalog. "
            "Example: ['payload_dot_poison', 'payload_knockback']. "
            "NEVER invent payload IDs."
        )
    )

    @model_validator(mode="after")
    def validate_on_hit_payloads(self):
        """Remove any on_hit payload IDs that don't exist in the library."""
        known = set(primitive_registry.get_all_payloads().keys())
        valid, invalid = [], []
        for pid in self.on_hit_payloads:
            (valid if pid in known else invalid).append(pid)
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
            | llm_service.get_model("projectile_factory").with_structured_output(GeneratedProjectile)
        )

    async def generate_node(self, state: GlobalState) -> dict:
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

        print(f"[ProjectileFactory] Generating new projectile: {proj_id}")

        try:
            result: GeneratedProjectile = await self.chain.ainvoke(
                {
                    "projectile_id":   proj_id,
                    "description":     description,
                    "speed_hint":      speed_hint,
                    "lifetime_hint":   lifetime_hint,
                    "on_hit_hint":     on_hit_hint,
                    "payload_catalog": payload_catalog,
                },
                config={"callbacks": make_callbacks("ProjectileFactory", state.get("session_id", "default"))},
            )
        except Exception as e:
            print(f"[ProjectileFactory] Generation failed: {e}")
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
            "abilities": {
                "on_hit": result.on_hit_payloads
            },
        }

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
