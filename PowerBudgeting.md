# Power Budget Auto-Scaling — 详细说明

---

## 一、目标：什么是 Power Budget？

Power Budget 是一个**随关卡等级增长的目标强度值**，用来衡量每件武器"应该有多强"。

```
target_budget = 10 × level^1.5
```

| Level | Budget |
|-------|--------|
| 1     | 10     |
| 5     | ~111   |
| 10    | ~316   |

武器的实际强度（Power Score）会与这个目标对比，偏差超过 ±10% 就触发自动缩放。

---

## 二、Power Score 如何计算？

### Step 1 — 收集 Payload 操作数据

系统扫描武器绑定的所有 Payload（`on_hit` / `on_attack` / `on_equip`）的 `sequence`，
递归提取以下操作数据：

| 字段 | 来源 |
|------|------|
| `dmg_mult` | `OP_MODIFY_HP` (damage, weapon_multiplier) |
| `flat_dmg` | `OP_MODIFY_HP` (damage, absolute value) |
| `heal_mult` | `OP_MODIFY_HP` (heal, weapon_multiplier) |
| `flat_heal` | `OP_MODIFY_HP` (heal, absolute value) |
| `projectile_count` | `OP_SPAWN_PROJECTILE` (count) |

**特殊处理：**
- `OP_TIMER` 包裹的嵌套操作：乘以实际触发次数 `tick = duration / interval`
- 若存在投射物：`dmg_mult += projectile_count`（假设每颗投射物至少贡献 1.0 倍乘数）
- 若完全没有乘数（纯原始武器）：`dmg_mult = 1.0`（fallback，防止除零）

### Step 2 — 计算有效 DPS（eDPS）

```
cycle_time  = cooldown + duration          # 完整攻击周期（秒）

eDPS_mult   = (base_damage / cycle_time) × dmg_mult
eDPS_flat   = flat_dmg / cycle_time
eDPS_total  = eDPS_mult + eDPS_flat

aoe_factor  = 1 + range × 0.2             # 范围加成（RANGE_WEIGHT = 0.2）
```

### Step 3 — 加入治疗 Utility

```
utility_mult = (heal_mult × base_damage × 2.0) / cycle_time
utility_flat = (flat_heal × 2.0) / cycle_time
total_utility = utility_mult + utility_flat    # HEAL_WEIGHT = 2.0，治疗折算为伤害价值
```

### Step 4 — 最终 Power Score

```
Power Score = (eDPS_total × aoe_factor) + total_utility
```

---

## 三、Auto-Scale 逻辑

```
lower_bound = budget × 0.9
upper_bound = budget × 1.1

if score < lower_bound or score > upper_bound:
    ratio            = budget / score
    base_damage_new  = max(1.0, base_damage_old × ratio)
```

- **仅调整 `base_damage`**，其他属性（攻速、范围、payloads）完全不变
- `base_damage` 最低保底 1.0，防止武器变为 0 伤害
- 双向缩放：过强则压低，过弱则拉高
- 落在 ±10% 容忍带内则不缩放，仅记录 `design_level`

---

## 四、整体流程一览

```
AI 生成武器 JSON
        ↓
WeaponEvaluator.calculate_power_score()   # 算出实际 Power Score
        ↓
get_target_budget(world_level)            # 算出当前关卡目标 Budget
        ↓
score 在 [budget×0.9, budget×1.1] 内？
    ├─ YES → 直接通过，stamp design_level
    └─ NO  → base_damage × (budget / score)，强制对齐
        ↓
输出缩放后的武器 JSON
```

---

## 五、实例计算 — Flaming Sword

> "A flaming sword that slashes forward, dealing **5 HP instant damage** and a **5 HP burning debuff over 3 seconds**."

### 武器基础属性（AI 生成）

| 属性 | 值 |
|------|----|
| `base_damage` | 10 |
| `cooldown` | 0.8 s |
| `duration` | 0.2 s |
| `range` | 1.5 |
| `world_level` | 5 |

### Payload 序列（on_hit）

```
1. OP_MODIFY_HP  → category=damage, source=absolute, value=5
                   → flat_dmg += 5

2. OP_TIMER      → duration=3s, interval=1s  →  tick = 3/1 = 3 ticks
     └─ OP_MODIFY_HP → value=1.67/tick (共 5 HP)
                   → flat_dmg += 1.67 × 3 = 5
```

`flat_dmg = 10`，无 `weapon_multiplier` → `dmg_mult = 1.0`（fallback）

### 逐步计算

```
cycle_time  = 0.8 + 0.2  = 1.0 s

eDPS_mult   = (10 / 1.0) × 1.0  = 10.0
eDPS_flat   = 10 / 1.0           = 10.0
eDPS_total  = 20.0

aoe_factor  = 1 + 1.5 × 0.2     = 1.3

Power Score = 20.0 × 1.3         = 26.0
```

### 对比目标 Budget（level 5）

```
budget      = 10 × 5^1.5  = 111.8

lower_bound = 111.8 × 0.9 = 100.6
upper_bound = 111.8 × 1.1 = 122.9

score 26.0 < 100.6  →  触发 Scale UP

ratio           = 111.8 / 26.0   = 4.3
base_damage_new = 10 × 4.3       = 43.0
```

**结果：** `base_damage` 从 `10` → `43`，其余属性不变，武器强度对齐关卡 5 的预算。

---

## 六、一句话总结

> 系统根据 `10 × level^1.5` 曲线算出目标强度，再根据武器 Payload 的伤害/治疗/范围
> 计算实际 eDPS，两者之比直接乘到 `base_damage` 上，实现双向自动平衡。

---

## 六、PPT 用简洁版（直接复制到 Mathematical Stat Scaling 下面）

**Method:** Compute `Power Score = eDPS × AoE + Utility`, compare against `Budget = 10 × level^1.5`; auto-scale `base_damage` by `budget / score` ratio — bidirectional, ±10% tolerance.
