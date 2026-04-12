# Trace — Pipeline Optimization Log

## Session 2026-03-15

### 优化 1：Surgical Patch（外科手术修复）

**问题**：tech_auditor 失败后整个武器被完整重新生成，但大多数失败只是局部字段问题（错误的 payload ID、超范围 stats），全量重跑浪费 token。

**改动：**
- `app/agents/weapon/graph.py`
  - import 新增 `json`, `ChatPromptTemplate`, `WeaponPatchSchema`, `apply_weapon_patch`
  - `__init__` 新增 `patch_chain`：`ChatPromptTemplate` + `llm_service.model.with_structured_output(WeaponPatchSchema)`，prompt 要求 LLM 只输出需要改的字段
  - 新增 `patch_node()` 方法：读取 `tech_feedback` + 原始武器，调用 patch chain，用 `apply_weapon_patch` 合并，出错时保底返回原始武器
- `app/core/workflow.py`
  - 注册 `weapon_patcher` 节点（`weapon_agent.patch_node`）
  - `tech_gatekeeper` 失败路由改为 `weapon_patcher`（不再重跑完整 `weapon_designer`）
  - 新增 edge：`weapon_patcher → tech_auditor`

---

### 优化 2：Gatekeeper 强制放行改造

**问题**：原 gatekeeper 在超过重试次数后直接绕过审核强制放行，导致 reviewer 形同虚设；tech_gatekeeper 原上限 2 次与 tech_auditor 的 LAX 模式（attempt ≥ 2）语义冲突。

**改动：**
- `app/core/workflow.py`
  - `idea_gatekeeper`：重试上限从 1 次提至 2 次；区分"返工日志"和"强制放行日志"
  - `tech_gatekeeper`：移除原强制跳过逻辑；失败统一路由至 `weapon_patcher`；安全网上限提至 3 次；依赖 LAX 模式自然通过

---

### 优化 3：generation_history 截断

**问题**：`generation_history` 无界增长，注入 prompt 后 token 会随游戏进行持续膨胀。

**改动：**
- `app/agents/designer/graph.py`：读取 history 时加 `[-20:]` 截断
- `app/agents/weapon/graph.py`：`crafting_node` 读取 history 时加 `[-20:]` 截断

---

### 优化 4：engine_manual State 缓存统一

**问题**：`crafting_node` 和 `tech_audit_node` 每次都重新从磁盘加载 engine manual，产生重复 I/O。`designer` 已有 state 缓存逻辑但其他节点未跟进。

**改动：**
- `app/core/state.py`：新增 `engine_manual: Optional[str]` 字段
- `app/agents/weapon/graph.py`：`crafting_node` 和 `patch_node` 优先读 `state["engine_manual"]`，miss 时才调用 `engine_docs_manager`
- `app/agents/reviewer/graph.py`：`tech_audit_node` 同上

---

### 功能：RAG — DB 武器历史注入 Pipeline

**目标**：用 MongoDB 持久化武器历史（跨 session），每次生成前将所有已有武器的轻量摘要注入 designer，防止重复设计和风格漂移。

**新 Pipeline 流程：**
```
START → db_retrieval → designer → concept_reviewer
                                       ↓
                                  weapon_designer → tech_auditor
                                                       ↓ (pass) → save to DB → END
                                                       ↓ (fail) → weapon_patcher → tech_auditor → ...
```

**改动：**

- `app/models/schemas.py`
  - `WeaponSchema` 新增 `summary: str` 字段，LLM 在生成武器时同步输出一句话描述

- `app/models/mongo/weapon.py`
  - `WeaponDocument` 新增顶层元数据字段：`biome`, `level`, `primary_payload`, `summary`（用于查询时的轻量投影，避免解析完整 content）

- `app/core/state.py`
  - 新增 `session_id: Optional[str]`（调用方在 `ainvoke` 时传入）
  - 新增 `reference_weapons: Optional[List[Dict]]`（`db_retrieval_node` 写入，designer 读取）

- `app/services/mongo_service/weapon_services.py`
  - `save_generated_weapon()` 新增 `biome`, `level` 参数；自动从 abilities 提取 `primary_payload`；存储 `summary`
  - 新增 `get_all_summaries()`：只投影 `id`, `name`, `biome`, `level`, `primary_payload`, `summary`，返回轻量列表（上限 500 条）

- `app/core/workflow.py`
  - 新增 `db_retrieval_node` 顶层异步函数：调用 `get_all_summaries()` 写入 `state["reference_weapons"]`
  - 注册为图节点 `"db_retrieval"`
  - 边改为 `START → db_retrieval → designer`

