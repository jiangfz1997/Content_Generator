from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectileDocument(BaseModel):
    id: str
    session_id: str = "SYSTEM"
    is_preset: bool = True
    content: dict                      # full projectile JSON verbatim
    icon: Optional[str] = None         # selected sprite filename
    shader_color: Optional[dict] = None  # {"r": float, "g": float, "b": float}
    last_synced: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        return self.model_dump()
