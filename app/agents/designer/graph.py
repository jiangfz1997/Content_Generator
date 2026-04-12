from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional
import json

from app.core.config import settings
from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.services.llm_service import llm_service
from langchain_core.prompts import load_prompt
from langchain_core.runnables import RunnableConfig
from app.core.state import GlobalState
from app.utils.inject_prompts import inject_prompts
from app.utils.callbacks import make_callbacks

from app.services.engine_docs_manager import engine_docs_manager
from app.services.primitive_registry import primitive_registry


_VALID_PRIMITIVES = frozenset({
    "OP_MODIFY_HP", "OP_TIMER", "OP_APPLY_FORCE", "OP_MODIFY_SPEED", "OP_SPAWN_PROJECTILE"
})

# Fields to strip from context objects injected into prompts (SLIM_CONTEXT=true)
_WEAPON_KEEP  = {"id", "name", "abilities", "summary"}
_MATERIAL_KEEP = {"itemName", "description"}
_STRIP_ICON   = {"icon_b64", "generated_icon_b64"}


def _slim_weapon(w: dict) -> dict:
    """Keep only fields the LLM needs for design context. Drop motions/stats/visual_stats/icon."""
    if not settings.SLIM_CONTEXT:
        return {k: v for k, v in w.items() if k not in _STRIP_ICON}
    print("[DesignBlueprint] SLIM_CONTEXT is True — stripping weapon fields for prompt injection.")
    return {k: w[k] for k in _WEAPON_KEEP if k in w}


def _slim_material(m: dict) -> dict:
    """Keep only itemName and description. Drop id/itemType/count_in_altar."""
    if not settings.SLIM_CONTEXT:
        return m
    print("[DesignBlueprint] SLIM_CONTEXT is True — stripping material fields for prompt injection.")
    return {k: m[k] for k in _MATERIAL_KEEP if k in m}


# --- Step 1: 带有思维链 (CoT) 的策划蓝图结构 ---
class NewProjectileSpec(BaseModel):
    id: str = Field(description="New projectile ID in snake_case with 'projectile_' prefix, e.g. 'projectile_dark_bolt'")
    description: str = Field(description="What this projectile looks/behaves like. 1-2 sentences.")
    speed_hint: float = Field(description="Suggested travel speed (e.g. 8.0 slow, 14.0 normal, 20.0 fast)")
    lifetime_hint: float = Field(description="Suggested lifetime in seconds before despawn (e.g. 1.5–4.0)")
    on_hit_hint: str = Field(description=(
        "Which existing payload IDs should trigger on_hit. "
        "Copy IDs CHARACTER-FOR-CHARACTER from the Payload Catalog. "
        "Example: 'payload_dot_poison, payload_knockback'"
    ))


class NewPayloadSpec(BaseModel):
    id: str = Field(description="New payload ID in snake_case with 'payload_' prefix, e.g. 'payload_chain_lightning'")
    description: str = Field(description="What single combat effect this payload produces. 1-2 sentences.")
    primitive_hint: str = Field(description=(
        "Which engine primitives to use and how. "
        "ONLY reference primitives from this exact list: "
        "OP_MODIFY_HP, OP_TIMER, OP_APPLY_FORCE, OP_MODIFY_SPEED, OP_SPAWN_PROJECTILE. "
        "Example: 'OP_TIMER wrapping OP_MODIFY_HP (fire tag, weapon_multiplier)'. "
        "Do NOT invent primitive names like OP_DOT, OP_CHAIN, OP_BUFF, etc."
    ))

    @model_validator(mode="after")
    def sanitize_primitive_hint(self):
        import re
        # Find all OP_SOMETHING tokens in the hint
        found = re.findall(r"OP_[A-Z_]+", self.primitive_hint)
        invalid = [op for op in found if op not in _VALID_PRIMITIVES]
        if invalid:
            # Strip invalid tokens from the hint text
            cleaned = self.primitive_hint
            for op in invalid:
                cleaned = cleaned.replace(op, "OP_MODIFY_HP")
            self.primitive_hint = cleaned
            print(f"[DesignBlueprint] Replaced invalid primitives {invalid} with OP_MODIFY_HP in hint.")
        return self


