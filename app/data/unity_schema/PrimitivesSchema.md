# Primitives API (Logic & Physics)
> Generated on: 2026-03-15 20:06:48
> Total entries: 5

## `OP_APPLY_FORCE`
- **Class:** `PrimitiveApplyForce`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `magnitude` | `float` | The strength of the physical impulse. Because this directly sets the linear velocity, it ignores the target's mass, ensuring a consistent knockback distance. |
| `target_type` | `string` | Specifies who receives the force. Valid options are 'self' (e.g., for weapon recoil or dashes) or 'target' (e.g., for knocking back an enemy). Defaults to 'target'. |
| `direction_mode` | `string` | Determines how the knockback direction vector is calculated. Valid options: 'HitNormal' (perpendicular to the collision surface), 'SourceForward' (opposite to the caster's facing direction, ideal for recoil), 'FromHitPoint' (from the exact impact point to the target's center, ideal for explosions), or 'SourceToTarget' (from the caster's position to the target's position). |
| `override_duration` | `float` | The duration in seconds for which the target's AI movement logic is disabled (stunned). This allows the physics engine (Rigidbody2D's linear drag) to smoothly slide the target to a halt without the AI instantly overriding the knockback velocity. Defaults to 0.25s. |

---
## `OP_MODIFY_HP`
- **Class:** `PrimitiveModifyHP`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `value` | `float` | Always a POSITIVE number. When source is 'weapon_multiplier', this is a COEFFICIENT of the weapon's scaled base_damage (e.g., 1.0 = 100% weapon damage, 1.5 = 150%, 0.25 = 25% per DOT tick). When source is 'absolute', this is a flat HP amount that does not scale with level. |
| `source` | `string` | 'weapon_multiplier': value is a multiplier of ctx.WeaponDamage — scales with player level and weapon design_level. 'absolute': value is a flat number, always the same regardless of level. Use 'absolute' for fixed costs (e.g. sacrifice, healing items). Defaults to 'absolute'. |
| `category` | `string` | 'damage': reduces target HP (value applied as negative). 'heal': restores target HP (value applied as positive). 'self_damage': reduces own HP, capped to leave 1 HP. Defaults to 'damage'. |
| `tag` | `string` | Element or context: 'physical', 'fire', 'ice', 'poison', 'lightning', 'magic', 'true', 'sacrifice', 'heal', 'lifesteal'. |
| `target_type` | `string` | Who receives the modification: 'self' or 'target'. Defaults to 'target'. |

---
## `OP_MODIFY_SPEED`
- **Class:** `PrimitiveModifySpeed`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `value` | `float` | The numeric value used to modify the speed. Its exact effect depends on the specified 'mode' (e.g., 0.5 as a Multiplier halves the speed, while 15.0 as a Set instantly assigns a speed of 15). |
| `target_type` | `string` | Specifies who receives the speed modification. Valid options are 'self' (the caster) or 'target' (the hit entity). Defaults to 'target'. |
| `mode` | `string` | The mathematical operation to apply. Valid options: 'Set' (overrides current speed), 'Add' (adds to current speed), or 'Multiplier' (multiplies current speed). |
| `duration` | `float` | The duration in seconds. CRITICAL: If greater than 0, it applies a temporary logic-level buff/debuff to the AI's movement system (e.g., a 3-second slow). If exactly 0, it applies an instant physics-level impulse by directly modifying the Rigidbody's velocity (e.g., a dash or knockback). |

---
## `OP_SPAWN_PROJECTILE`
- **Class:** `PrimitiveSpawnProjectile`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `projectile_id` | `string` | ID of the projectile definition in ProjectileDatabase (e.g. 'projectile_bullet'). |
| `count` | `int` | Number of projectiles to fire simultaneously. Default 1. |
| `spread_angle` | `float` | Total spread angle in degrees when count > 1. E.g. 30 means projectiles fan out over a 30-degree arc. Default 0. |

---
## `OP_TIMER`
- **Class:** `PrimitiveTimer`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `duration` | `float` | The total lifespan of the timer in seconds. Once this duration is reached, the timer stops executing and destroys its runner. |
| `interval` | `float` | The time delay in seconds between each execution tick. For example, an interval of 1.0 means the nested actions will trigger exactly once every second. |
| `actions` | `array` | CRITICAL: A nested JSON array containing other primitive effect configurations. These nested effects will be executed together every time the 'interval' tick occurs. Ideal for Damage-Over-Time (DOT) or recurring logic. |

---
