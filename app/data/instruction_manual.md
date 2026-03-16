# GLOBAL DESIGN CONSTITUTION (STRICT RULES)

### THE CORE CONSTITUTION (Design Principles)
1. **Primitives are Physics, Payloads are Chemistry**: Primitives (OPs) define the raw laws of the engine. Payloads are the intended 'reactions' created by combining those laws.
2. **Intent-Driven Architecture**: Never use a Primitive just because it's available; use it only if it serves the specific tactical role of the chosen Payload.
3. **Atomic Integrity**: Do not attempt to bypass the logic of a Payload. If a Payload requires a Timer to function, the weapon's motion must accommodate that duration.


---

# Engine Tactical Manual
**Overview:** The engine provides a set of primitives that can be combined to create complex payloads. OP_MODIFY_HP deals damage or heals based on either a coefficient of the weapon's damage or a flat value. OP_SPAWN_PROJECTILE allows the spawning of projectiles with defined properties, enabling area-of-effect and multi-target attacks. These primitives enable a wide range of tactical behaviors in combat.

### Atomic Capabilities (Index):
- OP_APPLY_FORCE: Applies a force to a target entity. (Params: magnitude sets force strength; target_type specifies force recipient; direction_mode determines knockback direction; override_duration disables AI movement for smooth sliding.)
- OP_MODIFY_HP: Modifies target HP based on specified value and source. (Params: value is positive; source selects weapon_multiplier (level-scaled) or absolute (flat); category sets damage/heal/self_damage; tag names the element.)
- OP_MODIFY_SPEED: Modifies target speed using a specified value and mode. (Params: value adjusts speed; target_type specifies recipient; mode determines operation type (Set, Add, Multiplier); duration sets effect duration.)
- OP_SPAWN_PROJECTILE: Spawns a projectile by referencing a projectile_id. (Params: projectile_id identifies projectile; count sets number of projectiles; spread_angle controls multi-shot spread.)
- OP_TIMER: Executes nested actions at specified intervals over a duration. (Params: duration sets total lifespan; interval defines execution frequency; actions contain nested primitive configurations.)
- OP_ARC: Moves weapon along a circular orbit. (Params: radius defines orbit size; start_angle and end_angle set sweep range; curve determines interpolation; time_start/time_end control timing.)
- OP_MOVE: Moves weapon from start to end position. (Params: start and end define movement path; curve determines interpolation; time_start/time_end control timing.)
- OP_ROTATE: Rotates weapon around its Z-axis. (Params: start and end define rotation angles; curve determines interpolation; time_start/time_end control timing.)
- OP_SCALE: Scales weapon from start to end size. (Params: start and end define scale changes; curve determines interpolation; time_start/time_end control timing.)

### Motion Capabilities (Index):
- OP_ARC: Moves weapon along a circular orbit. (Params: radius defines orbit size; start_angle and end_angle set sweep range; curve determines interpolation; time_start/time_end control timing.)
- OP_MOVE: Moves weapon from start to end position. (Params: start and end define movement path; curve determines interpolation; time_start/time_end control timing.)
- OP_ROTATE: Rotates weapon around its Z-axis. (Params: start and end define rotation angles; curve determines interpolation; time_start/time_end control timing.)
- OP_SCALE: Scales weapon from start to end size. (Params: start and end define scale changes; curve determines interpolation; time_start/time_end control timing.)

## Payload Catalog
### payload_dot_bleed
- Tactical Intent: Sustained bleed damage over a short duration.
- Logic: OP_TIMER fires OP_MODIFY_HP (0.3× weapon damage, bleed tag) every 0.5s for 3s.

### payload_dot_dark_poison
- Tactical Intent: Sustained poison damage with added movement debuff.
- Logic: OP_TIMER fires OP_MODIFY_HP (0.25× weapon damage) every 1s for 5s.

### payload_dot_fire
- Tactical Intent: Sustained fire damage over a moderate duration.
- Logic: OP_TIMER fires OP_MODIFY_HP (0.25× weapon damage, fire tag) every 1s for 5s.

