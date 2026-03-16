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
