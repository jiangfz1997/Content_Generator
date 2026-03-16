# app/models/common_types.py
from pydantic import BaseModel, Field
from typing import Literal

# Interpolation curve types
CurveType = Literal["Linear", "EaseIn", "EaseOut", "EaseInOut", "Overshoot", "PingPong", "Loop"]

class Vector2(BaseModel):
    x: float = Field(default=1.0)
    y: float = Field(default=1.0)

class Vector3(BaseModel):
    x: float = Field(default=1.0)
    y: float = Field(default=1.0)
    z: float = Field(default=1.0)