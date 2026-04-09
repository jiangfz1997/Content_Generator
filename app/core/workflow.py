import hashlib
import json

from app.core.state import GlobalState
from app.core.config import settings
from langgraph.graph import StateGraph, START, END

from app.agents.weapon.graph import weapon_agent
from app.agents.designer.graph import designer_agent
from app.agents.reviewer.graph import reviewer_agent
from app.agents.payload_factory.graph import payload_factory_agent
from app.agents.projectile_factory.graph import projectile_factory_agent
from app.agents.artist.graph import artist_agent
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.services.primitive_registry import primitive_registry
from app.services.weapon_evaluator import WeaponEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_input_hash(materials: list, weapons: list, biome: str = "") -> str:
    """Stable md5 over sorted material names + weapon IDs + optional biome."""
    mat_keys = sorted(m.get("itemName", m.get("id", "")) for m in (materials or []))
    wpn_keys = sorted(w.get("id", "") for w in (weapons or []))
    key_obj: dict = {"materials": mat_keys, "weapons": wpn_keys}
    if biome:
        key_obj["biome"] = biome
    return hashlib.md5(json.dumps(key_obj, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pure-code nodes (shared across all workflow modes)
# ---------------------------------------------------------------------------

async def input_cache_node(state: GlobalState) -> dict:
    """
    Pre-designer cache: if SKIP_INPUT_CACHE is False, computes a hash from
    materials + weapons + (optional) biome and checks whether we already have a
    weapon for this combination.  On hit, loads the cached weapon + runs artist,
    then routes to cache_power_budget (same alias used by the post-designer cache).
    On miss, stores the hash in state for later persistence.
    """
    materials = state.get("materials") or []
    weapons   = state.get("weapons")   or []
    biome     = state.get("biome")     or ""

    input_hash = _compute_input_hash(materials, weapons, biome)

    if settings.SKIP_INPUT_CACHE:
        return {"is_input_cache_hit": False, "input_hash": input_hash}

    cached = await weapon_mongo_service.find_by_input_hash(input_hash, state.get("session_id", ""))
    if not cached:
        print(f"[InputCache] miss (hash={input_hash[:8]}…)")
        return {"is_input_cache_hit": False, "input_hash": input_hash}

    print(f"🎯 [InputCache] hit: {cached.get('id')} (hash={input_hash[:8]}…) — skipping designer")
    artist_result = {}
    try:
        artist_result = await artist_agent.generate_icon_node({**state, "final_output": cached})
    except Exception as e:
        print(f"[InputCache] Artist failed (non-blocking): {e}")
    return {"final_output": cached, "is_input_cache_hit": True, "input_hash": input_hash, **artist_result}


async def payload_validator_node(state: GlobalState) -> dict:
    """
    Pure-code node: validates all payload IDs in final_output against the on-disk library.
    If invalid IDs are found, short-circuits to weapon_patcher with exact fix instructions.
    """
    final_weapon = state.get("final_output") or {}
    abilities = final_weapon.get("abilities") or {}
    used = (
        (abilities.get("on_hit") or []) +
        (abilities.get("on_attack") or []) +
        (abilities.get("on_equip") or [])
    )

    _ENGINE_BUILTIN_PAYLOADS = {"payload_shoot_generic"}
    known = set(primitive_registry.get_all_payloads().keys()) | _ENGINE_BUILTIN_PAYLOADS
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
    """Entry node: fetch all weapon summaries + similar weapons from DB."""
    print("[DB Retrieval] Loading weapon history from DB...")
    summaries = await weapon_mongo_service.get_all_summaries()
    similar = await weapon_mongo_service.get_similar_weapons(
        biome=state.get("biome", ""),
        level=state.get("level", 1),
    )
    print(f"[DB Retrieval] Total={len(summaries)} weapons, similar={len(similar)} (biome={state.get('biome')}, lv{state.get('level')})")
    return {"reference_weapons": summaries[:20], "similar_weapons": similar}


async def power_budget_node(state: GlobalState) -> dict:
    """Pure-math node: evaluates weapon PowerScore and auto-scales base_damage."""
    weapon      = state.get("final_output") or {}
    world_level = state.get("world_level") or 1
    updated_weapon, score, budget = WeaponEvaluator.auto_scale(weapon, world_level)
    print(f"[PowerBudget] world_level={world_level} | budget={budget} | score={score}")
    return {"final_output": updated_weapon, "power_score": score}


async def cache_check_node(state: GlobalState) -> dict:
    """
    Looks up whether a weapon with the same payload+projectile combination already exists
    in the DB for this biome.  On hit: loads the cached weapon and runs artist inline,
    then routes to cache_power_budget (skips all generation nodes).
    On miss: sets is_cache_hit=False so the normal fork takes over.
    """
    concept  = state.get("design_concept") or {}
    payload_ids    = concept.get("chosen_payload_ids") or []
    projectile_id  = concept.get("chosen_projectile_id")
    biome          = state.get("biome", "")

    cached = await weapon_mongo_service.find_by_combination(
        biome=biome,
        payload_ids=payload_ids,
        projectile_id=projectile_id,
        session_id=state.get("session_id"),
    )

    if not cached:
        print(f"[CacheCheck] miss — biome={biome}, payloads={payload_ids}, proj={projectile_id}")
        return {"is_cache_hit": False}

    print(f"🎯 [CacheCheck] hit: {cached.get('id')} — skipping generation, adjusting power budget")

    # Run artist inline so the response has a fresh icon (uses design_concept for shape/theme)
    artist_result = {}
    try:
        artist_result = await artist_agent.generate_icon_node({**state, "final_output": cached})
    except Exception as e:
        print(f"[CacheCheck] Artist failed (non-blocking): {e}")

    return {"final_output": cached, "is_cache_hit": True, **artist_result}


# ---------------------------------------------------------------------------
# Shared gatekeeper factories (return closures so each build gets its own)
# ---------------------------------------------------------------------------

def _make_idea_gatekeeper(after_pass_target: str):
    """Returns idea_gatekeeper that routes to after_pass_target on success."""
    def idea_gatekeeper(state: GlobalState) -> str:
        if not state.get("is_idea_passed"):
            retries = state.get("retry_count", 0)
            if retries >= 2:
                print(f"⚠️ [IdeaGate] Retried {retries} times, forcing pass. Reason: {state.get('idea_feedback')}")
                return after_pass_target
            print(f"🔁 [IdeaGate] Retry #{retries + 1}, feedback: {state.get('idea_feedback')}")
            return "designer"
        print(f"✅ [IdeaGate] passed -> {after_pass_target}")
        return after_pass_target
    return idea_gatekeeper


def _make_payload_validator_gate(patcher_target: str = "weapon_patcher"):
    def payload_validator_gate(state: GlobalState) -> str:
        if state.get("payload_valid") is False:
            print(f"💉 [PayloadValidator] routing to {patcher_target} to fix invalid payload IDs")
            return patcher_target
        if settings.SKIP_TECH_AUDIT:
            print("⚡ [Workflow] SKIP_TECH_AUDIT=True — tech_auditor skipped")
            return "power_budget"
        return "tech_auditor"
    return payload_validator_gate


def _make_tech_gatekeeper():
    def tech_gatekeeper(state: GlobalState) -> str:
        if not state.get("is_final_passed"):
            attempts = state.get("audit_attempts", 0)
            if attempts >= 3:
                print(f"⚠️ [TechGate] Fixed {attempts} times, forcing pass. Reason: {state.get('tech_feedback')}")
                return "power_budget"
            print(f"💉 [TechGate] Attempt #{attempts}, triggering surgical patch. Feedback: {state.get('tech_feedback')}")
            return "weapon_patcher"
        print("🎉 [TechGate] passed — power budget next, then send to Unity")
        return "power_budget"
    return tech_gatekeeper


def _add_base_nodes(builder: StateGraph) -> None:
    """Register nodes that exist in every workflow mode."""
    builder.add_node("db_retrieval",       db_retrieval_node)
    builder.add_node("input_cache",        input_cache_node)
    builder.add_node("designer",           designer_agent.planning_node)
    builder.add_node("concept_reviewer",   reviewer_agent.idea_audit_node)
    builder.add_node("cache_check",        cache_check_node)
    builder.add_node("cache_power_budget", power_budget_node)   # alias: hit path only → END directly
    builder.add_node("weapon_designer",    weapon_agent.crafting_node)
    builder.add_node("weapon_patcher",     weapon_agent.patch_node)
    builder.add_node("tech_auditor",       reviewer_agent.tech_audit_node)
    builder.add_node("payload_factory",    payload_factory_agent.generate_node)
    builder.add_node("projectile_factory", projectile_factory_agent.generate_node)
    builder.add_node("artist",             artist_agent.generate_icon_node)
    builder.add_node("payload_validator",  payload_validator_node)
    builder.add_node("power_budget",       power_budget_node)


def _add_entry(builder: StateGraph, miss_fork: str) -> None:
    """
    Wire START → db_retrieval → input_cache → designer → concept_reviewer → cache_check.
    Two early-exit paths both lead to cache_power_budget → END:
      - input_cache hit  (same materials+weapons+biome seen before)
      - cache_check hit  (same payload+projectile combination in same biome)
    """
    builder.add_edge(START, "db_retrieval")
    builder.add_edge("db_retrieval", "input_cache")

    def input_cache_route(state: GlobalState) -> str:
        if state.get("is_input_cache_hit"):
            print("🎯 [InputCacheRoute] hit → cache_power_budget")
            return "cache_power_budget"
        return "designer"

    builder.add_conditional_edges("input_cache", input_cache_route,
                                  {"cache_power_budget": "cache_power_budget", "designer": "designer"})

    if settings.SKIP_IDEA_AUDIT:
        print("⚡ [Workflow] SKIP_IDEA_AUDIT=True — concept_reviewer skipped")
        builder.add_edge("designer", "cache_check")
    else:
        builder.add_edge("designer", "concept_reviewer")
        gk = _make_idea_gatekeeper("cache_check")
        builder.add_conditional_edges("concept_reviewer", gk,
                                      {"designer": "designer", "cache_check": "cache_check"})

    def cache_route(state: GlobalState) -> str:
        if state.get("is_cache_hit"):
            print("🎯 [CacheRoute] hit → cache_power_budget")
            return "cache_power_budget"
        return miss_fork

    builder.add_conditional_edges("cache_check", cache_route,
                                  {"cache_power_budget": "cache_power_budget", miss_fork: miss_fork})
    builder.add_edge("cache_power_budget", END)


def _add_weapon_audit_chain(builder: StateGraph,
                             entry: str,
                             patcher_loop_target: str = "payload_validator") -> None:
    """
    Wire the weapon audit loop: entry → payload_validator → tech_auditor/patcher → power_budget.
    patcher_loop_target: node weapon_patcher sends back to (allows split in full_parallel mode).
    """
    builder.add_edge(entry, "payload_validator")

    pv_gate = _make_payload_validator_gate(patcher_target="weapon_patcher")
    builder.add_conditional_edges("payload_validator", pv_gate, {
        "weapon_patcher": "weapon_patcher",
        "tech_auditor":   "tech_auditor",
        "power_budget":   "power_budget",
    })

    tg = _make_tech_gatekeeper()
    builder.add_conditional_edges("tech_auditor", tg, {
        "weapon_patcher": "weapon_patcher",
        "power_budget":   "power_budget",
    })

    builder.add_edge("weapon_patcher", patcher_loop_target)


# ===========================================================================
# Mode 1 — SERIAL
# ===========================================================================
#
#   db_retrieval → designer → concept_reviewer
#                                   ↓ (gatekeeper)
#               [payload_factory] → [projectile_factory] → weapon_designer
#                                                                ↓
#                                          payload_validator ↔ patcher loop
#                                                                ↓
#                                                         power_budget → artist → END
# ===========================================================================

def build_serial_workflow() -> StateGraph:
    builder = StateGraph(GlobalState)
    _add_base_nodes(builder)

    # Serial mode: no extra join nodes needed
    first_fork = "serial_factory_gate"
    builder.add_node("serial_factory_gate", lambda state: {})  # passthrough, routing done below
    _add_entry(builder, first_fork)

    # Route: needs payload → payload_factory; needs projectile → projectile_factory; else → weapon_designer
    def serial_factory_route(state: GlobalState) -> str:
        concept = state.get("design_concept") or {}
        if concept.get("needs_new_payload"):
            print(f"🏭 [Serial] new payload: {concept.get('new_payload_spec', {}).get('id', '?')}")
            return "payload_factory"
        if concept.get("needs_new_projectile"):
            print(f"🚀 [Serial] new projectile: {concept.get('new_projectile_spec', {}).get('id', '?')}")
            return "projectile_factory"
        return "weapon_designer"

    builder.add_conditional_edges("serial_factory_gate", serial_factory_route, {
        "payload_factory":    "payload_factory",
        "projectile_factory": "projectile_factory",
        "weapon_designer":    "weapon_designer",
    })

    # payload_factory → (optional projectile_factory) → weapon_designer
    def after_payload_factory(state: GlobalState) -> str:
        concept = state.get("design_concept") or {}
        if concept.get("needs_new_projectile"):
            print(f"🚀 [Serial] payload done, continuing to projectile: {concept.get('new_projectile_spec', {}).get('id', '?')}")
            return "projectile_factory"
        return "weapon_designer"

    builder.add_conditional_edges("payload_factory", after_payload_factory, {
        "projectile_factory": "projectile_factory",
        "weapon_designer":    "weapon_designer",
    })
    builder.add_edge("projectile_factory", "weapon_designer")

    # Weapon audit chain: weapon_designer → payload_validator → ... → power_budget
    _add_weapon_audit_chain(builder, entry="weapon_designer")

    # Artist runs last (after power_budget)
    builder.add_edge("power_budget", "artist")
    builder.add_edge("artist", END)

    print("🔧 [Workflow] Mode=serial | artist sequential | factories sequential")
    return builder.compile()


# ===========================================================================
# Mode 2 — FACTORY_PARALLEL
# ===========================================================================
#
#   db_retrieval → designer → concept_reviewer
#                                   ↓ (gatekeeper)
#                [factory_fork] → payload_factory ──┐
#                              → projectile_factory ─┴→ factory_join → forge_fork
#                                                                           ├── weapon_designer → audit chain
#                                                                           └── artist ──────────── merge_node ← power_budget
#                                                                                                       ↓
#                                                                                                      END
# ===========================================================================

def build_factory_parallel_workflow() -> StateGraph:
    builder = StateGraph(GlobalState)
    _add_base_nodes(builder)

    builder.add_node("factory_fork", lambda state: {})   # fan-out: payload || projectile
    builder.add_node("factory_join", lambda state: {})   # fan-in: wait for both factories
    builder.add_node("forge_fork",   lambda state: {})   # fan-out: weapon_designer || artist
    builder.add_node("merge_node",   lambda state: {})   # fan-in: wait for power_budget + artist

    # Entry: if factories needed go to factory_fork, else skip to forge_fork
    def factory_parallel_route(state: GlobalState) -> str:
        concept = state.get("design_concept") or {}
        if concept.get("needs_new_payload") or concept.get("needs_new_projectile"):
            pids = []
            if concept.get("needs_new_payload"):
                pids.append(f"payload={concept.get('new_payload_spec', {}).get('id', '?')}")
            if concept.get("needs_new_projectile"):
                pids.append(f"projectile={concept.get('new_projectile_spec', {}).get('id', '?')}")
            print(f"🏭 [FactoryParallel] parallel factories: {', '.join(pids)}")
            return "factory_fork"
        return "forge_fork"

    first_fork = "fp_concept_gate"
    builder.add_node("fp_concept_gate", lambda state: {})
    _add_entry(builder, first_fork)
    builder.add_conditional_edges("fp_concept_gate", factory_parallel_route, {
        "factory_fork": "factory_fork",
        "forge_fork":   "forge_fork",
    })

    # factory_fork → payload_factory || projectile_factory → factory_join → forge_fork
    builder.add_edge("factory_fork", "payload_factory")
    builder.add_edge("factory_fork", "projectile_factory")
    builder.add_edge("payload_factory",    "factory_join")
    builder.add_edge("projectile_factory", "factory_join")
    builder.add_edge("factory_join", "forge_fork")

    # forge_fork → weapon_designer || artist (parallel)
    builder.add_edge("forge_fork", "weapon_designer")
    builder.add_edge("forge_fork", "artist")

    # weapon audit chain
    _add_weapon_audit_chain(builder, entry="weapon_designer")

    # merge: power_budget + artist → merge_node → END
    builder.add_edge("power_budget", "merge_node")
    builder.add_edge("artist",       "merge_node")
    builder.add_edge("merge_node", END)

    print("🔧 [Workflow] Mode=factory_parallel | factories parallel | weapon+artist parallel")
    return builder.compile()


# ===========================================================================
# Mode 3 — FULL_PARALLEL
# ===========================================================================
#
#   db_retrieval → designer → concept_reviewer
#                                   ↓ (gatekeeper)
#                             concept_fork ──────────────────────── artist ──────────────┐
#                                ├── payload_factory ──┐                                  │
#                                ├── projectile_factory┴─ factory_join ──┐               │
#                                └── weapon_designer ──────────── pre_validator_join      │
#                                                                        ↓                │
#                                                              payload_validator          │
#                                                              ↓         ↑(retry)         │
#                                                        tech_auditor  patcher            │
#                                                              ↓                          │
#                                                        power_budget ──── merge_node ────┘
#                                                                              ↓
#                                                                             END
#
# Note: weapon_patcher loops back to payload_validator directly.
# pre_validator_join has exactly 2 incoming edges (factory_join + weapon_designer).
# payload_validator has 2 incoming edges (pre_validator_join + weapon_patcher) but they
# are never active in the same superstep — LangGraph's superstep model handles this safely.
# ===========================================================================

def build_full_parallel_workflow() -> StateGraph:
    builder = StateGraph(GlobalState)
    _add_base_nodes(builder)

    builder.add_node("concept_fork",        lambda state: {})  # fan-out: 4 parallel paths
    builder.add_node("factory_join",        lambda state: {})  # fan-in: payload + projectile done
    builder.add_node("pre_validator_join",  lambda state: {})  # fan-in: factory_join + weapon_designer done
    builder.add_node("merge_node",          lambda state: {})  # fan-in: power_budget + artist done

    _add_entry(builder, "concept_fork")

    # concept_fork → 4 parallel paths
    builder.add_edge("concept_fork", "payload_factory")
    builder.add_edge("concept_fork", "projectile_factory")
    builder.add_edge("concept_fork", "weapon_designer")
    builder.add_edge("concept_fork", "artist")

    # Two factories → factory_join, then factory_join + weapon_designer → pre_validator_join
    builder.add_edge("payload_factory",    "factory_join")
    builder.add_edge("projectile_factory", "factory_join")
    builder.add_edge("factory_join",    "pre_validator_join")
    builder.add_edge("weapon_designer", "pre_validator_join")

    # Weapon audit chain: pre_validator_join → payload_validator → ... → power_budget
    # weapon_patcher loops back to payload_validator directly (sequential retry, not a parallel join)
    _add_weapon_audit_chain(builder, entry="pre_validator_join")

    # merge: power_budget + artist → merge_node → END
    builder.add_edge("power_budget", "merge_node")
    builder.add_edge("artist",       "merge_node")
    builder.add_edge("merge_node", END)

    print("🔧 [Workflow] Mode=full_parallel | full parallel from concept_fork")
    return builder.compile()


# ---------------------------------------------------------------------------
# Build and export
# ---------------------------------------------------------------------------

_BUILDERS = {
    "serial":            build_serial_workflow,
    "factory_parallel":  build_factory_parallel_workflow,
    "full_parallel":     build_full_parallel_workflow,
}

_mode = settings.WORKFLOW_MODE
if _mode not in _BUILDERS:
    print(f"⚠️ [Workflow] Unknown WORKFLOW_MODE={_mode!r}, falling back to full_parallel")
    _mode = "full_parallel"

global_graph = _BUILDERS[_mode]()
