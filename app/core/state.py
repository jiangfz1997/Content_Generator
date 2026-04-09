from typing import TypedDict, List, Dict, Any, Optional


class GlobalState(TypedDict):
    prompt: str
    materials: List[dict]
    weapons: List[dict]
    biome: str
    level: int
    audit_attempts:int
    # next_agent: str

    retry_count: int

    design_concept: Optional[Dict[str, Any]]

    idea_score: Optional[int]
    is_idea_passed: Optional[bool]
    idea_feedback: Optional[str]

    final_output: Optional[Dict[str, Any]]

    is_final_passed: Optional[bool]
    tech_feedback: Optional[str]

    generation_history: Optional[List[Dict[str, Any]]]

    engine_manual: Optional[str]  # cached markdown manual, populated on first load

    session_id: Optional[str]                          # passed in at invocation time
    reference_weapons: Optional[List[Dict[str, Any]]]  # all weapon summaries (for ID uniqueness)
    similar_weapons: Optional[List[Dict[str, Any]]]    # same-biome weapons sorted by level proximity
    pending_payload_ids: Optional[List[str]]            # IDs of newly factory-generated payloads
    pending_projectile_ids: Optional[List[str]]         # IDs of newly factory-generated projectiles
    generated_icon: Optional[str]                      # icon file path produced by artist_node
    generated_icon_b64: Optional[str]                  # base64-encoded PNG for direct WebSocket delivery
    payload_valid: Optional[bool]                      # set by payload_validator_node (code, not LLM)
    world_level: Optional[int]                         # global difficulty from Unity, used for power budget
    power_score: Optional[float]                       # computed by WeaponEvaluator after generation
    is_cache_hit: Optional[bool]                       # True if weapon was found in DB by combination match
    is_input_cache_hit: Optional[bool]                 # True if weapon was found by input hash (pre-designer)
    input_hash: Optional[str]                          # md5 of materials+weapons+biome, set by input_cache_node