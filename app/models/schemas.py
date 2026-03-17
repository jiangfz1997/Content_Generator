from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional

from app.models.common_types import Vector2
from app.models.motion_primitive_schemas import AnyMotionPrimitive
from app.models.primitive_schemas import AnyLogicPrimitive



class WeaponStats(BaseModel):
    range: float = Field(description="Collider activation distance in world units.")
    duration: float = Field(description="Total attack animation duration in seconds. MUST be 0.3–0.6.")
    cooldown: float = Field(description="Minimum seconds between attacks.")

    # ！
    @field_validator("duration")
    @classmethod
    def clamp_duration(cls, v: float) -> float:
        return max(0.3, min(0.6, v))
    base_damage: float = Field(description="Raw damage output at design_level. Scaling formula: final = base_damage × √(player_level / design_level).")
    design_level: int = Field(description="Player level this weapon is balanced for. Suggested base_damage: Lv1→10-14, Lv5→18-22, Lv10→28-35.")
    hit_start: float = Field(description="Normalized time [0,1] when hitbox collider activates. Use 0 for ranged weapons (no physical hitbox).")
    hit_end: float = Field(description="Normalized time [0,1] when hitbox collider deactivates. Use 0 (same as hit_start) for ranged weapons.")

class VisualStats(BaseModel):
    world_length: float = Field(description="武器在世界空间中的视觉长度，例如匕首0.8，长矛3.0")
    pivot: Vector2 = Field(default_factory=lambda: Vector2(x=0.5, y=0.5),description="旋转轴心点，通常 x=0.0 (底部) 或 x=0.5 (中心)")



# Payload IDs are dynamic — the factory can generate new ones at runtime.
# See app/data/payloads/*.json for the current library.
AvailablePayloads = str


class Abilities(BaseModel):
    on_hit: List[AvailablePayloads] = Field(
        default_factory=list,
        max_length=3,
        description="Atomic Payload IDs triggered when the hitbox collider hits an enemy. MAX 3. Combine atomic effects (e.g. dot_fire + knockback). Leave empty [] for pure ranged weapons that use on_attack instead."
    )

    on_attack: List[AvailablePayloads] = Field(
        default_factory=list,
        max_length=2,
        description="Payload IDs triggered at the very start of AttackRoutine, before animation. MAX 2. Primary use: spawning projectiles for ranged weapons (payload containing OP_SPAWN_PROJECTILE). For melee weapons, leave empty []."
    )

    on_equip: List[AvailablePayloads] = Field(
        default_factory=list,
        max_length=2,
        description="Atomic Payload IDs that activate once when the weapon is equipped. MAX 2. Best suited for self-buffs (haste) or persistent costs (sacrifice). If no passive equip effects, return []."
    )

    @model_validator(mode="after")
    def warn_invalid_payload_ids(self):
        """Log invalid IDs but keep them — payload_validator_node handles routing."""
        from app.services.primitive_registry import primitive_registry
        known = set(primitive_registry.get_all_payloads().keys())
        all_ids = self.on_hit + self.on_attack + self.on_equip
        invalid = [pid for pid in all_ids if pid and pid not in known]
        if invalid:
            print(f"[Abilities] ⚠️ Invalid payload IDs detected (will be caught by payload_validator): {invalid}")
        return self

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

    summary: str = Field(
        description="One sentence describing this weapon's identity and core mechanic for future reference. "
                    "Include the primary payload and what makes it unique. (MAX 20 words)"
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


class ProjectileStats(BaseModel):
    speed: float = Field(description="Travel speed in world units/s. Set 0 for stationary explosion area.")
    lifetime: float = Field(description="Max seconds before self-destruct regardless of hit.")
    penetration: int = Field(default=0, description="Extra targets hit after the first. 0=single target, 99=unlimited (explosion area).")
    collider_radius: float = Field(default=0.1, description="CircleCollider2D radius in world units. Use ~2.5 for explosion areas.")

class ProjectileAbilities(BaseModel):
    on_hit: List[AvailablePayloads] = Field(
        default_factory=list,
        max_length=3,
        description="Payload IDs triggered when the projectile hits an enemy. ctx.Source=original attacker, ctx.WeaponDamage locked at spawn time."
    )

class ProjectileSchema(BaseModel):
    id: str = Field(description="Unique ID. Must match filename (e.g. 'projectile_bullet').")
    name: str = Field(description="Display/debug name.")
    stats: ProjectileStats
    abilities: ProjectileAbilities


def apply_weapon_patch(original_json: dict, patch: WeaponPatchSchema) -> dict:
    """
    将 AI 生成的补丁对象安全地合并到原始 JSON 数据中
    """
    # 1. 将原始字典转换为 Pydantic 对象（model_validate 会正确解析 discriminated union 嵌套结构）
    original_obj = WeaponSchema.model_validate(original_json)

    # 2. 提取补丁中真正被赋值的字段 (排除 unset 的字段)
    patch_data = patch.model_dump(exclude_unset=True)

    # 3. 移除补丁专用的分析字段，不污染核心数据
    patch_data.pop("patch_analysis", None)

    # 4. 合并后重新 model_validate，确保 discriminated union 字段（motions 等）被正确解析
    merged = {**original_obj.model_dump(), **patch_data}
    updated_obj = WeaponSchema.model_validate(merged)

    return updated_obj.model_dump()