import json
from pathlib import Path
from typing import List, Dict, Any

from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import load_prompt

from app.core.config import settings
from app.core.state import GlobalState
from app.services.engine_docs_manager import engine_docs_manager
from app.services.llm_service import llm_service
from app.utils.callbacks import AgentConsoleCallback


# Known parameter keys per primitive — used to rescue flat-layout outputs
_PRIMITIVE_PARAM_KEYS: Dict[str, set] = {
    "OP_APPLY_FORCE":      {"magnitude", "target_type", "direction_mode", "override_duration"},
    "OP_MODIFY_HP":        {"value", "source", "category", "tag", "target_type"},
    "OP_MODIFY_SPEED":     {"value", "target_type", "mode", "duration"},
    "OP_TIMER":            {"duration", "interval", "actions"},
    "OP_SPAWN_PROJECTILE": {"projectile_id", "count", "spread_angle"},
}

_VALID_DIRECTION_MODES = {"HitNormal", "SourceForward", "FromHitPoint", "SourceToTarget"}
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
        """If LLM outputs params=null with fields at the same level, reconstruct params dict."""
        if not isinstance(data, dict):
            return data
        pid = data.get("primitive_id", "")
        raw_params = data.get("params")
        if raw_params:  # params already present and non-empty — nothing to do
            return data

        # params is None/null/missing — try to collect known param keys from sibling fields
        known_keys = _PRIMITIVE_PARAM_KEYS.get(pid, set())
        rescued = {k: data[k] for k in known_keys if k in data}
        if rescued:
            print(f"[PrimitiveEntry] Rescued flat params for {pid}: {list(rescued.keys())}")
            data = {k: v for k, v in data.items() if k not in known_keys}
            data["params"] = rescued
        else:
            data["params"] = {}  # ensure params is at least an empty dict
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
                raise ValueError(f"OP_TIMER.duration must be a float, got {p.get('duration')!r}")
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
            if not isinstance(p.get("projectile_id"), str) or not p.get("projectile_id"):
                raise ValueError(f"OP_SPAWN_PROJECTILE.projectile_id must be a non-empty string")

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
        self.chain = self.prompt | llm_service.get_model("payload_factory").with_structured_output(GeneratedPayload)

    async def generate_node(self, state: GlobalState) -> dict:
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

        if state.get("engine_manual"):
            engine_manual_md = state["engine_manual"]
        else:
            engine_manual_md = await engine_docs_manager.get_factory_manual()

        print(f"[PayloadFactory] Generating new payload: {payload_id}")

        try:
            result: GeneratedPayload = await self.chain.ainvoke(
                {
                    "engine_manual": engine_manual_md,
                    "payload_id": payload_id,
                    "payload_description": description,
                    "primitive_hint": primitive_hint,
                },
                config={"callbacks": [AgentConsoleCallback(agent_name="PayloadFactory")]},
            )
        except Exception as e:
            print(f"[PayloadFactory] Generation failed: {e}")
            return {}

        # Use the AI-confirmed ID (it may have corrected casing)
        final_id = result.id

        # Serialize to JSON — sequence entries may contain nested dicts (e.g. OP_TIMER actions)
        payload_dict = {
            "id": final_id,
            "description": result.description,
            "sequence": [entry.model_dump() for entry in result.sequence],
        }

        # Save to payloads directory
        save_path: Path = settings.PAYLOADS_PATH / f"{final_id}.json"
        try:
            settings.PAYLOADS_PATH.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload_dict, f, indent=2, ensure_ascii=False)
            print(f"[PayloadFactory] Saved: {save_path}")
        except Exception as e:
            print(f"[PayloadFactory] Failed to save payload file: {e}")

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
