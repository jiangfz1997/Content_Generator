import json
from pathlib import Path
from typing import List, Dict, Any

from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import load_prompt
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.state import GlobalState
from app.services.engine_docs_manager import engine_docs_manager
from app.services.llm_service import llm_service
from app.services.primitive_registry import primitive_registry
from app.utils.callbacks import make_callbacks


# Known parameter keys per primitive — used to rescue flat-layout outputs
_PRIMITIVE_PARAM_KEYS: Dict[str, set] = {
    "OP_APPLY_FORCE":      {"magnitude", "target_type", "direction_mode", "override_duration"},
    "OP_MODIFY_HP":        {"value", "source", "category", "tag", "target_type"},
    "OP_MODIFY_SPEED":     {"value", "target_type", "mode", "duration"},
    "OP_TIMER":            {"duration", "interval", "actions"},
    "OP_SPAWN_PROJECTILE": {"projectile_id", "count", "spread_angle"},
}

_VALID_DIRECTION_MODES = {"HitNormal", "SourceForward", "FromHitPoint", "SourceToTarget", "FromColliderCenter"}
_VALID_HP_SOURCES      = {"weapon_multiplier", "absolute"}
_VALID_HP_CATEGORIES   = {"damage", "heal", "self_damage"}
_VALID_SPEED_MODES     = {"Set", "Add", "Multiplier"}