- `app/agents/designer/graph.py`
  - 用 `state["reference_weapons"]` 替换 `generation_history` 构建 `past_weapons` 字符串
  - 格式：`[id] Name (Biome, Payload, LvN): summary`

- `app/agents/reviewer/graph.py`
  - `tech_audit_node` 通过时调用 `weapon_mongo_service.save_generated_weapon()` 存档（替代旧的内存 `generation_history` append）
  - 移除旧的 `generation_history` 追加逻辑

- `app/core/prompts/designer.yaml`
  - `Memory (Past Creations)` 段落改为 `Reference Arsenal (Existing Weapons — DO NOT DUPLICATE)`，加入格式说明引导 LLM 解读

**调用方变更**：`global_graph.ainvoke()` 的初始 state 需传入 `session_id`：
```python
await global_graph.ainvoke({
    ...,
    "session_id": "some_session_id",
})
```

---

## Session 2026-03-15 (续)

### 功能：原子化 Payload 系统重设计

**时间戳：** 2026-03-15

**背景**：旧 payload（7 个）是捆绑式设计（一个 payload 内嵌多种效果），导致复合效果难以组合、payload 库增长迅速。改为原子化设计：每个 payload 只做一件事，武器通过 `on_hit`/`on_attack`/`on_equip` 组合 2-3 个 payload。

**删除旧 payload（7 个）：**
`payload_fire_burn`, `payload_ice_freeze`, `payload_gravity_pull`, `payload_heal_from_damage`, `payload_blood_frenzy`, `payload_heavy_smash`, `payload_toxic`

**新增原子 payload（13 个）：**

| ID | 效果 |
|---|---|
| `payload_strike` | 即时物理伤害 |
| `payload_magic_bolt` | 即时魔法伤害 |
| `payload_dot_fire` | 火焰 DOT：0.25× 每秒，持续 5 秒 |
| `payload_dot_poison` | 毒素 DOT：0.167× 每秒，持续 6 秒 |
| `payload_dot_bleed` | 流血 DOT：0.25× 每 0.5 秒，持续 3 秒 |
| `payload_drain` | 魔法伤害 + 自身回血（生命汲取） |
| `payload_sacrifice` | 自伤（sacrifice tag），用于血魔组合代价 |
| `payload_knockback` | 击退（远离撞击点） |
| `payload_pull` | 拉拽（朝向施法者） |
| `payload_slow` | 目标减速 50%，持续 3 秒 |
| `payload_freeze` | 目标减速至 10%，持续 2 秒（近似定身） |
| `payload_haste` | 自身加速 2×，持续 3 秒 |
| `payload_recoil_dash` | 命中时自身向后弹飞（打了就跑） |

**模型改动：**

- `app/models/schemas.py`
  - `AvailablePayloads` Literal 替换为 13 个原子 ID
  - `Abilities.on_hit` 上限 1→3；`on_equip` 上限 1→2；新增 `on_attack`（上限 2），所有字段 `default_factory=list`

- `app/models/primitive_schemas.py`（完整重写）
  - `ModifyHPParams`：value 恒为正数，新增 `source`（`weapon_multiplier`/`absolute`），`category`（`damage`/`heal`/`self_damage`），`target_type`；删除 `is_percentage`
  - 新增 `SpawnProjectileParams` + `PrimitiveSpawnProjectile`（`OP_SPAWN_PROJECTILE`）
  - `AnyLogicPrimitive` union 更新

- `app/models/motion_primitive_schemas.py`（完整重写）
  - `CurveType` 扩展：新增 `EaseIn`, `EaseInOut`, `Overshoot`
  - 所有 motion params 新增 `time_start: float = 0.0` 和 `time_end: float = 1.0`
  - 新增 `ArcParams` + `PrimitiveArc`（`OP_ARC`）：`radius`, `start_angle`, `end_angle`, `curve`, `time_start`, `time_end`
  - `MoveParams.start/end` 改为 `dict`（对齐 Unity JSON 格式）
  - `AnyMotionPrimitive` union 加入 `PrimitiveArc`

- `app/models/schemas.py`
  - `WeaponStats` 新增字段：`base_damage`, `design_level`, `hit_start`, `hit_end`

---

### 功能：Unity Schema 同步 + Summarizer 更新

**时间戳：** 2026-03-15

**背景**：Unity 侧更新了 Primitives、Motions、Weapon、Projectile Schema，Python 侧需完整同步，并将新 schema 注入 AI 生成的 `instruction_manual.md`。

