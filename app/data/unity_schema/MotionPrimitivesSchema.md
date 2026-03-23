# Motion Primitives API (Logic & Physics)
> Generated on: 2026-03-17 18:31:34
> Total entries: 4

## `OP_ARC`
- **Class:** `PrimitiveArc`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `radius` | `float` | Orbit radius in world units from the weapon's pivot. E.g., 1.5 for a shortsword, 3.0 for a greatsword. |
| `start_angle` | `float` | Starting angle in degrees. 0=right, 90=up, 180=left, 270=down. |
| `end_angle` | `float` | Ending angle in degrees. Use values outside [0,360] for multi-revolution sweeps. |
| `curve` | `string` | Interpolation curve: 'EaseOut' (impactful slam), 'EaseInOut' (smooth sweep), 'EaseIn' (wind-up swing). |
| `time_start` | `float` | Normalized time [0,1] when this primitive begins. Default 0.0. |
| `time_end` | `float` | Normalized time [0,1] when this primitive ends. Default 1.0. |

---
## `OP_MOVE`
- **Class:** `PrimitiveMove`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `Vector3 {x, y}` | The starting local offset from the weapon's pivot point. |
| `end` | `Vector3 {x, y}` | The target local offset the weapon moves toward. |
| `curve` | `string` | Interpolation curve: 'Linear', 'EaseIn', 'EaseOut', 'EaseInOut', 'Overshoot', 'PingPong', 'Loop'. |
| `time_start` | `float` | Normalized time [0,1] when this primitive begins. Default 0.0. |
| `time_end` | `float` | Normalized time [0,1] when this primitive ends. Default 1.0. |

---
## `OP_ROTATE`
- **Class:** `PrimitiveRotate`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `float` | The starting rotation angle in degrees (Z-axis). |
| `end` | `float` | The ending rotation angle in degrees (Z-axis). |
| `curve` | `string` | Interpolation curve: 'Linear', 'EaseIn', 'EaseOut', 'EaseInOut', 'Overshoot', 'PingPong', 'Loop'. |
| `time_start` | `float` | Normalized time [0,1] when this primitive begins. Default 0.0. |
| `time_end` | `float` | Normalized time [0,1] when this primitive ends. Default 1.0. |

---
## `OP_SCALE`
- **Class:** `PrimitiveScale`

### Parameters
| Param | Type | Description |
| :--- | :--- | :--- |
| `start` | `Vector3 {x, y, z}` | The starting scale of the weapon. Defaults to {1, 1, 1}. |
| `end` | `Vector3 {x, y, z}` | The target scale at the end of the motion. |
| `curve` | `string` | Interpolation curve: 'Linear', 'EaseIn', 'EaseOut', 'EaseInOut', 'Overshoot', 'PingPong', 'Loop'. |
| `time_start` | `float` | Normalized time [0,1] when this primitive begins. Default 0.0. |
| `time_end` | `float` | Normalized time [0,1] when this primitive ends. Default 1.0. |

---
