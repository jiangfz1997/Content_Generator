from app.agents.weapon.state import WeaponState
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.prompts import load_prompt
from app.services.llm_service import llm_service
from app.core.config import settings
from app.models.schemas import WeaponSchema
from app.services.primitive_registery import primitive_registry
from app.utils.formatter import format_registries_for_llm_yaml


class WeaponAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "weapon_crafter.yaml"

        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")
        self.prompt_template = load_prompt(str(prompt_path), encoding=settings.ENCODING)

        # builder = StateGraph(AgentState)
        # builder.add_node("craft_weapon", self.crafting_node)
        # builder.set_entry_point("craft_weapon")
        # builder.add_edge("craft_weapon", END)

        # self.graph = builder.compile()


        self.structured_llm = llm_service.model.with_structured_output(WeaponSchema)

        self.chain = self.prompt_template | self.structured_llm
        self.graph = self._build_graph()
        self.fresh_payloads = None
        self.fresh_primitives = None
        self.fresh_motions = None
        self._load_predefined_data()

    def _build_graph(self):
        """组装武器部的内部工作流"""
        builder = StateGraph(WeaponState)
        builder.add_node("craft_weapon", self.crafting_node)
        builder.set_entry_point("craft_weapon")
        builder.add_edge("craft_weapon", END)
        return builder.compile()

    def _load_predefined_data(self):
        """
        load payloads and primitives from registry
        :return:
        """
        self.fresh_payloads = primitive_registry.get_all_payloads()
        self.fresh_primitives = primitive_registry.get_all_primitives()
        self.fresh_motions = primitive_registry.get_all_motions()


    async def crafting_node(self, state: WeaponState):
        """
        真正的“大脑”执行逻辑
        """
        # 组装 Chain：Prompt + LLM Service
        # 注意：这里直接使用了 llm_service 暴露出的模型实例
        self._load_predefined_data()
        print(f"[Crafting Node] 输入状态: biome={state['biome']}, level={state['level']}")
        # 执行推理
        registry_context = format_registries_for_llm_yaml(
            available_payloads=self.fresh_payloads,
            available_primitives=self.fresh_primitives,
            available_motions=self.fresh_motions,
        )
        weapon_obj: WeaponSchema = await self.chain.ainvoke({
            "biome": state["biome"],
            "level": state["level"],
            "prompt": state.get("prompt", ""),
            **registry_context
        })

        # 更新状态：返回生成的 JSON
        return {"final_output": weapon_obj.model_dump()}

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