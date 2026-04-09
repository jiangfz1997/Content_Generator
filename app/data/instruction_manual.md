# GLOBAL DESIGN CONSTITUTION (STRICT RULES)

### THE CORE CONSTITUTION (Design Principles)
1. **Primitives are Physics, Payloads are Chemistry**: Primitives (OPs) define the raw laws of the engine. Payloads are the intended 'reactions' created by combining those laws.
2. **Intent-Driven Architecture**: Never use a Primitive just because it's available; use it only if it serves the specific tactical role of the chosen Payload.
3. **Atomic Integrity**: Do not attempt to bypass the logic of a Payload. If a Payload requires a Timer to function, the weapon's motion must accommodate that duration.


---

# Engine Tactical Manual
**Overview:** The engine utilizes a suite of primitives such as OP_APPLY_FORCE, OP_MODIFY_HP, OP_MODIFY_SPEED, OP_SPAWN_PROJECTILE, OP_TIMER, OP_ARC, OP_MOVE, OP_ROTATE, and OP_SCALE. OP_MODIFY_HP scales damage based on the source (weapon_multiplier or absolute) and tag (element type), while OP_SPAWN_PROJECTILE fires the weapon's runtime projectile via "@weapon.projectile_id" — the projectile choice belongs to the designer, not the payload.

### Atomic Capabilities (Index):
- OP_APPLY_FORCE: Applies a force to the target or self. (Params: magnitude sets force strength; target_type determines recipient; direction_mode defines knockback direction — use 'FromColliderCenter' for explosions/AoE so all targets are pushed radially outward from the blast center, use 'SourceToTarget' for melee knockback, use 'SourceForward' for recoil; override_duration disables AI for smooth stop.)
- OP_MODIFY_HP: Modifies the target's HP based on value and source. (Params: value is positive; source selects weapon_multiplier (level-scaled) or absolute (flat); category sets damage/heal/self_damage; tag names the element.)
- OP_MODIFY_SPEED: Adjusts speed of target or self. (Params: value modifies speed; target_type determines recipient; mode sets modification type (Set, Add, Multiplier); duration applies temporary buff/debuff.)
- OP_SPAWN_PROJECTILE: Spawns a projectile from ProjectileDatabase. (Params: projectile_id MUST always be "@weapon.projectile_id" — the actual projectile is chosen by the designer at the weapon level and resolved at runtime, never hardcode a specific ID; count sets number of projectiles; spread_angle defines multi-shot spread.)
- OP_TIMER: Executes actions over a set duration with intervals. (Params: duration sets total time; interval defines execution frequency; actions contain nested primitive effects.)


### Motion Capabilities (Index):
- OP_ARC: Sweeps weapon along a circular orbit. (Params: radius defines orbit size; start_angle/end_angle set arc range; curve controls motion style; time_start/time_end manage primitive timing.)
- OP_MOVE: Moves weapon from start to end position. (Params: start/end define motion path; curve controls interpolation; time_start/time_end manage primitive timing.)
- OP_ROTATE: Rotates weapon around Z-axis. (Params: start/end set rotation angles; curve controls interpolation; time_start/time_end manage primitive timing.)
- OP_SCALE: Scales weapon dimensions. (Params: start/end define scale changes; curve controls interpolation; time_start/time_end manage primitive timing.)

## Payload Catalog
### payload_dot_fire
- Tactical Intent: Sustained fire DoT — stack with knockback for zone denial.
- Logic: OP_TIMER fires OP_MODIFY_HP (0.25× weapon damage, fire tag) every 1s for 5s.

### payload_shoot_generic
- Tactical Intent: Direct fire — effective for engaging single targets.
- Logic: OP_SPAWN_PROJECTILE fires the weapon's configured projectile via projectile_id="@weapon.projectile_id" (count=1, spread_angle=0). The actual projectile is determined by the designer, not this payload.

### payload_slow
- Tactical Intent: Control enemy movement — slows down targets for easier targeting or escape.
- Logic: OP_MODIFY_SPEED reduces the target's movement speed to 50% (Multiplier mode) for 3 seconds.

### payload_strike
- Tactical Intent: High damage burst — used for quick, impactful hits.
- Logic: OP_MODIFY_HP deals an instant burst of physical damage (1.0× weapon damage, physical tag) to the target.

