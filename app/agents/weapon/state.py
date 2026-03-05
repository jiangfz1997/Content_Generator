from typing import TypedDict, Dict, Any, Optional
class WeaponState(TypedDict):
    biome: str
    level: int
    prompt: Optional[str]
    # 内部私有状态
    retry_count: int
    # 交付给主管的最终产品
    final_output: Optional[Dict[str, Any]]