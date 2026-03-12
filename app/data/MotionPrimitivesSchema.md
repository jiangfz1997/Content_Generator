# Motion Primitives API (Logic & Physics)
> Generated on: 2026-03-10 22:21:07
> Total entries: 3

## `OP_MOVE`
- **Class:** `PrimitiveMove`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `Vector3 {x, y}` | The starting local offset from the weapon's pivot point. |
| `end` | `Vector3 {x, y}` | The target local offset the weapon moves toward. |
| `curve` | `string` | The interpolation curve: 'Linear', 'EaseOut' (fast start, slow end for swings), 'PingPong' (out and back for thrusts), or 'Loop'. |

---
## `OP_ROTATE`
- **Class:** `PrimitiveRotate`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `float` | The starting rotation angle in degrees (Z-axis). |
| `end` | `float` | The ending rotation angle in degrees (Z-axis). |
| `curve` | `string` | The interpolation curve: 'Linear', 'EaseOut' (for impactful slashes), 'PingPong', or 'Loop'. |

---
## `OP_SCALE`
- **Class:** `PrimitiveScale`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `Vector3 {x, y, z}` | The starting scale of the weapon. Defaults to {1, 1, 1}. |
| `end` | `Vector3 {x, y, z}` | The target scale at the end of the motion duration. |
| `curve` | `string` | The interpolation curve determining how the scaling transitions. |

---