**Schema 文件迁移：**
- `app/data/PrimitivesSchema.md` → `app/data/unity_schema/PrimitivesSchema.md`
- `app/data/MotionPrimitivesSchema.md` → `app/data/unity_schema/MotionPrimitivesSchema.md`
- 新增 `app/data/unity_schema/WeaponSchema.md`
- 新增 `app/data/unity_schema/ProjectileSchema.md`

**新增 Python 模型：**
- `app/models/schemas.py`：`ProjectileStats`, `ProjectileAbilities`, `ProjectileSchema`

**`app/core/config.py`（用户已完成）：**
- 路径指向新 `unity_schema/` 目录
- 新增 `WEAPON_SCHEMA_PATH` 和 `PROJECTILE_SCHEMA_PATH`

**`app/services/engine_docs_manager.py`：**
- `refresh_manual()` 末尾追加 Weapon / Projectile schema 的原始 Markdown 内容（通过 `primitive_registry.get_weapon_schema()` / `get_projectile_schema()`）

**Summarizer Prompt 更新：**
- `app/core/prompts/primitive_desc.yaml`：新增 OP_MODIFY_HP、OP_SPAWN_PROJECTILE、OP_ARC、time_start/time_end 的准确性注释
- `app/core/prompts/payload_desc.yaml`：新增 OP_MODIFY_HP 解读指南（weapon_multiplier vs absolute、category 含义）

**Bug 修复：GBK 编码崩溃（Windows）：**
- 现象：`load_prompt()` 默认使用系统编码（GBK），读取含特殊字符的 UTF-8 YAML 时崩溃
- `app/agents/summarizer/graph.py`：两处 `load_prompt()` 调用均添加 `encoding=settings.ENCODING`

---

### 功能：Payload Factory（按需生成新 Payload）

**时间戳：** 2026-03-15

**背景**：当 Designer 设计的武器概念找不到合适的已有 payload 时，pipeline 需要一条分支来动态生成并持久化新的原子 payload。

**新 Pipeline 分支：**
```
concept_reviewer → idea_gatekeeper
                       ├── needs_new_payload=True → payload_factory → weapon_designer
                       └── needs_new_payload=False → weapon_designer（原路径）
```

**改动：**

- `app/models/schemas.py`
  - `AvailablePayloads` 从 `Literal[...]` 改为 `str`，支持运行时动态 payload ID

- `app/agents/designer/graph.py`
  - 新增 `NewPayloadSpec` 模型（`id`, `description`, `primitive_hint`）
  - `DesignBlueprint` 新增字段：`needs_new_payload: bool`（默认 False），`new_payload_spec: Optional[NewPayloadSpec]`

- `app/core/state.py`
  - 新增 `pending_payload_id: Optional[str]`（记录本轮 factory 创建的 payload ID）

- `app/agents/payload_factory/graph.py`（新建）
  - `PayloadFactoryAgent`：读取 `design_concept.new_payload_spec`，通过 LLM 生成 `GeneratedPayload`（含 `factory_reasoning`, `id`, `description`, `sequence`）
  - 将生成的 payload 保存至 `app/data/payloads/{id}.json`
  - 将新 payload 描述追加到 `state["engine_manual"]`，下游节点（`weapon_designer`）立即可用新 ID
  - 单例：`payload_factory_agent`

- `app/core/prompts/payload_factory.yaml`（新建）
  - 严格规则：ATOMIC（单一效果）、OP_MODIFY_HP value 恒为正、OP_TIMER 用于 DOT、禁止编造 primitive ID

- `app/core/workflow.py`
  - 注册 `payload_factory` 节点（`payload_factory_agent.generate_node`）
  - `idea_gatekeeper` 扩展路由：`needs_new_payload=True` → `"payload_factory"`
  - `conditional_edges` 新增 `"payload_factory"` 目标
  - 新增 edge：`payload_factory → weapon_designer`

- `app/core/prompts/designer.yaml`
  - 新增 **Payload Factory Rules** 段落：默认使用已有 payload；仅在现有库无法表达核心机制时设 `needs_new_payload: true`；提供 `new_payload_spec` 填写规范

---

## Session 2026-03-16

### 功能：相近武器参考 + Payload 复用引导

**时间戳：** 2026-03-16

**背景**：`db_retrieval_node` 原先将全库武器一并注入 designer，没有区分"相近"与"全库"，LLM 无法感知哪些 payload 在当前 biome/level 已被充分覆盖，也无法主动优先复用已有 payload。

**新 Pipeline 步骤：**
```
db_retrieval_node
 ├── get_all_summaries()   → reference_weapons（全库，防重名）
 └── get_similar_weapons() → similar_weapons（同 biome，按 level 距离排序，含完整 abilities）
```