### payload_explode
- Tactical Intent: Heavy AOE blast — damages and knocks back all enemies caught in the explosion radius.
- Logic: OP_MODIFY_HP deals 1.5× weapon damage (physical), then OP_APPLY_FORCE knocks back target radially outward from the explosion center (FromColliderCenter) with magnitude 20.

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
  "id":           "weapon_pistol",
  "name":         "Pistol",
  "icon":         "weapon_pistol.png",
  "stats":        { ... },
  "visual_stats": { ... },
  "motions":      [ ... ],
  "abilities":    { ... }
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique identifier. Must match the filename (e.g. `weapon_pistol.json` → `"weapon_pistol"`). |
| `name` | `string` | Display name shown in UI. |
| `icon` | `string` | Sprite filename inside `Resources/Weapons/`. Defaults to `"{id}.png"` if omitted. |
| `stats` | `object` | Numeric parameters controlling timing, range, and base power. See table below. |
| `visual_stats` | `object` | Visual sizing and pivot configuration. See table below. |
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
| `projectile_id` | `string` | `""` | **Ranged only.** ID of the projectile to fire (e.g. `"projectile_bullet"`). Must match an entry in `ProjectileDatabase`. Leave empty or omit for melee weapons. |
| `projectile_count` | `int` | `1` | **Ranged only.** Number of projectiles fired per attack. `1` = pistol, `5` = shotgun. |
| `spread_angle` | `float` | `0.0` | **Ranged only.** Total spread in degrees when `projectile_count > 1`. E.g. `30` fans projectiles across a 30° arc. Ignored when `projectile_count` is `1`. |


---

## `visual_stats` Fields

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `world_length` | `float` | `1.0` | **Currently not read by code** — `WeaponInstance._targetWorldLength` is hardcoded to `1.0`. Reserved for future use. Intended to set the weapon sprite's longest dimension in world units via `ApplySizeNormalization`. |
| `pivot` | `object {x, y}` | `{x:0.5, y:0.0}` | The sprite's pivot point in normalized coordinates used when loading the sprite. Controls the rotation anchor. `x=0` is the left/handle end, `x=1` is the tip. Typical values: `{x:0.1, y:0}` for a grip-pivoting sword. |

---

## `abilities` Fields

Maps **trigger keys** to ordered lists of payload IDs. Each payload is defined separately in `Assets/StreamingAssets/Config/Payloads/*.json`.

```json
"abilities": {
  "on_hit":    ["payload_strike"],
  "on_attack": ["payload_shoot_generic"],
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
    "on_hit":    ["payload_strike"],
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
    "hit_end": 0,
    "projectile_id": "projectile_bullet",
    "projectile_count": 1,
    "spread_angle": 0.0
  },
  "motions": [
    { "primitive_id": "OP_ROTATE", "params": { "start": 0, "end": -15, "curve": "EaseOut" } }
  ],
  "abilities": {
    "on_hit":    [],
    "on_attack": ["payload_shoot_generic"],
    "on_equip":  []
  }
}
```

## Motion Design Rules — Ranged Weapons

Design motions based on the **physical nature** of the weapon, NOT just the fact that it fires a projectile.

| Weapon type | Recommended motion | Example |
| :--- | :--- | :--- |
| **Firearms** (pistol, rifle, shotgun, cannon) | Backward `OP_MOVE` to simulate recoil | `end: {x:-0.3, y:0}, curve: EaseOut` |
| **Bows / crossbows** | Pull-back then snap: `OP_MOVE` EaseIn + OP_ROTATE | `end: {x:-0.15, y:0}` then release |
| **Wands / staves / magic** | Gentle forward thrust or rotate | `end: {x:0.2, y:0}` or small OP_ROTATE |
| **Thrown weapons** | Forward throw arc | `end: {x:0.3, y:0.1}` |

> **CRITICAL:** Never add a backward recoil motion (`OP_MOVE` with negative x) to a wand, bow, staff, orb, or any magic weapon. Recoil is exclusive to physical firearms.

---

# Projectile Implementation Reference
# Projectile Database
> Generated on: 2026-03-17 18:31:34
> Total entries: 6

## `projectile_bullet`
- **Name:** Bullet

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `14` |
| `lifetime` | `3` |
| `penetration` | `0` |

### Abilities
- **on_hit:** `payload_strike`

---
## `projectile_explosion`
- **Name:** Explosion

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `0` |
| `lifetime` | `0.08` |
| `penetration` | `99` |
| `collider_radius` | `2.5` |

### Abilities
- **on_hit:** `payload_explode`

---
## `projectile_lightning_poison`
- **Name:** Lightning Poison Dart

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `10` |
| `lifetime` | `4` |
| `penetration` | `0` |
| `collider_radius` | `0.1` |

### Abilities
- **on_hit:** `payload_dot_poison`, `payload_slow`

---
## `projectile_plasma_bolt`
- **Name:** Plasma Bolt

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `18` |
| `lifetime` | `2` |
| `penetration` | `99` |
| `collider_radius` | `0.1` |

### Abilities
- **on_hit:** `payload_magic_bolt`, `payload_dot_fire`

---
## `projectile_rocket`
- **Name:** Rocket

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `10` |
| `lifetime` | `4` |
| `penetration` | `0` |
| `collider_radius` | `0.15` |

### Abilities
- **on_hit:** `payload_rocket_impact`

---
## `projectile_water_shadow`
- **Name:** Water Shadow Projectile

### Stats
| Field | Value |
| :--- | :--- |
| `speed` | `12` |
| `lifetime` | `3.5` |
| `penetration` | `0` |
| `collider_radius` | `0.1` |

### Abilities
- **on_hit:** `payload_dot_poison`, `payload_dot_dark_poison`

---
