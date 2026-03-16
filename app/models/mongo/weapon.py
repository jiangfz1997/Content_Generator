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

class WeaponDocument(BaseModel):
    id: str = Field(..., description="weapon's  unique ID")
    session_id: str = Field(default="SYSTEM", description="session ID, system means it's a preset weapon not generated from a specific session")
    is_preset: bool = True
    content: WeaponContent
    last_synced: datetime = Field(default_factory=datetime.utcnow)

    # RAG metadata — top-level for cheap projection queries
    biome: Optional[str] = None
    level: Optional[int] = None
    primary_payload: Optional[str] = None
    summary: Optional[str] = None

    def to_mongo(self):
        return self.model_dump(exclude_none=True)