**改动：**

- `app/services/mongo_service/weapon_services.py`
  - 新增 `get_similar_weapons(biome, level, limit=6)`：按 biome 过滤，Python 侧按 level 距离排序，返回含 `content.name` + `content.abilities` 的轻量文档

- `app/core/state.py`
  - 新增 `similar_weapons: Optional[List[Dict[str, Any]]]`

- `app/core/workflow.py`
  - `db_retrieval_node` 同时调用 `get_similar_weapons()`，将结果写入 `state["similar_weapons"]`

- `app/agents/designer/graph.py`
  - 将 `similar_weapons` 格式化为含完整 payload combo 的字符串，末尾附 `Payloads proven in this biome: ...` 提示行
  - 全库 `reference_weapons` 仍保留，格式精简为 ID + 名称 + summary
  - 两份字符串分别注入 chain 的 `similar_weapons` 和 `past_weapons` 变量

- `app/core/prompts/designer.yaml`
  - 将原 `Reference Arsenal` 单一区块拆为两个区块：
    - `Similar Weapons — Highest Duplication Risk`（含 payload combo，重点参考）
    - `Full Arsenal — All Existing Weapons`（防重名）

---

### Bug 修复：调用链隐藏 Bug（6 处）

**时间戳：** 2026-03-16

| # | 文件 | 问题 | 严重度 |
|---|------|------|--------|
| 1 | `app/agents/weapon/graph.py:93` | `state["generation_history"]` 在初始 state 未包含该 key 时 KeyError → 改为 `state.get("generation_history", [])` | Critical |
| 2 | `app/agents/designer/graph.py` | `state.get("user_request")` 不存在，state key 是 `"prompt"` → 用户 prompt 永远是 "None" | Critical |
| 3 | `app/agents/designer/graph.py` | `state.get("review_feedback")` 不存在，state key 是 `"idea_feedback"` → Idea retry 时反馈永远是 "None" | Critical |
| 4 | `app/services/mongo_service/weapon_services.py:57` | `primary_payload` 提取只查 `on_hit`/`on_equip`，漏掉 `on_attack` → 远程武器存 None | Critical |
| 5 | `app/websocket/handlers.py` | `ainvoke` 缺少 `retry_count=0`, `audit_attempts=0`, `generation_history=[]`, `session_id` → bug #1 必触发 | Critical |
| 6 | `app/core/state.py:15` | `design_concept: str` 类型注解错误，实际为 dict → 改为 `Optional[Dict[str, Any]]` | Medium |

---

### 功能：Artist 节点（并行图标生成接口）

**时间戳：** 2026-03-16

**背景**：为未来接入 AI 图标生成（Stable Diffusion / DALL-E 等）预留接口。Artist 与 `weapon_designer` 并行运行，当前为 stub，返回固定占位图标。

**新 Pipeline 结构：**
```
concept_reviewer → idea_gatekeeper
                       ├── needs_new_payload=True → payload_factory → forge_fork
                       ├── retry → designer
                       └── pass  → forge_fork

forge_fork ─┬─→ weapon_designer ─→ tech_auditor
            └─→ artist (stub)       ↑
                                    │
               weapon_patcher ──────┘  (repair loop，artist 不重复执行)
```

**并行机制**：`forge_fork` 是一个 no-op 节点，LangGraph 从它发出两条静态 edge。两个目标节点在同一 superstep 内并行执行，superstep 结束时 state merge，`tech_auditor` 在下一 superstep 获得两者的合并结果。`weapon_patcher → tech_auditor` 路径不经过 `forge_fork`，artist 不会重复执行。

**改动：**

- `app/agents/artist/graph.py`（新建）
  - `ArtistAgent.generate_icon_node`：读取 `design_concept.codename` 打印日志，返回 `{"generated_icon": "weapon_axe.png"}`（stub）
  - TODO 注释标明后续替换为真实图像生成

- `app/agents/artist/__init__.py`（新建，空文件）

- `app/core/state.py`
  - 新增 `generated_icon: Optional[str]`

- `app/core/workflow.py`
  - 注册 `forge_fork` 节点（`lambda state: {}`，no-op）
  - 注册 `artist` 节点（`artist_agent.generate_icon_node`）
  - `idea_gatekeeper` pass 路由从 `"weapon_designer"` 改为 `"forge_fork"`
  - `payload_factory → forge_fork`（替换原 `payload_factory → weapon_designer`）
  - 新增静态 edge：`forge_fork → weapon_designer`、`forge_fork → artist`

