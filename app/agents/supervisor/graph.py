from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.prompts import ChatPromptTemplate, load_prompt
from app.services.llm_service import llm_service
from app.core.state import GlobalState
from app.core.config import settings

class RouteDecision(BaseModel):
    next_agent: Literal["weapon_department", "FINISH"] = Field(
        description="Dispatch to the next agent based on need. 'FINISH' means the supervisor thinks no further generation is needed and the current materials/requirements are sufficient."
    )
    reason: str = Field(description="Reason for the routing decision")


class SupervisorAgent:
    def __init__(self):

        prompt_path = settings.PROMPTS_DIR / "supervisor.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Missing prompt asset at: {prompt_path}")

        self.router_llm = llm_service.model.with_structured_output(RouteDecision)

        self.prompt = load_prompt(str(prompt_path), encoding=settings.ENCODING)

        self.chain = self.prompt | self.router_llm

    async def route_node(self, state: GlobalState):
        decision: RouteDecision = await self.chain.ainvoke({
            "materials": ", ".join(state.get("materials", [])),
            "prompt": state.get("prompt", ""),
            "level": state.get("level", 0),
            "biome": state.get("biome", "")
        })

        print(f"[Supervisor] 决定路由至: {decision.next_agent} (理由: {decision.reason})")

        # 将决策更新到状态板中，LangGraph 会根据这个字段决定下一条边
        return {"next_agent": decision.next_agent}


supervisor_agent = SupervisorAgent()