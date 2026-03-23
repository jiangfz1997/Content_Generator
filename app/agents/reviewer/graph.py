import json
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.core.state import GlobalState  # 你的状态定义
from app.core.config import settings
from langchain_core.prompts import load_prompt
from app.services.llm_service import llm_service

# 🌟 引入新的极简文档管理器和控制台回调
from app.services.engine_docs_manager import engine_docs_manager
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.utils.callbacks import make_callbacks


# --- Pydantic Schemas ---
class IdeaReviewResult(BaseModel):
    # 🧠 CoT 思考前置
    concept_analysis: Optional[str] = Field(
        default="",
        description="STEP 1: Briefly analyze if the concept fits the biome and materials. MAX 15 words.")

    is_idea_passed: bool = Field(description="True if creative and fits biome. False if generic.")
    idea_feedback: str = Field(description="Constructive feedback for the Planner.")

    @field_validator("concept_analysis", mode="before")
    @classmethod
    def truncate_concept_analysis(cls, v):
        if isinstance(v, str) and len(v) > 200:
            return v[:200]
        return v or ""


class TechAuditResult(BaseModel):
    # 🧠 CoT 思考前置 — Optional，防止 token 溢出导致后续关键字段丢失
    manual_compliance_check: Optional[str] = Field(
        default="",
        description="STEP 1: Are the payload IDs valid? Are motions valid? MAX 15 words.")
    balance_analysis: Optional[str] = Field(
        default="",
        description="STEP 2: Are the stats balanced for this level? MAX 15 words.")

    is_final_passed: bool = Field(
        description="True if stats are balanced, payloads are valid, and it matches the concept.")
    tech_feedback: str = Field(
        description="If False, give exact instructions on what fields to fix. If True, write 'None'.")

    @field_validator("manual_compliance_check", "balance_analysis", mode="before")
    @classmethod
    def truncate_cot_fields(cls, v):
        if isinstance(v, str) and len(v) > 200:
            return v[:200]
        return v or ""

# --- Agent Class ---
class ReviewerAgent:
    def __init__(self):
        # 1. 加载两个不同的 YAML Prompt
        idea_prompt_path = settings.PROMPTS_DIR / "concept_reviewer.yaml"
        tech_prompt_path = settings.PROMPTS_DIR / "tech_auditor.yaml"

        self.idea_prompt = load_prompt(str(idea_prompt_path), encoding=settings.ENCODING)
        self.tech_prompt = load_prompt(str(tech_prompt_path), encoding=settings.ENCODING)

        # 2. 绑定两套不同的结构化输出
        self.idea_llm = llm_service.get_model("concept_reviewer").with_structured_output(IdeaReviewResult)
        self.tech_llm = llm_service.get_model("tech_auditor").with_structured_output(TechAuditResult)

        # 3. 组装两条独立的 Chain
        self.idea_chain = self.idea_prompt | self.idea_llm
        self.tech_chain = self.tech_prompt | self.tech_llm

    # ==========================================
    # 节点 1：创意审核 (接在 Planner 之后)
    # ==========================================
    async def idea_audit_node(self, state: GlobalState):
        materials_dump = json.dumps(state.get("materials", []), ensure_ascii=False)

        result: IdeaReviewResult = await self.idea_chain.ainvoke({
                "biome": state.get("biome", "Unknown"),
                "level": state.get("level", 1),
                "materials": materials_dump,
                "concept": state.get("design_concept", "")
            },
            config={"callbacks": make_callbacks("IdeaAuditor", state.get("session_id", "default"))}
        )


        color = "\033[92m" if result.is_idea_passed else "\033[91m"
        print(f"{color}[Idea Audit] Passed: {result.is_idea_passed} | Feedback: {result.idea_feedback}\033[0m")

        # 返回局部状态更新
        return {
            "is_idea_passed": result.is_idea_passed,
            "idea_feedback": result.idea_feedback,
            "retry_count": state.get("retry_count", 0) + (0 if result.is_idea_passed else 1),
        }

    # ==========================================
    # 节点 2：技术终审 (接在 Weapon Designer 之后)
    # Currently not used in the pipeline
    # ==========================================

    async def tech_audit_node(self, state: GlobalState):
        attempts = state.get("audit_attempts", 0)
        strictness = "MAXIMUM (Strictly follow manual)"
        if attempts == 1:
            strictness = "MODERATE (Allow minor stat offsets)"
        elif attempts >= 2:
            strictness = "LAX (Only fail on critical logic errors)"

        if state.get("engine_manual"):
            engine_manual_md = state["engine_manual"]
        else:
            engine_manual_md = await engine_docs_manager.get_audit_manual()

        final_weapon_data = state.get("final_output") or {}
        weapon_json_str = json.dumps(final_weapon_data, ensure_ascii=False) if final_weapon_data else "{}"
        print("\n[TechAuditor] 正在对照引擎底层手册进行最终校验...")

        result: TechAuditResult = await self.tech_chain.ainvoke({
            "biome": state.get("biome", "Unknown"),
            "level": state.get("level", 1),
            "concept": state.get("design_concept", ""),
            "final_weapon": weapon_json_str,
            "engine_manual": engine_manual_md,
            "strictness_level": strictness,
        },
            config={"callbacks": make_callbacks("TechAuditor", state.get("session_id", "default"))})

        color = "\033[92m" if result.is_final_passed else "\033[91m"
        print(f"{color}[Tech Audit] Passed: {result.is_final_passed} | Feedback: {result.tech_feedback}\033[0m")

        if result.is_final_passed:
            session_id = state.get("session_id", "unknown_session")
            await weapon_mongo_service.save_generated_weapon(
                weapon_data=final_weapon_data,
                session_id=session_id,
                biome=state.get("biome"),
                level=state.get("level"),
            )
            # Local backup
            import json
            try:
                backup_dir = settings.SESSIONS_DIR / session_id / "weapons"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{final_weapon_data.get('id', 'unknown')}.json"
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(final_weapon_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ [Reviewer] 武器本地备份失败 (不影响流程): {e}")

        return {
            "is_final_passed": result.is_final_passed,
            "tech_feedback": result.tech_feedback,
            "audit_attempts": attempts + 1,
        }

reviewer_agent = ReviewerAgent()