from app.core.state import GlobalState
from langgraph.graph import StateGraph, START, END

from app.agents.weapon.graph import weapon_agent
from app.agents.designer.graph import designer_agent
from app.agents.reviewer.graph import reviewer_agent

def build_smart_workflow():
    builder = StateGraph(GlobalState)

    # 1. 注册所有节点
    builder.add_node("designer", designer_agent.planning_node)
    builder.add_node("concept_reviewer", reviewer_agent.idea_audit_node)  # 极速审 Idea
    builder.add_node("weapon_designer", weapon_agent.crafting_node)  # 昂贵的 JSON 生成
    builder.add_node("tech_auditor", reviewer_agent.tech_audit_node)  # 终审数值

    # 2. 第一阶段：策划出草案 -> 立刻过审
    builder.add_edge(START, "designer")
    builder.add_edge("designer", "concept_reviewer")

    # 🌟 闸机 1：Idea 行不行？
    def idea_gatekeeper(state: GlobalState):
        if not state.get("is_idea_passed"):
            print(f"❌ [Idea 拒稿] 理由: {state.get('idea_feedback')} -> 打回策划重写！")
            return "designer"  # 核心：直接打回，根本不触发 weapon_designer

        print("✅ [Idea 过审] -> 发送给技术部生成 JSON。")
        return "weapon_designer"

    # 在 idea 审完之后，决定走向
    builder.add_conditional_edges("concept_reviewer", idea_gatekeeper, {
        "designer": "designer",
        "weapon_designer": "weapon_designer"
    })

    # 3. 第二阶段：技术出 JSON -> 终审
    builder.add_edge("weapon_designer", "tech_auditor")

    # 🌟 闸机 2：JSON 数值行不行？
    def tech_gatekeeper(state: GlobalState):
        if not state.get("is_final_passed"):
            print(f"⚠️ [Tech 拒稿] 理由: {state.get('tech_feedback')} -> 打回技术重调数值！")
            return "weapon_designer"  # 核心：只打回技术部，不需要策划重新想 Idea

        print("🎉 [终审过关] -> 准备发送给 Unity！")
        return END

    # 在 tech 审完之后，决定是否结束
    builder.add_conditional_edges("tech_auditor", tech_gatekeeper, {
        "weapon_designer": "weapon_designer",
        END: END
    })

    return builder.compile()

global_graph = build_smart_workflow()