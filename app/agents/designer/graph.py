from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any
import json

from app.core.config import settings
from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.services.llm_service import llm_service
from langchain_core.prompts import load_prompt
from app.core.state import GlobalState
from app.utils.inject_prompts import inject_prompts
from app.utils.callbacks import AgentConsoleCallback

# 🌟 引入刚写好的文档管理器
from app.services.engine_docs_manager import engine_docs_manager


_VALID_PRIMITIVES = frozenset({
    "OP_MODIFY_HP", "OP_TIMER", "OP_APPLY_FORCE", "OP_MODIFY_SPEED", "OP_SPAWN_PROJECTILE"
})


# --- Step 1: 带有思维链 (CoT) 的策划蓝图结构 ---
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
        # Fix 1: auto-set needs_new_payload if spec was provided but flag was forgotten
        if self.new_payload_spec is not None and not self.needs_new_payload:
            print("[DesignBlueprint] new_payload_spec provided but needs_new_payload=False — auto-correcting to True.")
            self.needs_new_payload = True

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
        return self


class DesignerAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "designer.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        # 绑定带有 CoT 字段的模型
        self.planner_llm = llm_service.get_model("designer").with_structured_output(DesignBlueprint)

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)
        self.chain = self.prompt | self.planner_llm

    async def planning_node(self, state: GlobalState):
        # 1. 序列化基础物资
        raw_materials = state.get("materials", [])
        materials_full_dump = [json.dumps(m, ensure_ascii=False) for m in raw_materials]

        raw_weapons = state.get("weapons", [])
        weapons_full_dump = [json.dumps(w, ensure_ascii=False) for w in raw_weapons]

        if state.get("engine_manual", None) is None:
            engine_manual_md = await engine_docs_manager.get_markdown_manual()
            state["engine_manual"] = engine_manual_md
        else:
            engine_manual_md = state["engine_manual"]

        # --- 相近武器：同 biome，带完整 payload 组合，供 designer 判断重复度 ---
        similar = state.get("similar_weapons", [])
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

        # --- 全库：仅 ID + 名称，防止重名 ---
        ref_weapons = state.get("reference_weapons", [])
        if ref_weapons:
            history_str = "\n".join([
                f"- [{w.get('id', '?')}] {w.get('name', '?')} (Lv{w.get('level', '?')}): {w.get('summary', '')}"
                for w in ref_weapons
            ])
        else:
            history_str = "No weapons created yet. You are designing the first one."

        print(f"[Designer] 正在查阅引擎手册，并结合 {state.get('biome')} 环境构思蓝图...")

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
            },
            
            config={"callbacks": [AgentConsoleCallback(agent_name="DesignerAgent")]}
        )

        print(f"[Designer] 构思完成: {blueprint.codename}")

        return {"design_concept": blueprint.model_dump()}


# 实例化
designer_agent = DesignerAgent()