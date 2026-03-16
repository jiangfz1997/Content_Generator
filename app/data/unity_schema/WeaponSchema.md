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
