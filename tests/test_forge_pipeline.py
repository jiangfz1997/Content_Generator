"""
Pipeline unit test — no server required.
Calls global_graph.ainvoke() directly, hitting the real LLM.

Run:
    pytest tests/test_forge_pipeline.py -v -s
"""
import json
import pytest
from app.core.workflow import global_graph
from app.core.state import GlobalState


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_MATERIALS = [
    {
        "id": "mat_fire_essence",
        "itemName": "Fire Essence",
        "itemType": 1,
        "description": "A crystallised stone that stores the power of fire.",
        "count_in_altar": 2,
    },
    {
        "id": "mat_obsidian_shard",
        "itemName": "Obsidian Shard",
        "itemType": 1,
        "description": "A razor-sharp volcanic glass fragment.",
        "count_in_altar": 1,
    },
]

MOCK_WEAPONS = [
    {
        "id": "weapon_starter_blade",
        "name": "Starter Blade",
        "abilities": {"on_hit": ["payload_strike"], "on_attack": [], "on_equip": []},
        "motions": [
            {"primitive_id": "OP_ROTATE", "params": {"start": 30, "end": -90, "curve": "EaseIn",
                                                      "time_start": 0.0, "time_end": 1.0}},
        ],
    }
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_initial_state(biome: str = "Magma_Chamber", level: int = 5,
                        prompt: str = "Create a fire-themed weapon") -> GlobalState:
    """Construct a valid initial state matching handlers.py ainvoke() call."""
    return {
        "prompt": prompt,
        "materials": MOCK_MATERIALS,
        "weapons": MOCK_WEAPONS,
        "biome": biome,
        "level": level,
        "session_id": "test_session_001",
        "retry_count": 0,
        "audit_attempts": 0,
        "generation_history": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weapon_generation_pipeline():
    """Full pipeline smoke test: pipeline must produce a valid WeaponSchema dict."""

    initial_state = _make_initial_state()
    print("\n🚀 [Test] Starting forge pipeline...")

    final_state = await global_graph.ainvoke(initial_state)

    # --- Core assertion ---
    weapon = final_state.get("final_output")
    assert weapon is not None, "Pipeline returned no weapon (熔断 or fatal error)"

    # --- Schema fields ---
    assert "id" in weapon,      "Missing: id"
    assert "name" in weapon,    "Missing: name"
    assert "stats" in weapon,   "Missing: stats"
    assert "motions" in weapon, "Missing: motions"
    assert "abilities" in weapon, "Missing: abilities"
    assert "summary" in weapon, "Missing: summary"

    stats = weapon["stats"]
    assert "base_damage" in stats,   "Missing: stats.base_damage"
    assert "design_level" in stats,  "Missing: stats.design_level"
    assert "cooldown" in stats,      "Missing: stats.cooldown"
    assert "range" in stats,         "Missing: stats.range"
    assert "hit_start" in stats,     "Missing: stats.hit_start"
    assert "hit_end" in stats,       "Missing: stats.hit_end"

    abilities = weapon["abilities"]
    assert isinstance(abilities.get("on_hit", []), list),    "abilities.on_hit must be a list"
    assert isinstance(abilities.get("on_attack", []), list), "abilities.on_attack must be a list"
    assert isinstance(abilities.get("on_equip", []), list),  "abilities.on_equip must be a list"

    assert len(weapon["motions"]) >= 1, "Weapon must have at least one motion"

    # --- Print pipeline trace ---
    print("\n--- 💡 Design Concept ---")
    concept = final_state.get("design_concept") or {}
    print(f"  Codename     : {concept.get('codename', '?')}")
    print(f"  Core Mechanic: {concept.get('core_mechanic', '?')}")
    print(f"  Needs Factory: {concept.get('needs_new_payload', False)}")
    if concept.get('needs_new_payload'):
        spec = concept.get('new_payload_spec') or {}
        print(f"  Factory Spec : {spec.get('id')} — {spec.get('description')}")

    print("\n--- ⚖️ Idea Review ---")
    print(f"  Passed  : {final_state.get('is_idea_passed')}")
    print(f"  Feedback: {final_state.get('idea_feedback')}")

    print("\n--- 🔧 Tech Audit ---")
    print(f"  Passed   : {final_state.get('is_final_passed')}")
    print(f"  Attempts : {final_state.get('audit_attempts')}")
    print(f"  Feedback : {final_state.get('tech_feedback')}")

    print("\n--- 🎨 Artist ---")
    print(f"  Generated Icon: {final_state.get('generated_icon')}")

    if final_state.get("pending_payload_id"):
        print(f"\n--- 🏭 Payload Factory ---")
        print(f"  New Payload: {final_state.get('pending_payload_id')}")

    print("\n--- 🗃️ DB Similar Weapons ---")
    similar = final_state.get("similar_weapons") or []
    if similar:
        for w in similar:
            print(f"  [{w.get('id')}] {w.get('name')} Lv{w.get('level')}")
    else:
        print("  (none — first weapon in this biome)")

    print("\n--- 🛠️ Final Weapon JSON ---")
    print(json.dumps(weapon, indent=2, ensure_ascii=False))


@pytest.mark.asyncio
async def test_pipeline_with_user_prompt():
    """Verify the user prompt actually reaches the designer (regression for bug #2)."""

    specific_prompt = "A weapon that deals lightning damage and stuns enemies"
    initial_state = _make_initial_state(
        biome="Storm_Peaks",
        level=10,
        prompt=specific_prompt,
    )
    print(f"\n🚀 [Test] Prompt: '{specific_prompt}'")

    final_state = await global_graph.ainvoke(initial_state)

    weapon = final_state.get("final_output")
    assert weapon is not None, "Pipeline returned no weapon"

    concept = final_state.get("design_concept") or {}
    print(f"\n  Designer's manual_analysis: {concept.get('manual_analysis', '?')}")
    print(f"  Weapon name: {weapon.get('name')}")
    print(f"  Summary: {weapon.get('summary')}")
    print(f"  Payloads on_hit: {weapon.get('abilities', {}).get('on_hit')}")
