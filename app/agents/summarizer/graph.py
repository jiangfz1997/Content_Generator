import json

from langchain_core.prompts import load_prompt

from app.core.config import settings
from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.services.primitive_registery import primitive_registry
from app.utils.callbacks import AgentConsoleCallback
from app.utils.inject_prompts import inject_prompts
from app.websocket.handlers import llm_service


from pydantic import BaseModel, Field
from typing import List, Dict

# --- Step 1: 原子文档模型 ---
class PrimitiveDoc(BaseModel):
    id: str = Field(description="Primitive ID, e.g., OP_APPLY_FORCE")
    function: str = Field(description="One brief sentence on what it does.")
    # 🌟 加回参数逻辑，但严格限制描述
    params_logic: str = Field(description="A single sentence summarizing the core parameters.")

class PrimitiveManual(BaseModel):
    # 不用 default_factory，只要 AI 不截断，它一定会老老实实输出这个 List
    primitives: List[PrimitiveDoc] = Field(description="List of extracted primitives")
    motions: List[PrimitiveDoc] = Field(description="List of extracted motion primitives")

# --- Step 2: 最终引擎手册 ---
class PayloadTacticalDoc(BaseModel):
    id: str = Field(description="Payload ID")
    combination_logic: str = Field(description="How it works by combining primitives")
    tactical_intent: str = Field(description="Description of Tactical Intent")

class FinalEngineManual(BaseModel):
    primitive_summary: str = Field(description="Primitive Summary")
    payload_catalog: List[PayloadTacticalDoc]


class SummarizerAgent:
    def __init__(self):
        # 1. 准备两套 Prompt
        self.primitive_prompt = load_prompt(settings.PROMPTS_DIR / "primitive_desc.yaml")
        self.payload_prompt = load_prompt(settings.PROMPTS_DIR / "payload_desc.yaml")
        inject_prompts(GLOBAL_DESIGN_CONSTITUTION, self.primitive_prompt)
        inject_prompts(GLOBAL_DESIGN_CONSTITUTION, self.payload_prompt)

        # 2. 定义两套 LLM 链
        self.primitive_chain = self.primitive_prompt | llm_service.model.with_structured_output(PrimitiveManual)
        self.payload_chain = self.payload_prompt | llm_service.model.with_structured_output(FinalEngineManual)

    async def summarize_engine(self) -> tuple[FinalEngineManual, str]:
        # --- 第一步：解析 Primitives ---
        raw_primitives_md = primitive_registry.get_primitives_schema()
        raw_motions_md = primitive_registry.get_motions_schema()

        # 也可以包含 motions 以便完整理解
        print("[Summarizer] Analyzing Primitive and Motion Schemas...")
        primitive_manual: PrimitiveManual = await self.primitive_chain.ainvoke({
            "raw_primitives": raw_primitives_md,
            "raw_motions": raw_motions_md
        },
        config = {"callbacks": [AgentConsoleCallback(agent_name="SummarizerAgent")]},)

        # --- 第二步：作为上下文解析 Payloads ---
        raw_payloads_dict = primitive_registry.get_all_payloads()
        prim_str = "\n".join(
            [f"- {p.id}: {p.function} (Params: {p.params_logic})" for p in primitive_manual.primitives])
        motion_str = "\n".join([f"- {m.id}: {m.function} (Params: {m.params_logic})" for m in primitive_manual.motions])
        # 构造给 Payload Chain 使用的上下文
        # 我们把 Primitive 和 Motion 的总结拼在一起
        manual_str = (
            "### Atomic Capabilities (Index):\n"
            f"{prim_str}\n\n"
            "### Motion Capabilities (Index):\n"
            f"{motion_str}"
        )


        # --- Step 4: 最终合成手册 ---
        print(f"[Summarizer] Synthesizing tactical manual for {len(raw_payloads_dict)} payloads...")
        final_manual: FinalEngineManual = await self.payload_chain.ainvoke({
            "primitive_manual": manual_str,
            "raw_payloads": json.dumps(raw_payloads_dict, ensure_ascii=False)
        },
        config={"callbacks": [AgentConsoleCallback(agent_name="SummarizerAgent")]},)

        return final_manual, manual_str


summarizer_agent = SummarizerAgent()