class DesignBlueprint(BaseModel):
    # 🧠 大脑前额叶：强制先进行战术和材料分析 (放在最前面！)
    manual_analysis: str = Field(
        description="STEP 1: Analyze the Engine Tactical Manual. Which payload best fits the user's request and current biome?(MAX 25 words)")
    material_synergy: str = Field(
        description="STEP 2: How do the provided materials justify this design? This will appear as the weapon's material flavor text.(MAX 25 words)")

    # 🦾 运动皮层：真正输出游戏设计数据
    keywords: List[str] = Field(
        description=(
            "Exactly 3 to 5 single-word elemental/thematic tags for this weapon's identity. "
            "GOOD examples: ['fire', 'volcanic', 'burn', 'melee'] or ['poison', 'shadow', 'slow', 'dagger']. "
            "BAD examples: payload IDs, primitive names, field names, sentences, or anything with underscores or spaces. "
            "These tags describe the THEME, not the implementation."
        )
    )
    codename: str = Field(description="The thematic name of the weapon")
    visual_manifest: str = Field(description="Visual description of the weapon(MAX 50 words)")
    core_mechanic: str = Field(
        description="Detailed explanation of the gameplay gimmick, explicitly referencing the chosen Payload ID(MAX 50 words)")
    lore: str = Field(description="A short flavor text (MAX 25 words)")

    weapon_type: Literal["melee", "ranged"] = Field(
        description=(
            "STEP 3: Classify the weapon. "
            "'melee' = hitbox-based contact weapon (sword, axe, spear). "
            "'ranged' = fires a projectile at attack start (bow, wand, gun). "
            "This determines which base payload is auto-injected."
        )
    )

    # 武器制造者直接使用的 payload ID 列表 — 从 Payload Catalog 逐字复制
    chosen_payload_ids: List[str] = Field(
        default_factory=list,
        description=(
            "STEP 3: The exact payload IDs this weapon will use, copied CHARACTER-FOR-CHARACTER from the Payload Catalog. "
            "List 1–3 IDs. If needs_new_payload=True, include the new payload's ID here too. "
            "Example: ['payload_dot_fire', 'payload_knockback']. NEVER invent IDs."
        )
    )

    # 投射物选择（任意 weapon_type 均可使用，只要 chosen_payload_ids 中有 OP_SPAWN_PROJECTILE 的 payload）
    chosen_projectile_id: Optional[str] = Field(
        default=None,
        description=(
            "STEP 4: If ANY of your chosen payloads spawns a projectile (OP_SPAWN_PROJECTILE), "
            "pick the projectile from AVAILABLE PROJECTILES list. "
            "Leave None if no spawn payload is used. "
            "NEVER invent a projectile ID — copy exactly from the list."
        )
    )

    # Projectile Factory routing
    needs_new_projectile: bool = Field(
        default=False,
        description=(
            "Set True ONLY if no existing projectile in AVAILABLE PROJECTILES fits the design "
            "(e.g. a homing fireball, a bouncing blade, a slow poison cloud). "
            "NEVER set True just to change numeric values — use chosen_projectile_id + stats tuning instead."
        )
    )
    new_projectile_spec: Optional[NewProjectileSpec] = Field(
        default=None,
        description="Required if needs_new_projectile=True. Describe the new projectile to create."
    )

    # Payload Factory routing
    needs_new_payload: bool = Field(
        default=False,
        description=(
            "Set True ONLY if no existing payload in the Engine Manual can express the core mechanic "
            "through a structurally different effect type (e.g. chain lightning, shield, teleport). "
            "NEVER set True just because you want different numeric values (damage, duration, speed) — "
            "existing payloads already scale with weapon stats via weapon_multiplier. Default: False."
        ))
    new_payload_spec: Optional[NewPayloadSpec] = Field(
        default=None,
        description="Required if needs_new_payload=True. Describe the new payload to create.")

    @model_validator(mode="after")
    def sanitize_blueprint(self):
        # Fix 1a: auto-set needs_new_payload if spec was provided but flag was forgotten
        if self.new_payload_spec is not None and not self.needs_new_payload:
            print("[DesignBlueprint] new_payload_spec provided but needs_new_payload=False — auto-correcting to True.")
            self.needs_new_payload = True

        # Fix 1b: auto-set needs_new_projectile if spec was provided but flag was forgotten
        if self.new_projectile_spec is not None and not self.needs_new_projectile:
            print("[DesignBlueprint] new_projectile_spec provided but needs_new_projectile=False — auto-correcting to True.")
            self.needs_new_projectile = True

        # Fix 2: strip technical/implementation words from keywords
        bad_patterns = ("payload_", "op_", "needs_", "new_", "spec", "source", "multiplier",
                        "true", "false", "null", "value", "damage", "duration")
        cleaned = [
            kw for kw in self.keywords
            if " " not in kw
            and len(kw) <= 20
            and not any(kw.lower().startswith(p) for p in bad_patterns)
        ]
        self.keywords = cleaned[:5] if cleaned else ["elemental", "melee"]

        # Fix 3: validate chosen_payload_ids against registry
        # New payload IDs (from new_payload_spec) are not yet in registry — keep them
        new_id = self.new_payload_spec.id if self.new_payload_spec else None
        all_payloads = primitive_registry.get_all_payloads()
        known = set(all_payloads.keys())
        valid, invalid = [], []
        for pid in self.chosen_payload_ids:
            if pid == new_id or pid in known:
                valid.append(pid)
            else:
                invalid.append(pid)
        if invalid:
            print(f"[DesignBlueprint] Removed invalid chosen_payload_ids: {invalid}")
        self.chosen_payload_ids = valid

        # Fix 3b: strip auto-injected base payloads that the LLM mistakenly listed manually
        _AUTO_INJECTED = {"payload_shoot_generic", "payload_strike"}
        self.chosen_payload_ids = [pid for pid in self.chosen_payload_ids if pid not in _AUTO_INJECTED]

        # Fix 4: auto-inject base payload if missing
        def _has_toplevel_primitive(pid: str, primitive: str) -> bool:
            """Check if a payload's TOP-LEVEL sequence contains a primitive.
            Does NOT recurse into OP_TIMER.actions — timer-wrapped OP_MODIFY_HP is DoT, not instant damage."""
            payload = all_payloads.get(pid, {})
            return any(
                step.get("primitive_id") == primitive
                for step in payload.get("sequence", [])
                if isinstance(step, dict)
            )

        # Melee base damage — always inject payload_strike for contact weapons,
        # even when the weapon also fires a shockwave projectile.
        if self.weapon_type == "melee":
            has_damage = any(_has_toplevel_primitive(pid, "OP_MODIFY_HP") for pid in self.chosen_payload_ids)
            if not has_damage and "payload_strike" in known:
                self.chosen_payload_ids = ["payload_strike"] + self.chosen_payload_ids
                print("[DesignBlueprint] Auto-injected payload_strike as base melee damage.")

        # Ranged weapons always fire via on_attack.
        # payload_shoot_generic is engine built-in — not on disk, always inject for ranged.
        if self.weapon_type == "ranged":
            if "payload_shoot_generic" not in self.chosen_payload_ids:
                self.chosen_payload_ids = ["payload_shoot_generic"] + self.chosen_payload_ids
                print("[DesignBlueprint] Auto-injected payload_shoot_generic for ranged weapon.")

        # Fix 5: validate chosen_projectile_id against registry
        # Ranged weapons or melee+spawn need a valid projectile_id in stats
        new_proj_id = self.new_projectile_spec.id if self.new_projectile_spec else None
        # payload_shoot_generic is built-in (no file), detect ranged by weapon_type or on-disk spawn payloads
        has_any_spawn = (
            self.weapon_type == "ranged"
            or "payload_shoot_generic" in self.chosen_payload_ids
            or any(_has_toplevel_primitive(pid, "OP_SPAWN_PROJECTILE") for pid in self.chosen_payload_ids)
        )
        if has_any_spawn:
            all_projectiles = primitive_registry.get_all_projectiles()
            known_proj = set(all_projectiles.keys())
            # new_projectile_spec ID is not on disk yet — treat as valid
            valid_proj = known_proj | ({new_proj_id} if new_proj_id else set())
            if not self.chosen_projectile_id or self.chosen_projectile_id not in valid_proj:
                # Prefer the new spec if it exists, else fall back to projectile_bullet
                fallback = new_proj_id or ("projectile_bullet" if "projectile_bullet" in known_proj else next(iter(known_proj), None))
                if self.chosen_projectile_id and self.chosen_projectile_id not in valid_proj:
                    print(f"[DesignBlueprint] Invalid chosen_projectile_id '{self.chosen_projectile_id}' — falling back to '{fallback}'.")
                else:
                    print(f"[DesignBlueprint] No projectile selected but spawn payload present — auto-selecting '{fallback}'.")
                self.chosen_projectile_id = fallback
        else:
            # No spawn payload → projectile_id is irrelevant
            self.chosen_projectile_id = None

        # Fix 6: melee weapons that ended up with a projectile (shockwave / energy wave)
        # need payload_shoot_generic in on_attack so Unity knows to fire it.
        # This runs after Fix 5 so chosen_projectile_id is already validated.
        if (self.weapon_type == "melee"
                and self.chosen_projectile_id
                and "payload_shoot_generic" not in self.chosen_payload_ids):
            self.chosen_payload_ids = self.chosen_payload_ids + ["payload_shoot_generic"]
            print("[DesignBlueprint] Auto-injected payload_shoot_generic for melee weapon with projectile.")

        return self


class DesignerAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "designer.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        # 绑定带有 CoT 字段的模型
        self.planner_llm = llm_service.get_structured_model("designer", DesignBlueprint)

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)
        self.chain = self.prompt | self.planner_llm

    async def planning_node(self, state: GlobalState, config: RunnableConfig | None = None):
        # 1. 序列化基础物资
        raw_materials = state.get("materials", [])
        materials_full_dump = [json.dumps(_slim_material(m), ensure_ascii=False) for m in raw_materials]

        raw_weapons = state.get("weapons", [])
        weapons_full_dump = [json.dumps(_slim_weapon(w), ensure_ascii=False) for w in raw_weapons]

        if state.get("engine_manual", None) is None:
            # Designer only needs the Payload Catalog — Constitution is already injected
            # via inject_prompts(), and Weapon/Projectile schemas are irrelevant at design phase.
            engine_manual_md = await engine_docs_manager.get_reviewer_manual()
            state["engine_manual"] = engine_manual_md
        else:
            engine_manual_md = state["engine_manual"]

        # --- 相近武器：同 biome，带完整 payload 组合，供 designer 判断重复度 ---
        similar = state.get("similar_weapons", [])[:2]
        if similar:
            similar_lines = []
            all_used_payloads = set()
            for w in similar:
                abilities = w.get("abilities", {})
                combos = (
                    abilities.get("on_hit", []) +
                    abilities.get("on_attack", []) +
                    abilities.get("on_equip", [])
                )
                all_used_payloads.update(combos)
                combo_str = " + ".join(combos) if combos else w.get("primary_payload", "?")
                similar_lines.append(
                    f"- [{w.get('id', '?')}] {w.get('name', '?')} "
                    f"(Lv{w.get('level', '?')}) [{combo_str}]: {w.get('summary', '')}"
                )
            proven_payloads = ", ".join(sorted(all_used_payloads)) if all_used_payloads else "none yet"
            similar_str = (
                "\n".join(similar_lines) +
                f"\n\nPayloads proven in this biome: {proven_payloads}"
                "\n→ PREFER combining these before requesting a new payload via Factory."
            )
        else:
            similar_str = "No weapons in this biome yet — you are pioneering this design space."

        # --- 全库：仅 ID + 名称，防止重名，最多取 2 条 ---
        ref_weapons = state.get("reference_weapons", [])[:2]
        ref_weapons = [] # TODO:only for debug
        if ref_weapons:
            history_str = "\n".join([
                f"- [{w.get('id', '?')}] {w.get('name', '?')} (Lv{w.get('level', '?')}): {w.get('summary', '')}"
                for w in ref_weapons
            ])
        else:
            history_str = "No weapons created yet. You are designing the first one."

        print(f"[Designer] Consulting engine manual, designing for biome={state.get('biome')}...")

        # Build available projectiles summary for the prompt
        all_projectiles = primitive_registry.get_all_projectiles()
        available_projectiles = "\n".join(
            f"- {pid}: speed={p['stats'].get('speed', '?')}, "
            f"lifetime={p['stats'].get('lifetime', '?')}s, "
            f"on_hit={p.get('abilities', {}).get('on_hit', [])}"
            for pid, p in all_projectiles.items()
        ) or "No projectiles available."

        blueprint: DesignBlueprint = await self.chain.ainvoke(
            {
                "materials": "\n---\n".join(materials_full_dump),
                "weapons": "\n---\n".join(weapons_full_dump),
                "prompt": state.get("prompt", "None"),
                "level": state.get("level", 0),
                "biome": state.get("biome", "Unknown"),
                "feedback": state.get("idea_feedback", "None"),
                "engine_manual": engine_manual_md,
                "similar_weapons": similar_str,
                "past_weapons": history_str,
                "available_projectiles": available_projectiles,
            },
            
            config={"callbacks": make_callbacks("DesignerAgent", state.get("session_id", "default"), config)}
        )

        print(f"[Designer] Blueprint ready: {blueprint.codename}")

        return {"design_concept": blueprint.model_dump()}


# 实例化
designer_agent = DesignerAgent()