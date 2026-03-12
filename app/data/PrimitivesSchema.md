# Primitives API (Logic & Physics)
> Generated on: 2026-03-10 22:21:07
> Total entries: 4

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
| `value` | `float` | The amount to modify the health. Positive values heal the target, negative values deal damage. |
| `is_percentage` | `boolean` | If true, the 'value' is treated as a percentage of the target's maximum health (e.g., -0.5 removes 50% of max HP). |
| `tag` | `string` | The elemental or contextual tag for this modification (e.g., 'physical', 'fire', 'heal', 'true_damage'). Useful for damage resistance or weakness calculations. |

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
## `OP_TIMER`
- **Class:** `PrimitiveTimer`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `duration` | `float` | The total lifespan of the timer in seconds. Once this duration is reached, the timer stops executing and destroys its runner. |
| `interval` | `float` | The time delay in seconds between each execution tick. For example, an interval of 1.0 means the nested actions will trigger exactly once every second. |
| `actions` | `array` | CRITICAL: A nested JSON array containing other primitive effect configurations. These nested effects will be executed together every time the 'interval' tick occurs. Ideal for Damage-Over-Time (DOT) or recurring logic. |

---
