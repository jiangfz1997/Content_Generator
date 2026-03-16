from pydantic import BaseModel, Field
from typing import Literal, Union
from typing_extensions import Annotated

from app.models.common_types import *


class ArcParams(BaseModel):
    radius: float = Field(
        description="Orbit radius in world units from the weapon's pivot. "
                    "E.g. 1.5 for a shortsword, 3.0 for a greatsword."
    )
    start_angle: float = Field(
        description="Starting angle in degrees. 0=right, 90=up, 180=left, 270=down."
    )
    end_angle: float = Field(
        description="Ending angle in degrees. Values outside [0,360] produce multi-revolution sweeps."
    )
    curve: CurveType = Field(
        description="'EaseOut': impactful slam. 'EaseInOut': smooth sweep. 'EaseIn': wind-up swing."
    )
    time_start: float = Field(
        default=0.0,
        description="Normalized time [0,1] when this primitive begins within the attack duration."
    )
    time_end: float = Field(
        default=1.0,
        description="Normalized time [0,1] when this primitive ends within the attack duration."
    )


class MoveParams(BaseModel):
    start: Vector2 = Field(description="Starting local offset from pivot: {x, y}.")
    end: Vector2 = Field(description="Target local offset the weapon moves toward: {x, y}.")
    curve: CurveType = Field(
        description="'EaseOut': fast-start slow-end (swings). 'PingPong': out-and-back (thrusts). "
                    "'Overshoot': overshoots target then snaps back."
    )
    time_start: float = Field(
        default=0.0,
        description="Normalized time [0,1] when this primitive begins within the attack duration."
    )
    time_end: float = Field(
        default=1.0,
        description="Normalized time [0,1] when this primitive ends within the attack duration."
    )


class RotateParams(BaseModel):
    start: float = Field(description="Starting rotation angle in degrees (Z-axis).")
    end: float = Field(description="Ending rotation angle in degrees (Z-axis).")
    curve: CurveType = Field(
        description="'EaseOut': impactful slashes. 'EaseIn': wind-up. 'Overshoot': snappy bounce."
    )
    time_start: float = Field(
        default=0.0,
        description="Normalized time [0,1] when this primitive begins within the attack duration."
    )
    time_end: float = Field(
        default=1.0,
        description="Normalized time [0,1] when this primitive ends within the attack duration."
    )


class ScaleParams(BaseModel):
    start: Vector3 = Field(
        default_factory=lambda: Vector3(x=1.0, y=1.0, z=1.0),
        description="Starting scale: {x, y, z}. Defaults to {1, 1, 1}."
    )
    end: Vector3 = Field(description="Target scale at end of motion: {x, y, z}.")
    curve: CurveType = Field(description="Interpolation curve for the scale transition.")
    time_start: float = Field(
        default=0.0,
        description="Normalized time [0,1] when this primitive begins within the attack duration."
    )
    time_end: float = Field(
        default=1.0,
        description="Normalized time [0,1] when this primitive ends within the attack duration."
    )


class PrimitiveArc(BaseModel):
    primitive_id: Literal["OP_ARC"]
    params: ArcParams

class PrimitiveMove(BaseModel):
    primitive_id: Literal["OP_MOVE"]
    params: MoveParams

class PrimitiveRotate(BaseModel):
    primitive_id: Literal["OP_ROTATE"]
    params: RotateParams

class PrimitiveScale(BaseModel):
    primitive_id: Literal["OP_SCALE"]
    params: ScaleParams


AnyMotionPrimitive = Annotated[
    Union[
        PrimitiveArc,
        PrimitiveMove,
        PrimitiveRotate,
        PrimitiveScale,
    ],
    Field(discriminator="primitive_id")
]
