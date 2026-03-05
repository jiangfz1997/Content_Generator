from typing import TypedDict, List, Dict, Any, Optional


class GlobalState(TypedDict):
    prompt: str
    materials: List[str]
    biome: str
    level: int

    next_agent: str

    final_output: Optional[Dict[str, Any]]