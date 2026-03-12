from __future__ import annotations # 🌟 必须放在第一行，支持优雅的递归引用
from pydantic import BaseModel, Field
from typing import List, Literal, Union
from typing_extensions import Annotated

# ==========================================
# 1. 定义各自的 Params 参数体
# ==========================================

class ApplyForceParams(BaseModel):
    magnitude: float = Field(description="物理冲量的强度。直接设置线速度，无视质量以保证击退距离一致。")
    target_type: Literal["self", "target"] = Field(default="target", description="受力目标。'self' 为后坐力/位移，'target' 为击退敌人。")
    direction_mode: Literal["HitNormal", "SourceForward", "FromHitPoint", "SourceToTarget"] = Field(description="击退方向向量的计算模式。")
    override_duration: float = Field(default=0.25, description="AI 寻路逻辑被禁用（眩晕）的持续时间，让物理引擎完成滑行。")

class ModifyHPParams(BaseModel):
    value: float = Field(description="HP 修改量。正数为治疗，负数为伤害。")
    is_percentage: bool = Field(description="若为 true，则 value 视为目标最大生命值的百分比（例：-0.5 即扣除 50% 最大 HP）。")
    tag: str = Field(description="伤害/治疗的元素或上下文标签（如 'physical', 'fire', 'true_damage'）。")

class ModifySpeedParams(BaseModel):
    value: float = Field(description="用于修改速度的数值。")
    target_type: Literal["self", "target"] = Field(default="target", description="受影响目标。")
    mode: Literal["Set", "Add", "Multiplier"] = Field(description="数学运算模式：覆盖(Set)、增减(Add)或乘法(Multiplier)。")
    duration: float = Field(description="CRITICAL: >0 为持续逻辑 Buff/Debuff；==0 为瞬发物理级冲量（修改 Rigidbody 速度）。")

class TimerParams(BaseModel):
    duration: float = Field(description="定时器的总生命周期（秒）。到达后销毁 runner。")
    interval: float = Field(description="每次执行 tick 的间隔时间（秒）。")
    # 🌟 核心：递归引用！允许 Timer 内部嵌套其他原语（甚至是另一个 Timer）
    actions: List['AnyLogicPrimitive'] = Field(description="CRITICAL: 每次 interval 触发时执行的嵌套 Effect 数组。用于 DOT 或周期性逻辑。")

# ==========================================
# 2. 将 Params 与专属的 primitive_id 强绑定
# ==========================================

class PrimitiveApplyForce(BaseModel):
    primitive_id: Literal["OP_APPLY_FORCE"]
    params: ApplyForceParams

class PrimitiveModifyHP(BaseModel):
    primitive_id: Literal["OP_MODIFY_HP"]
    params: ModifyHPParams

class PrimitiveModifySpeed(BaseModel):
    primitive_id: Literal["OP_MODIFY_SPEED"]
    params: ModifySpeedParams

class PrimitiveTimer(BaseModel):
    primitive_id: Literal["OP_TIMER"]
    params: TimerParams

# ==========================================
# 3. 终极多态联合体 (The Discriminated Union)
# ==========================================

# 告诉 Pydantic 和 LLM，遇到逻辑原语时，根据 primitive_id 自动派发校验
AnyLogicPrimitive = Annotated[
    Union[
        PrimitiveApplyForce,
        PrimitiveModifyHP,
        PrimitiveModifySpeed,
        PrimitiveTimer
    ],
    Field(discriminator="primitive_id")
]