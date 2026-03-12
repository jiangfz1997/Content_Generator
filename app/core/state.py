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

    design_concept: str

    idea_score: Optional[int]
    is_idea_passed: Optional[bool]
    idea_feedback: Optional[str]

    final_output: Optional[Dict[str, Any]]

    is_final_passed: Optional[bool]
    tech_feedback: Optional[str]

    generation_history: Optional[List[Dict[str, Any]]]