- `app/websocket/handlers.py`
  - `output_data["icon"]` 改为优先读 `final_state.get("generated_icon")`，fallback 到 weapon 自带 icon，再 fallback 到 `"weapon_axe.png"`

**后续接入方式**：只需修改 `app/agents/artist/graph.py` 中的 `generate_icon_node`，workflow 无需任何改动。

---

## Session 2026-03-16 (续二)

### 功能：Payload Validator 节点（纯代码 payload ID 验证）

**时间戳：** 2026-03-16

**背景**：`weapon_designer` 有时会从 `core_mechanic` 描述文本中复制不存在的 payload ID，三重防御：validator 节点（代码）、`weapon_crafter.yaml` 提示、`tech_auditor.yaml` LAX 模式禁令。

**改动：**

- `app/core/state.py`
  - 新增 `payload_valid: Optional[bool]`

- `app/core/workflow.py`
  - 新增 `payload_validator_node`（纯 Python，无 LLM）：提取武器 abilities 中所有 payload ID，与 `primitive_registry.get_all_payloads()` 对比，发现非法 ID 则写入 `tech_feedback` 并置 `payload_valid=False`
  - 新增 `payload_validator` 节点
  - `weapon_designer → payload_validator`（替换原 `weapon_designer → tech_auditor`）
  - 新增 `payload_validator_gate`：`payload_valid=False` → `weapon_patcher`，else → `tech_auditor`

- `app/core/prompts/weapon_crafter.yaml`
  - 加强 payload 选择说明：明确忽略 `core_mechanic` 里不存在于 Payload Catalog 的名称

- `app/core/prompts/tech_auditor.yaml`
  - LAX 模式新增绝对规则：非法 payload ID 无论 strictness 等级均为 CRITICAL failure

---

### 功能：Designer keywords 主题锁定

**时间戳：** 2026-03-16

**背景**：weapon_designer 有时产出与主题相悖的 payload（火焰武器出冰矛）。在 DesignBlueprint 增加 `keywords` 字段，作为绑定约束传入 weapon_crafter。

**改动：**

- `app/agents/designer/graph.py`
  - `DesignBlueprint` 新增 `keywords: List[str]` 字段（3-5 个单词主题标签）

- `app/agents/weapon/graph.py`
  - `crafting_node` 提取 `design_concept.keywords`，拼为 `keywords_str` 注入 chain

- `app/core/prompts/weapon_crafter.yaml`
  - 新增 **Theme Keywords (BINDING CONSTRAINT)** 段落，要求武器名称/payload/动作/描述全部反映所有 keywords

---

### 功能：模型配置文件（model_config.yaml）

**时间戳：** 2026-03-16

**背景**：各 Agent 通过代码注释切换模型，需要重新部署才能调整。改为外部 YAML 配置文件，无需改代码。

**改动：**

- `app/core/model_config.yaml`（新建）
  - 每行格式 `agent_name: model_key`，合法值：`model` / `mini_model` / `gpt_model`

- `app/core/config.py`
  - 新增 `MODEL_CONFIG_PATH = CORE_DIR / "model_config.yaml"`

- `app/services/llm_service.py`
  - `__init__` 加载 `model_config.yaml` 到 `_agent_model_map`
  - 新增 `get_model(agent: str)` 方法：查 map 返回对应模型实例，缺省返回 `self.model`

- 所有 Agent 的 `__init__` 替换硬编码模型引用：
  - `designer/graph.py` → `llm_service.get_model("designer")`
  - `reviewer/graph.py` → `llm_service.get_model("concept_reviewer")` + `"tech_auditor"`
  - `weapon/graph.py` → `llm_service.get_model("weapon_crafter")` + `"weapon_patcher"`
  - `payload_factory/graph.py` → `llm_service.get_model("payload_factory")`
  - `summarizer/graph.py` → `llm_service.get_model("summarizer")`

---

### 功能：Weapon Presets 更新（有效 payload 替换）

**时间戳：** 2026-03-16

**背景**：`app/data/weapon_presets/` 下 17 个武器预设仍引用旧的/不存在的 payload ID（如 `payload_fire_burn`, `payload_heavy_smash`），全部替换为 13 个原子 payload 的组合。同时将所有 `duration` 统一至 0.3–0.6 合理范围。

**改动：**

- `app/data/weapon_presets/*.json`（17 个文件全部更新）
  - 所有 `abilities` 字段替换为合法 payload ID 组合，新增 `on_attack: []` 字段
  - 所有 `duration` 值 clamp 至 0.3–0.6（按武器速度分档：快 0.3、中 0.45、重 0.6）
  - `weapon_inferno_lance.json` 额外清理 LLM 泄漏的 `manual_analysis` / `stat_balance_reasoning` 字段

