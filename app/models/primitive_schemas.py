from __future__ import annotations  # 🌟 必须放在第一行，支持优雅的递归引用
from pydantic import BaseModel, Field
from typing import List, Literal, Union
from typing_extensions import Annotated


# ==========================================
# 1. 定义各自的 Params 参数体
# ==========================================

class ApplyForceParams(BaseModel):
    magnitude: float = Field(
        description="Physical impulse strength. Positive = push away, negative = pull toward. "
                    "Ignores target mass for consistent knockback distance."
    )
    target_type: Literal["self", "target"] = Field(
        default="target",
        description="'self' for recoil/dash, 'target' to knockback an enemy."
    )
    direction_mode: Literal["HitNormal", "SourceForward", "FromHitPoint", "SourceToTarget"] = Field(
        description="How the force direction vector is calculated. "
                    "'HitNormal': perpendicular to collision surface. "
                    "'SourceForward': opposite to caster's facing (recoil). "
                    "'FromHitPoint': impact point to target center (explosions). "
                    "'SourceToTarget': caster position to target position."
    )
    override_duration: float = Field(
        default=0.25,
        description="Seconds the target's AI movement is disabled (stun window) so physics can slide it to a halt."
    )


class ModifyHPParams(BaseModel):
    value: float = Field(
        description="ALWAYS a POSITIVE number. "
                    "When source='weapon_multiplier': coefficient of ctx.WeaponDamage "
                    "(e.g. 1.0 = 100% weapon damage, 0.25 = 25% per DOT tick). "
                    "When source='absolute': flat HP amount, ignores level scaling."
    )
    source: Literal["weapon_multiplier", "absolute"] = Field(
        default="absolute",
        description="'weapon_multiplier': scales with player level and weapon design_level. "
                    "Use for all combat damage. "
                    "'absolute': fixed flat amount regardless of level. "
                    "Use for sacrifice costs, fixed heals, etc."
    )
    category: Literal["damage", "heal", "self_damage"] = Field(
        default="damage",
        description="'damage': reduces target HP (value applied as negative internally). "
                    "'heal': restores target HP (value applied as positive). "
                    "'self_damage': reduces own HP, capped to leave 1 HP minimum."
    )
    tag: str = Field(
        default="physical",
        description="Element or context tag: 'physical', 'fire', 'ice', 'poison', 'lightning', "
                    "'magic', 'true', 'sacrifice', 'heal', 'lifesteal'."
    )
    target_type: Literal["self", "target"] = Field(
        default="target",
        description="Who receives the HP modification: 'self' (caster) or 'target' (enemy hit)."
    )


class ModifySpeedParams(BaseModel):
    value: float = Field(
        description="Numeric speed modifier. Exact effect depends on 'mode' "
                    "(e.g. 0.5 as Multiplier halves speed, 15.0 as Set assigns speed of 15)."
    )
    target_type: Literal["self", "target"] = Field(
        default="target",
        description="'self' (caster) or 'target' (hit entity)."
    )
    mode: Literal["Set", "Add", "Multiplier"] = Field(
        description="'Set': override current speed. 'Add': add to current speed. 'Multiplier': multiply current speed."
    )
    duration: float = Field(
        description="CRITICAL: >0 applies a temporary logic-level buff/debuff (e.g. 3s slow). "
                    "==0 applies an instant physics-level impulse via Rigidbody velocity (e.g. dash)."
    )


class SpawnProjectileParams(BaseModel):
    projectile_id: str = Field(
        description="ID of the projectile definition in ProjectileDatabase (e.g. 'projectile_bullet'). "
                    "Must match a file in Assets/StreamingAssets/Config/Projectiles/."
    )
    count: int = Field(
        default=1,
        description="Number of projectiles fired simultaneously."
    )
    spread_angle: float = Field(
        default=0.0,
        description="Total spread angle in degrees when count > 1. "
                    "E.g. 30 = projectiles fan out over a 30-degree arc."
    )


class TimerParams(BaseModel):
    duration: float = Field(description="Total timer lifespan in seconds. Destroys runner on expiry.")
    interval: float = Field(description="Seconds between each execution tick.")
    actions: List['AnyLogicPrimitive'] = Field(
        description="CRITICAL: Nested array of primitives executed every interval tick. "
                    "Use for DOT or recurring logic."
    )


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

class PrimitiveSpawnProjectile(BaseModel):
    primitive_id: Literal["OP_SPAWN_PROJECTILE"]
    params: SpawnProjectileParams

class PrimitiveTimer(BaseModel):
    primitive_id: Literal["OP_TIMER"]
    params: TimerParams


# ==========================================
# 3. 终极多态联合体 (The Discriminated Union)
# ==========================================

AnyLogicPrimitive = Annotated[
    Union[
        PrimitiveApplyForce,
        PrimitiveModifyHP,
        PrimitiveModifySpeed,
        PrimitiveSpawnProjectile,
        PrimitiveTimer,
    ],
    Field(discriminator="primitive_id")
]
TimerParams.model_rebuild()