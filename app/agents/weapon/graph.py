import json

from app.agents.weapon.state import WeaponState
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.prompts import load_prompt

from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.core.state import GlobalState
from app.services.engine_docs_manager import engine_docs_manager
from app.services.llm_service import llm_service
from app.core.config import settings
from app.models.schemas import WeaponSchema, WeaponPatchSchema, apply_weapon_patch
from app.services.primitive_registery import primitive_registry
from app.utils.callbacks import AgentConsoleCallback
from app.utils.formatter import format_registries_for_llm_yaml
from app.utils.inject_prompts import inject_prompts


class WeaponAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "weapon_crafter.yaml"

        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")
        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)


        self.structured_llm = llm_service.model.with_structured_output(WeaponSchema)
        inject_prompts(GLOBAL_DESIGN_CONSTITUTION, self.prompt)
        self.chain = self.prompt | self.structured_llm
        self.fresh_payloads = None
        self.fresh_primitives = None
        self.fresh_motions = None




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
        engine_manual_md = await engine_docs_manager.get_markdown_manual()

        # 🌟 2. 提取历史记忆 (让它知道自己之前造过什么，避免重复)
        history = state.get("generation_history", [])
        history_str = "\n".join([f"- {w['weapon_id']}" for w in history]) if history else "No weapons created yet."

        try:
            weapon_obj: WeaponSchema = await self.chain.ainvoke({
                "biome": state["biome"],
                "level": state["level"],
                "materials": state["materials"],  # 记得这里如果是列表，最好转成字符串
                "weapons": state["weapons"],
                "concept": state.get("design_concept", ""),
                "feedback": state.get("tech_feedback", "None"),

                # 🌟 3. 直接注入这两大核心上下文！取代之前的 registry_context
                "engine_manual": engine_manual_md,
                "past_weapons": history_str
            },
                # 🌟 顺手把我们写好的打字机回调加上，看着它流式思考
                config={"callbacks": [AgentConsoleCallback(agent_name="WeaponAgent")]})

            # 🌟 4. 生成成功后，别忘了把新武器存入记忆！
            state.setdefault("generation_history", []).append({
                "weapon_id": weapon_obj.id,  # 假设你的 Schema 里叫这个
                # "payload": weapon_obj.primary_payload_id
            })

            return {"final_output": weapon_obj.model_dump(), "generation_history": state["generation_history"]}
        except Exception as e:
            err_msg = f"[Crafting Node] {e}"
            print(err_msg)
            return {
                "final_output": None,
                "is_valid": False,
                "validation_errors": err_msg
            }
    """
    TODO: try to have a new method, instead of let weapon_crafter regenerate everything,
     only let it correct the attributes with issues to save token and accelerate the pipeline
    """


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