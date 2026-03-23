import json
from langchain_core.prompts import load_prompt, ChatPromptTemplate

from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.core.state import GlobalState
from app.services.engine_docs_manager import engine_docs_manager
from app.services.llm_service import llm_service
from app.services.primitive_registry import primitive_registry
from app.core.config import settings
from app.models.schemas import WeaponSchema, WeaponPatchSchema, apply_weapon_patch
from app.agents.designer.graph import _slim_weapon
from app.utils.callbacks import make_callbacks
from app.utils.inject_prompts import inject_prompts


class WeaponAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "weapon_crafter.yaml"

        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")
        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)


        self.structured_llm = llm_service.get_model("weapon_crafter").with_structured_output(WeaponSchema)
        inject_prompts(GLOBAL_DESIGN_CONSTITUTION, self.prompt)
        self.chain = self.prompt | self.structured_llm
        self.fresh_payloads = None
        self.fresh_primitives = None
        self.fresh_motions = None

        # Surgical patch chain: only fixes fields flagged by the auditor
        _patch_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Technical Weapon Surgeon. Your ONLY job is to fix the EXACT issues listed in the auditor's feedback.

Engine Manual (reference for valid payload/motion IDs):
{engine_manual}

CRITICAL RULES:
- ONLY modify the fields explicitly mentioned in the feedback.
- Keep ALL other fields byte-for-byte identical to the original.
- Do NOT rename, redesign, or restructure anything not mentioned.
- Payload IDs MUST exist in the Engine Manual above.
"""),
            ("human", """Current Weapon JSON:
{current_weapon}

Auditor Feedback (fix ONLY these issues):
{feedback}

Biome: {biome} | Level: {level}

