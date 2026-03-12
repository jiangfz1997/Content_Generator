from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional

from app.models.motion_primitive_schemas import AnyMotionPrimitive
from app.models.primitive_schemas import AnyLogicPrimitive


class Vector2(BaseModel):
    x: float
    y: float

class Vector3(BaseModel):
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    z: float = Field(default=0.0)

class WeaponStats(BaseModel):
    range: float = Field(description="武器攻击距离 (World Units)")
    duration: float = Field(description="攻击持续时间 (Seconds)")
    cooldown: float = Field(description="攻击冷却时间 (Seconds)")

class VisualStats(BaseModel):
    world_length: float = Field(description="武器在世界空间中的视觉长度，例如匕首0.8，长矛3.0")
    pivot: Dict[str, float] = Field(description="旋转轴心点，通常 x=0.0 (底部) 或 x=0.5 (中心)")



AvailablePayloads = Literal[
    "payload_fire_burn",
    "payload_ice_freeze",
    "payload_gravity_pull",
    "payload_heal_from_damage",
    "payload_blood_frenzy",
    "payload_heavy_smash",
    "payload_toxic"
]
class Abilities(BaseModel):
    on_hit: List[AvailablePayloads] = Field(
        max_length=1,
        description="List of Payload IDs triggered on hit.(MAX 1) If the weapon has no on-hit effects, you MUST return an empty array []."
    )
    on_equip: List[AvailablePayloads] = Field(
        max_length=1,
        description="List of Payload IDs triggered passively when equipped.(MAX 1) If there are no passive equip effects, you MUST return an empty array []."
    )

class WeaponSchema(BaseModel):

    manual_analysis: str = Field(description="Your thought process for selecting the Payload(CRITICAL: MAX 20 WORDS OR 2 SENTENCES)")
    stat_balance_reasoning: str = Field(description="Your thought process for balancing stats(CRITICAL: MAX 20 WORDS OR 2 SENTENCES)")

    id: str = Field(description="Unique ID")
    name: str = Field(description="Weapon's name")
    stats: WeaponStats = Field(
        description="Core combat stats defining the weapon's power, range, and operational feel."
    )

    visual_stats: VisualStats = Field(
        description="Visual parameters defining how the weapon is rendered and scaled in the game engine."
    )

    motions: List[AnyMotionPrimitive] = Field(
        max_length=3,
        description="Sequence of motion primitives defining the attack animation. MAX 3 motions."
    )

    abilities: Abilities = Field(
        description="Engine capabilities and logic payloads bound to this weapon."
    )

    icon: Optional[str] = Field(
        default='weapon_axe.png',
        description="File name of the weapon's UI icon, e.g., 'sword_01.png'."
    )


class WeaponPatchSchema(BaseModel):
    """
    Surgical patch for weapon attributes.
    Only the fields that need modification should be provided.
    """
    patch_analysis: str = Field(description="Brief explanation of the fix. (MAX 20 WORDS)")

    name: Optional[str] = None
    stats: Optional[WeaponStats] = None
    visual_stats: Optional[VisualStats] = None
    motions: Optional[List[AnyMotionPrimitive]] = None
    abilities: Optional[Abilities] = None


def apply_weapon_patch(original_json: dict, patch: WeaponPatchSchema) -> dict:
    """
    将 AI 生成的补丁对象安全地合并到原始 JSON 数据中
    """
    # 1. 将原始字典转换为 Pydantic 对象
    original_obj = WeaponSchema(**original_json)

    # 2. 提取补丁中真正被赋值的字段 (排除 unset 的字段)
    patch_data = patch.model_dump(exclude_unset=True)

    # 3. 移除补丁专用的分析字段，不污染核心数据
    patch_data.pop("patch_analysis", None)

    # 4. 执行合并操作
    updated_obj = original_obj.model_copy(update=patch_data)

    return updated_obj.model_dump()