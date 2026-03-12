from pydantic import BaseModel, Field
from typing import List, Optional
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


# --- Step 1: 带有思维链 (CoT) 的策划蓝图结构 ---
class DesignBlueprint(BaseModel):
    # 🧠 大脑前额叶：强制先进行战术和材料分析 (放在最前面！)
    manual_analysis: str = Field(
        description="STEP 1: Analyze the Engine Tactical Manual. Which payload best fits the user's request and current biome?(MAX 25 words)")
    material_synergy: str = Field(
        description="STEP 2: Analyze the provided materials. How can they be logically combined to justify the chosen mechanic?(MAX 25 words)")

    # 🦾 运动皮层：真正输出游戏设计数据
    codename: str = Field(description="The thematic name of the weapon")
    visual_manifest: str = Field(description="Visual description of the weapon(MAX 50 words)")
    core_mechanic: str = Field(
        description="Detailed explanation of the gameplay gimmick, explicitly referencing the chosen Payload ID(MAX 50 words)")
    material_logic: str = Field(description="How the materials justify this design(MAX 25 words)")
    lore: str = Field(description="A short flavor text (MAX 25 words)")


class DesignerAgent:
    def __init__(self):
        prompt_path = settings.PROMPTS_DIR / "designer.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        # 绑定带有 CoT 字段的模型
        self.planner_llm = llm_service.model.with_structured_output(DesignBlueprint)

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)
        self.chain = self.prompt | self.planner_llm

    async def planning_node(self, state: GlobalState):
        # 1. 序列化基础物资
        raw_materials = state.get("materials", [])
        materials_full_dump = [json.dumps(m, ensure_ascii=False) for m in raw_materials]

        raw_weapons = state.get("weapons", [])
        weapons_full_dump = [json.dumps(w, ensure_ascii=False) for w in raw_weapons]

        # 2. 🌟 拿取极致压缩的 Markdown 引擎手册 (无 Token 损耗！)
        engine_manual_md = await engine_docs_manager.get_markdown_manual()

        # 3. 🌟 提取历史记忆 (如果你的图逻辑里存了之前造的武器)
        history = state.get("generation_history", [])
        if history:
            history_str = "\n".join([f"- {w['name']} (Core: {w.get('mechanic', 'Unknown')})" for w in history])
        else:
            history_str = "No weapons created yet. You are designing the first one."

        print(f"[Designer] 正在查阅引擎手册，并结合 {state.get('biome')} 环境构思蓝图...")

        # 4. 调用 Chain
        blueprint: DesignBlueprint = await self.chain.ainvoke(
            {
                "materials": "\n---\n".join(materials_full_dump),
                "weapons": "\n---\n".join(weapons_full_dump),
                "prompt": state.get("user_request", "None"),
                "level": state.get("level", 0),
                "biome": state.get("biome", "Unknown"),
                "feedback": state.get("review_feedback", "None"),

                # 🌟 注入新的上下文变量
                "engine_manual": engine_manual_md,
                "past_weapons": history_str
            },
            # 挂载我们在控制台写好的打字机日志钩子
            config={"callbacks": [AgentConsoleCallback(agent_name="DesignerAgent")]}
        )

        print(f"[Designer] 构思完成: {blueprint.codename}")

        # 返回时，推荐使用 pydantic V2 的 model_dump()
        return {"design_concept": blueprint.model_dump()}


# 实例化
designer_agent = DesignerAgent()