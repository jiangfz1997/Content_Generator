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
- **on_hit:** `payload_bullet_hit`

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
- **on_hit:** `payload_explosion_damage`

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