---

### Bug 修复：Pydantic 序列化警告（motions/visual_stats）

**时间戳：** 2026-03-16

**现象**：`apply_weapon_patch` 中用 `WeaponSchema(**original_json)` 构造时，Pydantic 对 `motions`（discriminated union）和 `visual_stats` 的嵌套 dict 不做深层验证，导致 `model_dump()` 时报 `PydanticSerializationUnexpectedValue`。

**改动：**

- `app/models/schemas.py`
  - `apply_weapon_patch` 中 `WeaponSchema(**original_json)` → `WeaponSchema.model_validate(original_json)`

---

### Bug 修复：Payload Factory 多项 LLM 幻觉修复

**时间戳：** 2026-03-16

**问题 1 — `target` 字段幻觉**：LLM 生成 `"target": "ctx.Target"` 而非 `"target_type": "target"`。
**问题 2 — `value` 字符串幻觉**：LLM 生成 `"value": "${shadow_energy_absorbed}"` 等模板变量。
**问题 3 — ATOMIC 规则违反**：LLM 在单个 payload 内捆绑多个效果。
**问题 4 — 非法 `OP_` primitive**：`primitive_hint` 中出现 `OP_DOT`、`OP_CHAIN` 等幻造名称。
**问题 5 — `payload_factory.yaml` 模板冲突**：`${anything}` 被 LangChain PromptTemplate 当作变量。

**改动：**

- `app/core/prompts/payload_factory.yaml`
  - `OP_MODIFY_HP` 规则：明确 value 必须为正数 float literal，`target_type` 只能是 `"self"` 或 `"target"`，字段名禁止用 `target`
  - ATOMIC 规则加反例："poisonous fireball" 是两个效果 → 两个 payload
  - `${anything}` → `${{anything}}`（转义花括号）

- `app/agents/payload_factory/graph.py`
  - `PrimitiveEntry` 新增 `validate_and_sanitize` validator：
    - 自动将 `target` → `target_type`，值映射到 `"self"` 或 `"target"`
    - 非法 `target_type` 值强制改为 `"target"`
    - `OP_MODIFY_HP.value` 非数字时抛 `ValueError`

- `app/agents/designer/graph.py`
  - `NewPayloadSpec.primitive_hint` 描述加白名单：仅 5 个合法 primitive
  - 新增 `NewPayloadSpec.sanitize_primitive_hint` validator：正则扫描 `OP_XXX`，非白名单的替换为 `OP_MODIFY_HP`
  - `_VALID_PRIMITIVES` 常量：`{OP_MODIFY_HP, OP_TIMER, OP_APPLY_FORCE, OP_MODIFY_SPEED, OP_SPAWN_PROJECTILE}`

---

### Bug 修复：Designer 输出 keywords 污染 + needs_new_payload 漏填

**时间戳：** 2026-03-16

**问题 1 — keywords 污染**：LLM 将整个推理过程的技术词汇（`payload_dot_dark_poison`、`OP_DOT`、`needs_new_payload`、`true` 等）塞入 `keywords` 列表，导致输出死循环。
**问题 2 — needs_new_payload 漏填**：`new_payload_spec` 有值但 `needs_new_payload=False`，pipeline 路由跳过 factory 节点。

**改动：**

- `app/agents/designer/graph.py`
  - `DesignBlueprint.sanitize_blueprint` validator（合并 keywords 清理 + flag 自动修正）：
    - 自动将含 `new_payload_spec` 但 `needs_new_payload=False` 的情况修正为 `True`
    - 过滤 keywords 中含空格、超 20 字符、以 `payload_`/`op_`/`needs_`/`source` 等开头的词
    - 最多保留 5 个，全部被过滤时回退 `["elemental", "melee"]`
  - validator 从字段间迁移到 class 末尾（结构规范化）

---

### 功能：New Payload 随武器数据一并返回 Unity

**时间戳：** 2026-03-16

**背景**：PayloadFactory 动态生成的 payload 需要同步给 Unity 客户端。选择随武器数据合并返回（而非单独发一条 WebSocket），保证原子性，避免竞态。

**改动：**

- `app/core/state.py`
  - `pending_payload_id: Optional[str]` → `pending_payload_ids: Optional[List[str]]`（支持多个）

- `app/websocket/protocol.py`
  - `WeaponGenerateEvent` 新增 `new_payloads: Optional[List[Dict[str, Any]]] = None`
  - 补 `List` import

- `app/websocket/handlers.py`
  - 遍历 `pending_payload_ids`，逐一读取 `app/data/payloads/{id}.json`，收集为列表
  - 赋值给 `WeaponGenerateEvent.new_payloads`，空列表时发 `null`

