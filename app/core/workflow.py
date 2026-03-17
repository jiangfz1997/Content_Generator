from app.core.state import GlobalState
from langgraph.graph import StateGraph, START, END

from app.agents.weapon.graph import weapon_agent
from app.agents.designer.graph import designer_agent
from app.agents.reviewer.graph import reviewer_agent
from app.agents.payload_factory.graph import payload_factory_agent
from app.agents.artist.graph import artist_agent
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.services.primitive_registry import primitive_registry
from app.services.weapon_evaluator import WeaponEvaluator


async def payload_validator_node(state: GlobalState) -> dict:
    """
    Pure-code node: validates all payload IDs in final_output against the on-disk library.
    Runs after weapon_designer, before tech_auditor.
    If invalid IDs are found, short-circuits to weapon_patcher with exact fix instructions.
    """
    final_weapon = state.get("final_output") or {}
    abilities = final_weapon.get("abilities") or {}
    used = (
        (abilities.get("on_hit") or []) +
        (abilities.get("on_attack") or []) +
        (abilities.get("on_equip") or [])
    )

    known = set(primitive_registry.get_all_payloads().keys())
    invalid = [p for p in used if p and p not in known]

    if invalid:
        feedback = (
            f"CRITICAL — payload IDs do not exist in the library: {invalid}. "
            f"You MUST replace every invalid ID with a valid one from this list: {sorted(known)}. "
            "Do NOT invent new names. Copy exactly from the list above."
        )
        print(f"⛔ [PayloadValidator] Invalid IDs detected: {invalid}")
        return {"payload_valid": False, "is_final_passed": False, "tech_feedback": feedback}

    print(f"✅ [PayloadValidator] All payload IDs valid: {[p for p in used if p]}")
    return {"payload_valid": True}


async def db_retrieval_node(state: GlobalState):
    """Pipeline 入口节点：拉取全库摘要 + 相近武器（同 biome，按 level 距离排序）。"""
    print("[DB Retrieval] 正在从数据库加载历史武器摘要...")
    summaries = await weapon_mongo_service.get_all_summaries()
    similar = await weapon_mongo_service.get_similar_weapons(
        biome=state.get("biome", ""),
        level=state.get("level", 1),
    )
    print(f"[DB Retrieval] 全库 {len(summaries)} 把，相近 {len(similar)} 把 (biome={state.get('biome')}, lv{state.get('level')})。")
    return {"reference_weapons": summaries, "similar_weapons": similar}


async def power_budget_node(state: GlobalState) -> dict:
    """Pure-math node: evaluates weapon PowerScore and auto-scales base_damage to fit world_level budget."""
    weapon      = state.get("final_output") or {}
    world_level = state.get("world_level") or 1

    updated_weapon, score, budget = WeaponEvaluator.auto_scale(weapon, world_level)
    print(f"[PowerBudget] world_level={world_level} | budget={budget} | score={score}")
    return {"final_output": updated_weapon, "power_score": score}


def build_smart_workflow():
    builder = StateGraph(GlobalState)

    # 1. 注册所有节点
    builder.add_node("db_retrieval", db_retrieval_node)
    builder.add_node("designer", designer_agent.planning_node)
    builder.add_node("concept_reviewer", reviewer_agent.idea_audit_node)  # 极速审 Idea
    builder.add_node("weapon_designer", weapon_agent.crafting_node)  # 昂贵的 JSON 生成
    builder.add_node("weapon_patcher", weapon_agent.patch_node)       # 外科手术修复
    builder.add_node("tech_auditor", reviewer_agent.tech_audit_node)  # 终审数值
    builder.add_node("payload_factory", payload_factory_agent.generate_node)  # 按需生成新 Payload
    builder.add_node("forge_fork", lambda state: {})                   # 并行分叉点
    builder.add_node("artist", artist_agent.generate_icon_node)        # 图标生成（并行）
    builder.add_node("payload_validator", payload_validator_node)      # 代码级 payload ID 校验
    builder.add_node("power_budget", power_budget_node)               # 数学级战力评估 + auto-scale

    # 2. 第一阶段：DB 检索 -> 策划出草案 -> 立刻过审
    builder.add_edge(START, "db_retrieval")
    builder.add_edge("db_retrieval", "designer")
    builder.add_edge("designer", "concept_reviewer")

    # 🌟 闸机 1：Idea 行不行？
    def idea_gatekeeper(state: GlobalState):
        if not state.get("is_idea_passed"):
            retries = state.get("retry_count", 0)
            if retries >= 2:
                print(f"⚠️ [Idea 拒稿] 已重试 {retries} 次，携带反馈强制进入武器生成阶段。理由: {state.get('idea_feedback')}")
                return "weapon_designer"
            print(f"🔁 [Idea 拒稿] 第 {retries + 1} 次返工，反馈: {state.get('idea_feedback')}")
            return "designer"

        # Idea passed — check if designer requested a new payload
        concept = state.get("design_concept", {})
        if isinstance(concept, dict) and concept.get("needs_new_payload"):
            print(f"🏭 [Payload Factory] 设计师请求新 Payload: {concept.get('new_payload_spec', {}).get('id', '?')}")
            return "payload_factory"

        print("✅ [Idea 过审] -> 分叉：weapon_designer ∥ artist。")
        return "forge_fork"

    # 在 idea 审完之后，决定走向
    builder.add_conditional_edges("concept_reviewer", idea_gatekeeper, {
        "designer": "designer",
        "payload_factory": "payload_factory",
        "forge_fork": "forge_fork",
    })

    # payload factory 完成后也走 forge_fork（artist 同样并行）
    builder.add_edge("payload_factory", "forge_fork")

    # forge_fork 扇出：weapon_designer 和 artist 并行
    builder.add_edge("forge_fork", "weapon_designer")
    builder.add_edge("forge_fork", "artist")

    # 3. 第二阶段：weapon_designer → payload_validator（代码校验）→ tech_auditor / patcher
    builder.add_edge("weapon_designer", "payload_validator")

    def payload_validator_gate(state: GlobalState) -> str:
        if state.get("payload_valid") is False:
            print("💉 [PayloadValidator] 路由至 weapon_patcher 修复非法 payload ID")
            return "weapon_patcher"
        return "tech_auditor"

    builder.add_conditional_edges("payload_validator", payload_validator_gate, {
        "weapon_patcher": "weapon_patcher",
        "tech_auditor": "tech_auditor",
    })

    # 🌟 闸机 2：JSON 数值行不行？
    def tech_gatekeeper(state: GlobalState):
        if not state.get("is_final_passed"):
            attempts = state.get("audit_attempts", 0)
            if attempts >= 3:
                print(f"⚠️ [数值拒稿] 已修复 {attempts} 次，强制放行。理由: {state.get('tech_feedback')}")
                return "power_budget"
            print(f"💉 [数值拒稿] 第 {attempts} 次，启动外科手术修复。反馈: {state.get('tech_feedback')}")
            return "weapon_patcher"

        print("🎉 [终审过关] -> 战力评估后发送给 Unity！")
        return "power_budget"

    # 在 tech 审完之后，决定是否结束
    builder.add_conditional_edges("tech_auditor", tech_gatekeeper, {
        "weapon_patcher": "weapon_patcher",
        "power_budget": "power_budget",
    })

    builder.add_edge("power_budget", END)

    # patch 完成后先走 payload_validator 二次校验，再进 tech_auditor
    builder.add_edge("weapon_patcher", "payload_validator")

    return builder.compile()

global_graph = build_smart_workflow()