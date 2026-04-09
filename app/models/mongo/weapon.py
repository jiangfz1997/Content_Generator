from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class WeaponContent(BaseModel):
    id: str
    name: str
    stats: Dict[str, Any]
    motions: List[Dict[str, Any]]
    abilities: Dict[str, Any]
    visual_stats: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    summary: Optional[str] = None

class WeaponDocument(BaseModel):
    id: str = Field(..., description="weapon's  unique ID")
    session_id: str = Field(default="SYSTEM", description="session ID, system means it's a presets weapon not generated from a specific session")
    is_preset: bool = True
    content: WeaponContent
    last_synced: datetime = Field(default_factory=datetime.utcnow)

    # RAG metadata — top-level for cheap projection queries
    biome: Optional[str] = None
    level: Optional[int] = None
    primary_payload: Optional[str] = None
    summary: Optional[str] = None
    generation_time_secs: Optional[float] = None
    node_timings: Optional[Dict[str, float]] = None  # per-node wall-clock seconds
    node_traces:  Optional[Dict[str, Any]]  = None  # per-node {inputs, outputs, duration_secs}
    input_hash: Optional[str] = None                 # md5(sorted materials+weapons+biome) for input-cache lookup
    combination_hash: Optional[str] = None           # md5(sorted payload_ids+projectile_id+biome) for cache_check lookup

    def to_mongo(self):
        return self.model_dump(exclude_none=True)