- `app/agents/payload_factory/graph.py`
  - 返回时追加到已有列表：`existing_ids + [final_id]`

---

### 优化：duration 硬性限制 0.3–0.6

**时间戳：** 2026-03-16

**背景**：LLM 生成的武器 duration 普遍偏大（出现 3.0、5.5 等值），严重影响游戏手感。

**改动：**

- `app/core/prompts/weapon_crafter.yaml`
  - `Stats Generation Rules` 新增 `duration` 一行：`HARD LIMIT 0.3–0.6 seconds`，附三档参考值（快 ~0.3、中 ~0.45、重 ~0.6）

- `app/models/schemas.py`
  - `WeaponStats.duration` field description 更新为 `MUST be 0.3–0.6`
  - 新增 `@field_validator("duration")`：`max(0.3, min(0.6, v))`，任何超范围值在实例化时自动 clamp

---

## Session 2026-03-17

### 架构：MongoDB 作为 Source of Truth（Payload / Projectile）

**时间戳：** 2026-03-17

**背景**：payload 和 projectile 原先仅存于本地磁盘平铺目录，preset 与生成物混在一起，无法按 session 隔离。改为以 MongoDB 为读写主路径，本地文件降级为备份；registry 使用 in-memory cache 保持同步读取接口不变，兼容 Pydantic validator 等无法 await 的场景。

**新目录结构：**
```
app/data/
├── payloads/
│   ├── presets/         ← 固定 preset（启动时写入 DB session_id="SYSTEM"）
│   └── {session_id}/    ← 生成物本地备份（非主路径）
├── projectiles/
│   ├── presets/
│   └── {session_id}/
└── weapon_presets/      ← 不变
```

**改动：**

- `app/core/config.py`
  - 新增 `PAYLOADS_PRESET_PATH = DATA_DIR / "payloads" / "presets"`
  - 新增 `PROJECTILES_PRESET_PATH = DATA_DIR / "projectiles" / "presets"`

- `app/models/mongo/payload.py`（完整实现，原为空文件）
  - `PayloadDocument`：`id`, `session_id="SYSTEM"`, `is_preset`, `content`（完整 payload JSON）, `last_synced`

- `app/models/mongo/projectile.py`（新建）
  - `ProjectileDocument`：同上结构

- `app/services/mongo_service/payloads_services.py`（完整重写，原为残缺骨架）
  - `load_preset_payloads()`：扫描 `PAYLOADS_PRESET_PATH`，批量 upsert 至 `payloads` 集合，`session_id="SYSTEM"`
  - `save_generated_payload(session_id, payload_data)`：存生成物，绑定 session_id
  - `get_all_payloads(session_id=None)`：返回 SYSTEM + 指定 session 的 content 列表
  - `get_session_payloads(session_id)`：仅返回指定 session 生成物（供 handlers 发回 Unity）

- `app/services/mongo_service/projectiles_services.py`（新建）
  - 同上结构，操作 `projectiles` 集合

- `app/services/primitive_registry.py`（重构）
  - 新增 `_payload_cache: dict` 和 `_projectile_cache: dict`
  - 新增 `async initialize(session_id=None)`：从 MongoDB 加载 presets 到 cache，startup 时调用
  - 新增 `add_payload(id, data)` / `add_projectile(id, data)`：factory 生成后立即更新 cache
  - `get_all_payloads()` / `get_all_projectiles()`：优先读 cache，cache 为空时 fallback 到磁盘扫描（保证测试兼容）

- `app/agents/payload_factory/graph.py`
  - 生成后存盘路径改为 `PAYLOADS_PATH / session_id / {id}.json`（session 隔离备份）
  - 新增：`payload_mongo_service.save_generated_payload(session_id, payload_dict)`
  - 新增：`primitive_registry.add_payload(final_id, payload_dict)`（pipeline 内立即可查）

- `app/agents/projectile_factory/graph.py`
  - 存盘路径改为 `PROJECTILES_PATH / session_id / {id}.json`
  - 新增：`projectile_mongo_service.save_generated_projectile(session_id, projectile_dict)`
  - 新增：`primitive_registry.add_projectile(final_id, projectile_dict)`

- `app/websocket/handlers.py`
  - 移除旧的本地文件读取逻辑（`open(PAYLOADS_PATH / f"{pid}.json")`）
  - 改为调用 `payload_mongo_service.get_session_payloads(session_id)` + id 过滤
  - 同理处理 projectile