# --- Output schema for a single generated payload ---
class PrimitiveEntry(BaseModel):
    primitive_id: str = Field(description="Exact primitive ID: OP_MODIFY_HP | OP_TIMER | OP_APPLY_FORCE | OP_MODIFY_SPEED | OP_SPAWN_PROJECTILE")
    params: Dict[str, Any] = Field(description=(
        "ALL parameters MUST be nested inside this object. NEVER null. NEVER flat at the same level as primitive_id. "
        "Example: {\"primitive_id\": \"OP_APPLY_FORCE\", \"params\": {\"magnitude\": 12.0, \"direction_mode\": \"FromHitPoint\", \"target_type\": \"target\"}}. "
        "For OP_MODIFY_HP: value MUST be a positive float (e.g. 1.0), source is 'weapon_multiplier' or 'absolute', category is 'damage'/'heal'/'self_damage'."
    ))

    @model_validator(mode="before")
    @classmethod
    def rescue_flat_params(cls, data: Any) -> Any:
        """
        Rescue malformed params from three LLM failure modes:
          1. params is a flat list of alternating [key, val, key, val, ...]
          2. params is null/missing but fields sit at the same level as primitive_id
          3. params is already a valid dict — nothing to do
        """
        if not isinstance(data, dict):
            return data
        pid = data.get("primitive_id", "")
        raw_params = data.get("params")

        # Case 1: LLM serialized params as an alternating key-value list
        if isinstance(raw_params, list):
            if len(raw_params) % 2 == 0:
                try:
                    rescued = dict(zip(raw_params[::2], raw_params[1::2]))
                    print(f"[PrimitiveEntry] Rescued list-format params for {pid}: {list(rescued.keys())}")
                    data["params"] = rescued
                    return data
                except Exception:
                    pass
            print(f"[PrimitiveEntry] params is an unrecoverable list for {pid}, using empty dict.")
            data["params"] = {}
            return data

        # Case 2: params is a valid dict — nothing to do
        if isinstance(raw_params, dict) and raw_params:
            return data

        # Case 3: params is None/null/missing — collect known param keys from sibling fields
        known_keys = _PRIMITIVE_PARAM_KEYS.get(pid, set())
        rescued = {k: data[k] for k in known_keys if k in data}
        if rescued:
            print(f"[PrimitiveEntry] Rescued flat params for {pid}: {list(rescued.keys())}")
            data = {k: v for k, v in data.items() if k not in known_keys}
            data["params"] = rescued
        else:
            data["params"] = {}
        return data

    @model_validator(mode="after")
    def validate_and_sanitize(self):
        p = self.params

        # --- Fix "target" → "target_type" hallucination ---
        if "target" in p and "target_type" not in p:
            raw = p.pop("target")
            p["target_type"] = "self" if "self" in str(raw).lower() else "target"

        # --- Clamp target_type ---
        if "target_type" in p and p["target_type"] not in ("self", "target"):
            p["target_type"] = "target"

        pid = self.primitive_id

        # ── OP_MODIFY_HP ──────────────────────────────────────────────────────
        if pid == "OP_MODIFY_HP":
            v = p.get("value")
            if not isinstance(v, (int, float)):
                raise ValueError(f"OP_MODIFY_HP.value must be a positive float, got {type(v).__name__!r}: {v!r}")
            if float(v) <= 0:
                raise ValueError(f"OP_MODIFY_HP.value must be > 0, got {v}")
            if p.get("source") not in _VALID_HP_SOURCES:
                p["source"] = "weapon_multiplier"
            if p.get("category") not in _VALID_HP_CATEGORIES:
                p["category"] = "damage"

        # ── OP_APPLY_FORCE ────────────────────────────────────────────────────
        elif pid == "OP_APPLY_FORCE":
            if not isinstance(p.get("magnitude"), (int, float)):
                raise ValueError(f"OP_APPLY_FORCE.magnitude must be a float, got {p.get('magnitude')!r}")
            if p.get("direction_mode") not in _VALID_DIRECTION_MODES:
                # common hallucination: plain int/degree → default to FromHitPoint
                p["direction_mode"] = "FromHitPoint"

        # ── OP_MODIFY_SPEED ───────────────────────────────────────────────────
        elif pid == "OP_MODIFY_SPEED":
            if not isinstance(p.get("value"), (int, float)):
                raise ValueError(f"OP_MODIFY_SPEED.value must be a float, got {p.get('value')!r}")
            if p.get("mode") not in _VALID_SPEED_MODES:
                p["mode"] = "Multiplier"
            if not isinstance(p.get("duration"), (int, float)):
                p["duration"] = 3.0  # safe default

        # ── OP_TIMER ──────────────────────────────────────────────────────────
        elif pid == "OP_TIMER":
            if not isinstance(p.get("duration"), (int, float)):
                print(f"[PrimitiveEntry] OP_TIMER.duration missing — defaulting to 3.0")
                p["duration"] = 3.0
            if not isinstance(p.get("interval"), (int, float)):
                p["interval"] = 1.0  # safe default
            if not isinstance(p.get("actions"), list):
                raise ValueError(f"OP_TIMER.actions must be a list, got {type(p.get('actions')).__name__!r}")
            # Recursively validate each action — applies rescue_flat_params + type checks
            validated_actions = []
            for i, action in enumerate(p["actions"]):
                if not isinstance(action, dict):
                    print(f"[PrimitiveEntry] OP_TIMER.actions[{i}] is not a dict, skipping.")
                    continue
                try:
                    validated_actions.append(PrimitiveEntry.model_validate(action).model_dump())
                except Exception as e:
                    print(f"[PrimitiveEntry] OP_TIMER.actions[{i}] validation failed: {e} — dropping entry.")
            p["actions"] = validated_actions

        # ── OP_SPAWN_PROJECTILE ───────────────────────────────────────────────
        elif pid == "OP_SPAWN_PROJECTILE":
            # projectile_id must always be the runtime alias — the actual projectile is
            # chosen by the designer and stored in weapon.stats.projectile_id at runtime.
            # Never allow the LLM to hardcode a specific projectile ID here.
            proj_id = p.get("projectile_id", "")
            if proj_id != "@weapon.projectile_id":
                if proj_id:
                    print(f"[PrimitiveEntry] Replaced hardcoded projectile_id '{proj_id}' "
                          f"with runtime alias '@weapon.projectile_id'")
                p["projectile_id"] = "@weapon.projectile_id"

        return self


class GeneratedPayload(BaseModel):
    factory_reasoning: str = Field(description="Brief explanation of the primitive chain chosen. MAX 20 words.")
    id: str = Field(description="Payload ID in snake_case with 'payload_' prefix")
    description: str = Field(description="One sentence describing the effect")
    sequence: List[PrimitiveEntry] = Field(description="Ordered list of logic primitives that produce the effect")


class PayloadFactoryAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "payload_factory.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)
        self.chain = self.prompt | llm_service.get_structured_model("payload_factory", GeneratedPayload)

    async def generate_node(self, state: GlobalState, config: RunnableConfig | None = None) -> dict:
        """
        Reads new_payload_spec from design_concept, generates a payload JSON,
        saves it to app/data/payloads/, and appends the description to engine_manual in state.
        """
        concept = state.get("design_concept", {})
        if not isinstance(concept, dict):
            print("[PayloadFactory] design_concept is not a dict, skipping factory.")
            return {}

        spec = concept.get("new_payload_spec")
        if not spec:
            print("[PayloadFactory] No new_payload_spec found, skipping factory.")
            return {}

        payload_id = spec.get("id", "payload_unknown")
        description = spec.get("description", "")
        primitive_hint = spec.get("primitive_hint", "")

        # Pre-register the new projectile (if any) as a stub so OP_SPAWN_PROJECTILE validation
        # can reference it even though projectile_factory may still be running in parallel.
        new_proj_spec = concept.get("new_projectile_spec") or {}
        new_proj_id   = new_proj_spec.get("id", "")
        if new_proj_id and new_proj_id not in primitive_registry.get_all_projectiles():
            primitive_registry.add_projectile(new_proj_id, {
                "id": new_proj_id, "stats": {}, "abilities": {"on_hit": []}
            })
            print(f"[PayloadFactory] Pre-registered projectile stub: {new_proj_id}")

        if state.get("engine_manual"):
            engine_manual_md = state["engine_manual"]
        else:
            engine_manual_md = await engine_docs_manager.get_factory_manual()

        print(f"[PayloadFactory] Generating new payload: {payload_id} | desc={description[:80]}")

        MAX_ATTEMPTS = 3
        last_error = None
        result = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = await self.chain.ainvoke(
                    {
                        "engine_manual": engine_manual_md,
                        "payload_id": payload_id,
                        "payload_description": description,
                        "primitive_hint": primitive_hint,
                    },
                    config={"callbacks": make_callbacks("PayloadFactory", state.get("session_id", "default"), config)},
                )
                break  # success
            except Exception as e:
                last_error = e
                print(f"❌ [PayloadFactory] Attempt {attempt}/{MAX_ATTEMPTS} failed for '{payload_id}': {e}")

        if result is None:
            print(f"❌ [PayloadFactory] All {MAX_ATTEMPTS} attempts failed for '{payload_id}' "
                  f"(desc='{description}', hint='{primitive_hint}'). Last error: {last_error}")
            return {}

        # Use the AI-confirmed ID (it may have corrected casing)
        final_id = result.id

        # Serialize to JSON — sequence entries may contain nested dicts (e.g. OP_TIMER actions)
        payload_dict = {
            "id": final_id,
            "description": result.description,
            "sequence": [entry.model_dump() for entry in result.sequence],
        }

        # Backup to disk (per-session subfolder)
        session_id = state.get("session_id", "default")
        session_dir = settings.SESSIONS_DIR / session_id / "payloads"
        save_path: Path = session_dir / f"{final_id}.json"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload_dict, f, indent=2, ensure_ascii=False)
            print(f"[PayloadFactory] Backup saved: {save_path}")
        except Exception as e:
            print(f"[PayloadFactory] Failed to save payload file: {e}")

        # Persist to MongoDB + update in-memory cache so downstream nodes see the new ID
        try:
            from app.services.mongo_service.payloads_services import payload_mongo_service
            await payload_mongo_service.save_generated_payload(session_id, payload_dict)
            primitive_registry.add_payload(final_id, payload_dict)
        except Exception as e:
            print(f"[PayloadFactory] DB save failed (cache still updated): {e}")

        # Append new payload info to the in-memory engine manual so downstream nodes see it
        new_entry = (
            f"\n### {final_id}\n"
            f"- Tactical Intent: {result.description}\n"
            f"- Logic: {result.factory_reasoning}\n"
        )
        updated_manual = engine_manual_md + new_entry

        print(f"[PayloadFactory] Done. Reasoning: {result.factory_reasoning}")
        existing_ids = state.get("pending_payload_ids") or []
        return {
            "engine_manual": updated_manual,
            "pending_payload_ids": existing_ids + [final_id],
        }


payload_factory_agent = PayloadFactoryAgent()
