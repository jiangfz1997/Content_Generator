from langgraph.graph import StateGraph, START, END
from app.core.state import GlobalState
from app.agents.supervisor.graph import supervisor_agent
from app.agents.weapon.graph import weapon_agent


def build_global_workflow():

    builder = StateGraph(GlobalState)

    builder.add_node("supervisor", supervisor_agent.route_node)

    builder.add_node("weapon_department", weapon_agent.graph)

    builder.add_edge(START, "supervisor")

    def route_condition(state: GlobalState):
        return state.get("next_agent", None)

    builder.add_conditional_edges(
        "supervisor",
        route_condition,
        {
            # 如果主管的 next_agent 是 "weapon_department"，就走向武器部门的图
            "weapon_department": "weapon_department",
            # "item_department": "item_department",

            "FINISH": END
        }
    )

    builder.add_edge("weapon_department", END)

    return builder.compile()


global_graph = build_global_workflow()