- `app/websocket/main.py`
  - 新增启动序列：
    ```python
    await payload_mongo_service.load_preset_payloads()
    await projectile_mongo_service.load_preset_projectiles()
    await primitive_registry.initialize()
    ```

**关键设计决策：**
- `primitive_registry.get_all_payloads()` 保持同步接口不变，Pydantic validator 无需改动
- Cache 为进程级全局（非 session 隔离），payload_factory 生成后立即追加，`payload_validator_node` 在同一 pipeline run 内可见新 ID
- DB 存储按 session_id 隔离，handlers 按 session 查询发回 Unity，保证数据一致性
- 本地文件仅作灾难恢复备份，不再是读取主路径

---

### 功能：各节点 Prompt 日志记录

**时间戳：** 2026-03-17

**背景**：需要浏览每个 LLM 节点实际发出的完整 prompt，用于 debug 和质量评估。

**改动：**

- `app/utils/callbacks.py`
  - 新增 `PromptLogCallback`：拦截 `on_chat_model_start` 和 `on_llm_start`，将消息按 `[SYSTEM]/[HUMAN]` 分块写入 `logs/prompts/{session_id}/{ts}_{agent_name}.txt`
  - 新增 `make_callbacks(agent_name, session_id)` helper：返回 `[AgentConsoleCallback, PromptLogCallback]`
  - `AgentConsoleCallback` 补充 `on_chat_model_start`（chat model 不触发 `on_llm_start`）

- 所有 Agent（designer / weapon / reviewer / payload_factory / projectile_factory / summarizer）
  - 将 `[AgentConsoleCallback(agent_name="X")]` 替换为 `make_callbacks("X", state.get("session_id", "default"))`

---

### 优化：Designer 减少冗余 Prompt 注入

**时间戳：** 2026-03-17

**背景：**
1. Designer `planning_node` 调用 `get_markdown_manual()`（完整手册），但 designer 只需 Payload Catalog；Constitution 已由 `inject_prompts` 注入，导致重复；Weapon/Projectile Schema 对 designer 无用。
2. `_WEAPON_KEEP` 保留了 `abilities` 字段，同 biome 武器的 payload 组合在 `{weapons}` 和 `{similar_weapons}` 中重复出现两次。

**改动：**

- `app/agents/designer/graph.py`
  - `engine_manual_md = await engine_docs_manager.get_reviewer_manual()` （Payload Catalog only，~70% token 节省）
  - `available_projectiles` 字符串去掉 `on_hit` 字段（designer 阶段不需要）

---

### 数据修复：instruction_manual.md 质量问题

**时间戳：** 2026-03-17

**问题：**
1. `payload_venom_tether.json` 的 `OP_APPLY_FORCE` 和 `OP_MODIFY_HP` params 为 null，Summarizer LLM 无法区分与 `payload_toxic_vortex`，导致生成完全相同的 Logic 描述
2. `payload_shadow_fire_burst` 因 Summarizer token 截断被漏掉，Catalog 只有 18/19 个 payload
3. `WeaponSchema.md` 的 Melee 示例中使用了不存在的 `payload_fire_burn`（正确应为 `payload_dot_fire`）

**改动：**

- `app/data/payloads/payload_venom_tether.json`
  - `OP_APPLY_FORCE` params: `magnitude=10.0, direction_mode="FromHitPoint", target_type="target"`
  - `OP_MODIFY_HP` params: `value=0.15, source="weapon_multiplier", category="damage", target_type="target", tag="poison"`

- `app/data/unity_schema/WeaponSchema.md`
  - 示例中 `"payload_fire_burn"` → `"payload_dot_fire"`

- `app/agents/summarizer/graph.py`
  - 生成后新增 post-validation：检测缺失 payload ID 和重复 `combination_logic`，打印警告

- 删除 `app/data/instruction_manual.md` 并重新生成，确认：全部 19 个 payload 入 Catalog，`venom_tether` 与 `toxic_vortex` 描述已区分

---

### 功能：Artist 节点请求日志

**时间戳：** 2026-03-17

**背景：** 需要记录每次 SD 图像生成的 prompt、耗时和 token 估算，便于调试 ControlNet 效果。

**改动：**

- `app/agents/artist/graph.py`
  - `_write_log(prompt, negative_prompt, output_path, error, timing, tokens)` 写入 `logs/artist/{ts}.json`
  - `timing_secs`：`prompt_build`, `template_load`, `sd_call`, `save_icon`, `total`（使用 `time.perf_counter()`）
  - `tokens`：`prompt_words`, `negative_prompt_words`, `prompt_chars`（CLIP token 估算）
  - 控制台打印 `sd=Xs total=Xs`