### payload_dot_poison
- Tactical Intent: Sustained poison damage over an extended duration.
- Logic: OP_TIMER fires OP_MODIFY_HP (0.2× weapon damage, poison tag) every 1s for 6s.

### payload_drain
- Tactical Intent: Deals damage while restoring health to the caster.
- Logic: OP_MODIFY_HP deals magic damage (0.6× weapon damage) and heals the caster for a fixed amount.

### payload_freeze
- Tactical Intent: Immobilizes the target for a short duration.
- Logic: OP_MODIFY_SPEED reduces the target's speed to 10% for 2s.

### payload_haste
- Tactical Intent: Grants a burst of speed to the wielder.
- Logic: OP_MODIFY_SPEED increases the wielder's speed to 2x for 3s.

### payload_knockback
- Tactical Intent: Knocks the target back, useful for creating space or disrupting clusters.
- Logic: OP_APPLY_FORCE blasts the target away from the point of impact.

### payload_magic_bolt
- Tactical Intent: Instant magic damage with ignores physical armor.
- Logic: OP_MODIFY_HP deals an instant burst of magic damage (0.8× weapon damage).

### payload_pull
- Tactical Intent: Draws the target closer, useful for crowd control.
- Logic: OP_APPLY_FORCE pulls the target toward the caster.

### payload_recoil_dash
- Tactical Intent: Propels the wielder backward on hit, useful for hit-and-run strategies.
- Logic: OP_APPLY_FORCE propels the wielder backward.

### payload_sacrifice
- Tactical Intent: Pays a fixed blood cost on each hit, useful for blood-magic builds.
- Logic: OP_MODIFY_HP reduces the wielder's health by a fixed amount (8 HP) on each hit.

### payload_shadow_nova
- Tactical Intent: Fires multiple poison projectiles in all directions.
- Logic: OP_SPAWN_PROJECTILE fires 8 shadow-poison projectiles in all directions.

### payload_slow
- Tactical Intent: Slows the target's movement speed for a moderate duration.
- Logic: OP_MODIFY_SPEED reduces the target's speed to 50% for 3s.

### payload_strike
- Tactical Intent: Deals an instant burst of physical damage.
- Logic: OP_MODIFY_HP deals an instant burst of physical damage (1.0× weapon damage).

### payload_toxic_vortex
- Tactical Intent: Creates a localized singularity that pulls enemies inward while dealing poison damage.
- Logic: OP_TIMER fires OP_APPLY_FORCE to pull enemies inward and OP_MODIFY_HP to deal poison damage (0.2× weapon damage, poison tag) every 0.5s for 4s.

### payload_venom_tether
- Tactical Intent: Repeatedly pulls the target towards the caster while dealing poison damage over a set duration.
- Logic: OP_TIMER repeatedly pulls the target towards the caster and deals poison damage (0.2× weapon damage, poison tag) every 1s for 4s.


---

# Weapon Implementation Reference
# Weapon JSON Schema
> Updated: 2026-03-15

Weapon definitions live in `Assets/StreamingAssets/Config/Weapons/*.json`.
Each file describes one weapon and is loaded by `WeaponDatabase` at startup.

---

## Top-Level Structure