Output ONLY the fields that need to change."""),
        ])
        self.patch_chain = _patch_prompt | llm_service.get_model("weapon_patcher").with_structured_output(WeaponPatchSchema)




    async def crafting_node(self, state: GlobalState):
        """
        真正的“大脑”执行逻辑
        """
        # 组装 Chain：Prompt + LLM Service
        # 注意：这里直接使用了 llm_service 暴露出的模型实例
        print(f"[Crafting Node] 输入状态: biome={state['biome']}, level={state['level']}")
        # 执行推理
        # registry_context = format_registries_for_llm_yaml(available_payloads=self.fresh_payloads,
        #     available_primitives=self.fresh_primitives,
        #     available_motions=self.fresh_motions,
        # )
        crafter_manual = await engine_docs_manager.get_crafter_manual()

        history = state.get("generation_history", [])[-20:]
        history_str = "\n".join([f"- {w['weapon_id']}" for w in history]) if history else "No weapons created yet."

        concept = state.get("design_concept") or {}
        keywords = concept.get("keywords", [])
        keywords_str = ", ".join(keywords) if keywords else "none specified"

        # Payload IDs resolved by the designer — passed as hard constraint
        chosen_ids = concept.get("chosen_payload_ids") or []
        if chosen_ids:
            all_payloads = primitive_registry.get_all_payloads()
            chosen_payloads_str = "\n".join(
                f"- {pid}: {all_payloads.get(pid, {}).get('description', '(engine built-in)') if pid != 'payload_shoot_generic' else '(engine built-in) fires projectile_id from stats'}"
                for pid in chosen_ids
            )
        else:
            chosen_payloads_str = "(none specified — choose from the engine manual)"

        # Projectile context for ranged weapons
        chosen_projectile_id = concept.get("chosen_projectile_id")
        projectile_hint = (
            f"This weapon fires projectile: **{chosen_projectile_id}**. "
            f"Set stats.projectile_id = \"{chosen_projectile_id}\". "
            f"Set stats.hit_start = 0, stats.hit_end = 0."
            if chosen_projectile_id else
            "Melee weapon — no projectile. Leave stats.projectile_id null."
        )

        try:
            weapon_obj: WeaponSchema = await self.chain.ainvoke({
                "biome": state["biome"],
                "level": state["level"],
                "materials": state["materials"],
                "weapons": [
                    _slim_weapon(w) for w in (state.get("weapons") or [])
                ],
                "concept": concept,
                "keywords": keywords_str,
                "feedback": state.get("tech_feedback", "None"),
                "crafter_manual": crafter_manual,
                "chosen_payload_ids": chosen_payloads_str,
                "past_weapons": history_str,
                "projectile_hint": projectile_hint,
            },
                config={"callbacks": make_callbacks("WeaponAgent", state.get("session_id", "default"))})


            weapon_dict = weapon_obj.model_dump()

            # Hard-override: designer's chosen_projectile_id is the source of truth.
            # Never trust the LLM to copy it correctly into stats.projectile_id.
            if chosen_projectile_id:
                weapon_dict.setdefault("stats", {})["projectile_id"] = chosen_projectile_id
                weapon_dict["stats"]["hit_start"] = 0.0
                weapon_dict["stats"]["hit_end"] = 0.0
                print(f"[CraftingNode] Overrode stats.projectile_id → {chosen_projectile_id}")

            return {"final_output": weapon_dict, "generation_history": state.get("generation_history", [])}
        except Exception as e:
            err_msg = f"[Crafting Node] {e}"
            print(err_msg)
            return {
                "final_output": None,
                "is_valid": False,
                "validation_errors": err_msg
            }
    async def patch_node(self, state: GlobalState):
        """Surgical patch: fix only the fields flagged by tech_auditor feedback."""
        original_weapon = state.get("final_output", {})
        feedback = state.get("tech_feedback", "")
        print(f"[PatchNode] 外科手术修复，问题: {feedback[:80]}...")

        if state.get("engine_manual"):
            engine_manual_md = state["engine_manual"]
        else:
            engine_manual_md = await engine_docs_manager.get_markdown_manual()

        try:
            patch_result: WeaponPatchSchema = await self.patch_chain.ainvoke(
                {
                    "current_weapon": json.dumps(original_weapon, ensure_ascii=False),
                    "feedback": feedback,
                    "engine_manual": engine_manual_md,
                    "biome": state.get("biome", "Unknown"),
                    "level": state.get("level", 1),
                },
                config={"callbacks": make_callbacks("WeaponPatcher", state.get("session_id", "default"))},
            )
            patched_weapon = apply_weapon_patch(original_weapon, patch_result)

            # Re-apply projectile_id override in case patcher stomped it
            concept = state.get("design_concept") or {}
            proj_id = concept.get("chosen_projectile_id")
            if proj_id:
                patched_weapon.setdefault("stats", {})["projectile_id"] = proj_id
                patched_weapon["stats"]["hit_start"] = 0.0
                patched_weapon["stats"]["hit_end"] = 0.0

            print(f"[PatchNode] 修复完成: {patch_result.patch_analysis}")
            return {"final_output": patched_weapon}
        except Exception as e:
            print(f"[PatchNode] 修复失败，保留原始数据: {e}")
            return {"final_output": original_weapon}


    # async def perform_surgical_patch(self, original_weapon: dict, audit_feedback: str) -> dict:
    #     """
    #     独立修复方法：只针对反馈进行局部修改
    #     """
    #     print(f"💉 [WeaponAgent] Detecting issues: {audit_feedback[:50]}...")
    #
    #     # 1. 使用专门的补丁 Prompt (比全量生成的 Prompt 简单得多)
    #     patch_prompt = """
    #     You are a Technical Surgeon.
    #     Current Weapon Data: {current_weapon}
    #     Auditor's Feedback: {feedback}
    #
    #     Instruction: ONLY output the fields that must be changed to pass the audit.
    #     Keep all other fields identical. If 'stats.range' is the only issue, only return the 'stats' object.
    #     """
    #
    #     # 2. 调用补丁链
    #
    #
    #     patch_result: WeaponPatchSchema = await patch_chain.ainvoke({
    #         "current_weapon": json.dumps(original_weapon),
    #         "feedback": audit_feedback
    #     })
    #
    #     # 3. 应用补丁
    #     new_weapon = apply_weapon_patch(original_weapon, patch_result)
    #
    #     return new_weapon
    # async def run(self, input_data: Dict[str, Any]):
    #     """
    #     供外部 Router 调用的入口
    #     """
    #     # 初始化状态并运行
    #     initial_state = {
    #         "biome": input_data.get("biome", "Unknown"),
    #         "level": input_data.get("level", 1),
    #         "retry_count": 0
    #     }
    #     final_state = await self.graph.ainvoke(initial_state)
    #     return final_state["weapon_json"]


# 单例模式，供 API 层调用
weapon_agent = WeaponAgent()