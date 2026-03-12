from pydantic import BaseModel, Field
from typing import Literal, Union
from typing_extensions import Annotated



class Vector3(BaseModel):
    x: float = Field(default=0.0, description="X轴坐标/缩放")
    y: float = Field(default=0.0, description="Y轴坐标/缩放")
    z: float = Field(default=0.0, description="Z轴坐标/缩放（如果是 2D 位移通常为 0，缩放通常为 1）")

# 提取公共的 Curve 枚举，防止手滑写错，也方便统一扩展
CurveType = Literal["Linear", "EaseOut", "PingPong", "Loop"]



class MoveParams(BaseModel):
    start: Vector3 = Field(description="基于武器轴心点的起始本地偏移量。")
    end: Vector3 = Field(description="武器移动的终点本地偏移量。")
    curve: CurveType = Field(description="插值曲线：'Linear', 'EaseOut'(挥砍), 'PingPong'(突刺), 'Loop'。")

class RotateParams(BaseModel):
    start: float = Field(description="起始旋转角度 (Z轴，单位：度)。")
    end: float = Field(description="结束旋转角度 (Z轴，单位：度)。")
    curve: CurveType = Field(description="插值曲线：'Linear', 'EaseOut'(打击感重砍), 'PingPong', 'Loop'。")

class ScaleParams(BaseModel):
    start: Vector3 = Field(
        default_factory=lambda: Vector3(x=1.0, y=1.0, z=1.0),
        description="武器的起始缩放比例。默认为 {1, 1, 1}。"
    )
    end: Vector3 = Field(description="动作持续时间结束时的目标缩放比例。")
    curve: CurveType = Field(description="决定缩放如何过渡的插值曲线。")



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
        PrimitiveMove,
        PrimitiveRotate,
        PrimitiveScale
    ],
    Field(discriminator="primitive_id")
]