```json
{
  "id":      "weapon_pistol",
  "name":    "Pistol",
  "stats":   { ... },
  "motions": [ ... ],
  "abilities": { ... }
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique identifier. Must match the filename (e.g. `weapon_pistol.json` → `"weapon_pistol"`). |
| `name` | `string` | Display name shown in UI. |
| `stats` | `object` | Numeric parameters controlling timing, range, and base power. See table below. |
| `motions` | `array` | List of motion primitives that animate the weapon during an attack. See **MotionPrimitivesSchema.md**. |
| `abilities` | `object` | Maps trigger keys to lists of payload IDs. See **Abilities** section below. |

---

## `stats` Fields

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `range` | `float` | `1.5` | Collider activation distance in world units. Controls how far the weapon hitbox extends from the player. |
| `duration` | `float` | `0.5` | Total attack animation duration in seconds. Recommended range: **0.3 – 0.6**. Drives the coroutine length in `WeaponInstance`. |
| `cooldown` | `float` | `0.5` | Minimum time in seconds between attacks. Currently commented out in `WeaponInstance` (intentional — reserved for future use). |
| `base_damage` | `float` | `10` | The weapon's raw damage output at `design_level`. Used in the scaling formula: `final_damage = base_damage × √(player_level / design_level)`. |
| `design_level` | `int` | `1` | The player level this weapon is balanced for. A player at exactly `design_level` will deal exactly `base_damage`. Below → weaker, above → stronger. |
| `hit_start` | `float` | `0.2` | Normalized time [0, 1] when the hitbox collider is enabled. Use `0` for ranged weapons that never use the physical collider. |
| `hit_end` | `float` | `0.8` | Normalized time [0, 1] when the hitbox collider is disabled. Use `0` (same as `hit_start`) for ranged weapons. |

### Damage Scaling Reference

| `design_level` | Suggested `base_damage` | Intended Role |
| :--- | :--- | :--- |
| 1 | 10 – 14 | Starter weapon |
| 3 | 14 – 18 | Early game |
| 5 | 18 – 22 | Mid game |
| 7 | 22 – 28 | Late mid game |
| 10 | 28 – 35 | End game |
| 12+ | 35 – 45 | Boss / unique |

---

## `abilities` Fields

Maps **trigger keys** to ordered lists of payload IDs. Each payload is defined separately in `Assets/StreamingAssets/Config/Payloads/*.json`.

```json
"abilities": {
  "on_hit":    ["payload_fire_burn"],
  "on_attack": ["payload_shoot_bullet"],
  "on_equip":  []
}
```

| Trigger Key | When it fires | Typical use |
| :--- | :--- | :--- |
| `on_hit` | When the weapon's hitbox collider enters an enemy collider (inside the `hit_start`–`hit_end` window). `ctx.Target` = the enemy hit. | Melee damage, knockback, status effects. |
| `on_attack` | At the very start of `AttackRoutine`, before any animation. `ctx.Target` = `null`. | Spawning projectiles (ranged weapons). |
| `on_equip` | When the player equips this weapon. | Passive stat buffs, visual effects. |

**Rules:**
- Each trigger key maps to an array of payload ID strings.
- Payloads in the array execute **in order**.
- An empty array `[]` is valid and means no effects fire for that trigger.
- Omitting a trigger key is equivalent to an empty array.
- For ranged weapons: set `hit_start: 0, hit_end: 0` to disable the physical hitbox entirely and rely solely on `on_attack`.

---

## Full Example — Melee Weapon

```json
{
  "id": "weapon_axe",
  "name": "Mjolnir Prototype",
  "stats": {
    "range": 1.5,
    "duration": 0.5,
    "cooldown": 0.4,
    "base_damage": 12,
    "design_level": 1,
    "hit_start": 0.2,
    "hit_end": 0.85
  },
  "motions": [
    { "primitive_id": "OP_ROTATE", "params": { "start": 90, "end": -90, "curve": "EaseIn" } },
    { "primitive_id": "OP_MOVE",   "params": { "start": {"x":0,"y":0}, "end": {"x":0.5,"y":0}, "curve": "PingPong" } }
  ],
  "abilities": {
    "on_hit":    ["payload_fire_burn"],
    "on_attack": [],
    "on_equip":  []
  }
}
```

## Full Example — Ranged Weapon

```json
{
  "id": "weapon_pistol",
  "name": "Pistol",
  "stats": {
    "range": 1.0,
    "duration": 0.3,
    "cooldown": 0.5,
    "base_damage": 15,
    "design_level": 3,
    "hit_start": 0,
    "hit_end": 0
  },
  "motions": [
    { "primitive_id": "OP_MOVE", "params": { "start": {"x":0,"y":0}, "end": {"x":-0.3,"y":0}, "curve": "EaseOut" } }
  ],
  "abilities": {
    "on_hit":    [],
    "on_attack": ["payload_shoot_bullet"],
    "on_equip":  []
  }
}
```


---

# Projectile Implementation Reference
# Projectile JSON Schema
> Updated: 2026-03-15

Projectile definitions live in `Assets/StreamingAssets/Config/Projectiles/*.json`.
Each file describes one projectile type and is loaded by `ProjectileDatabase` at startup.
Projectiles are spawned at runtime via the `OP_SPAWN_PROJECTILE` primitive.

---

## Top-Level Structure

```json
{
  "id":        "projectile_bullet",
  "name":      "Bullet",
  "stats":     { ... },
  "abilities": { ... }
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique identifier. Referenced by `OP_SPAWN_PROJECTILE`'s `projectile_id` param. Must match the filename. |
| `name` | `string` | Display / debug name. |
| `stats` | `object` | Physics and lifetime parameters. See table below. |
| `abilities` | `object` | Maps trigger keys to lists of payload IDs. Only `on_hit` is currently supported. |

---

## `stats` Fields

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `speed` | `float` | `10.0` | Travel speed in world units per second via `Rigidbody2D.linearVelocity`. Set to `0` for a stationary projectile (e.g. explosion area). |
| `lifetime` | `float` | `3.0` | Maximum time in seconds before the projectile self-destructs, regardless of hit. |
| `penetration` | `int` | `0` | Number of **additional** targets the projectile can hit after the first. `0` = single target (destroyed on first hit). `1` = pierces 1 extra target. `99` = effectively unlimited (use for explosion areas). |
| `collider_radius` | `float` | `0.1` | Radius of the `CircleCollider2D` in world units. Increase for explosion-type projectiles (e.g. `2.5` for a grenade blast). |

### Projectile Type Recipes

| Type | `speed` | `lifetime` | `penetration` | `collider_radius` |
| :--- | :--- | :--- | :--- | :--- |
| Fast bullet | 14–20 | 2–3 | 0 | 0.1 |
| Slow projectile (rocket) | 8–12 | 4–6 | 0 | 0.15 |
| Piercing bolt | 14–18 | 3 | 2–5 | 0.1 |
| Explosion area (spawn-on-hit) | 0 | 0.05–0.1 | 99 | 1.5–3.0 |

---

## `abilities` Fields

| Trigger Key | When it fires | Typical use |
| :--- | :--- | :--- |
| `on_hit` | When the projectile's collider overlaps an enemy (once per target, tracked by `_hitTargets`). `ctx.Source` = original attacker, `ctx.Target` = enemy hit, `ctx.WeaponDamage` = locked at spawn time. | Damage, knockback, spawning secondary explosion projectile. |

**Explosion chaining pattern:**
```
projectile_rocket.on_hit → payload_rocket_impact
  payload_rocket_impact → OP_SPAWN_PROJECTILE (projectile_explosion)
    projectile_explosion.on_hit → payload_explosion_damage
      payload_explosion_damage → OP_MODIFY_HP + OP_APPLY_FORCE
```

The explosion projectile (`speed: 0, penetration: 99`) sits in place for one physics frame. Unity calls `OnTriggerEnter2D` for all overlapping colliders when the trigger is first created, so every enemy in radius receives the effect independently.

---

## Full Example — Basic Bullet

```json
{
  "id": "projectile_bullet",
  "name": "Bullet",
  "stats": {
    "speed": 14.0,
    "lifetime": 3.0,
    "penetration": 0,
    "collider_radius": 0.1
  },
  "abilities": {
    "on_hit": ["payload_bullet_hit"]
  }
}
```

## Full Example — Explosion Area (spawned on rocket impact)

```json
{
  "id": "projectile_explosion",
  "name": "Explosion",
  "stats": {
    "speed": 0,
    "lifetime": 0.08,
    "penetration": 99,
    "collider_radius": 2.5
  },
  "abilities": {
    "on_hit": ["payload_explosion_damage"]
  }
}
```
