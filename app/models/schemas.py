from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional


class Vector2(BaseModel):
    x: float
    y: float


class Motion(BaseModel):
    # 放开限制，依靠 Prompt 和 Registry 来约束 AI
    primitive_id: str = Field(description="动作类型，必须从 Context 提供的列表中选择")
    params: Dict[str, Any] = Field(description="动作参数，必须严格遵守对应的参数结构")


class WeaponSchema(BaseModel):
    """最终生成的武器协议格式"""
    id: str = Field(description="武器唯一标识符，例如 'weapon_spear'")
    name: str = Field(description="武器名称，例如 'Mjolnir Prototype'")

    # 使用 Literal 限制 AI 只能选择你后端实现的 Ability
    abilities: Dict[
        Literal["on_hit", "on_kill", "on_dash"],
        Literal["payload_fire_burn", "payload_ice_freeze", "payload_lightning_static"]
    ] = Field(description="武器的特殊能力及其对应的效果 Primitive")

    motions: List[Motion] = Field(description="武器的攻击动作序列")

