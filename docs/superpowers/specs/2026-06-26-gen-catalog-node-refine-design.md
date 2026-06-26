# 设计规格：gen-catalog 节点完善两步化（plan → apply）

**版本**: 1.0  
**日期**: 2026-06-26  
**状态**: 待审阅  
**Feature ID**: `007-tender-generate-node-refine-v2`  
**前置**: `007-tender-generate`（`docs/superpowers/specs/2026-06-25-tender-generate-design.md`）

---

## 1. 概述

将 `gen-catalog` 的**节点完善步**（原 `gen_catalog_node`）从单步 LLM「片段 + 目录树 → 新目录树」改为**两步门控**：

1. **Plan**：招标概要 + 当前目录树 + 片段 → `{needs_optimization, refinement_plan}`
2. **Apply**（仅当 `needs_optimization=true`）：招标概要 + 当前目录树 + 片段 + 优化方案 → `{outline, changes_summary}`

`needs_optimization=false` 时跳过 Apply，目录树不变，节点标记完成。

`gen_catalog_initial`（初始目录生成）**不变**。

**硬约束**：不修改 `doc_chunk`；变更限于 `tender_insights/gen_catalog` 及关联测试、Viewer 进度文案（如有）。

**范围外**：`gen_catalog_initial` 提示词调整、interpret 分段目录增量更新、手工编辑目录 UI。

---

## 2. 已确认决策

| 决策点 | 选择 |
|--------|------|
| 改造范围 | 仅 `gen_catalog_node` 节点完善步 |
| `needs_optimization=false` | 完全跳过 Apply；树不变；节点记入 `completed_steps` |
| 招标概要 | 仅 `tender_brief.json`（`summary_text` + `fields` 五字段） |
| Plan 输入 | 招标概要 + 当前目录树 + 片段（最精简，不含废标/评分/模板） |
| Apply 输入 | 与 Plan 相同共享前缀 + `## 优化或细化方案` + 执行任务尾段 |
| 提示词分层 | **单一 System** + **User 共享前缀** + **User 任务尾段**（差异仅末尾） |
| 步进计数 | `step_index` / `step_total` 仍按**节点**计，不按 LLM 调用次数膨胀 |
| `mode=step` | 每处理完一个节点（Plan + 可选 Apply）后暂停 |

---

## 3. 流水线

```text
gen_catalog_initial（不变）
    ↓
for each node_id in node_queue（前序遍历，跳过 completed_steps）:
    excerpt = pick_node_excerpt(source_md, node_title, …)

    Plan:  LLM(call_type=gen_catalog_node_plan)
           → { needs_optimization, refinement_plan }

    if not needs_optimization:
        completed_steps += [node_id]
        continue                        # draft.root 不变

    Apply: LLM(call_type=gen_catalog_node_apply)
           → { outline, changes_summary }
           draft.root = outline
           completed_steps += [node_id]

    [mode=step] 暂停
    ↓
status = awaiting_accept → accept → bid_outline.json
```

---

## 4. 提示词架构（前缀缓存）

### 4.1 分层原则

Plan 与 Apply 的 `messages` 满足：

| 部分 | Plan | Apply | 共享 |
|------|------|-------|------|
| System | `GEN_CATALOG_NODE_SYSTEM` | 同左 | ✅ |
| User 前三节 | 概要 + 树 + 摘录 | 同左 | ✅ |
| User 末尾 | 评估任务 + schema | 方案 + 执行任务 + schema | ❌ |

同一节点连续两次调用时，System + User 前三节构成**最长公共前缀**，利于 provider prompt cache。

任务相关指令、输出 schema **不得**放入 System；原先 plan/apply 各自的 schema 约束全部放在 User **最后**。

### 4.2 System（单一固定）

`GEN_CATALOG_NODE_SYSTEM` — Plan / Apply 字节级相同，仅含通用规则：

- 角色：投标目录规划专家
- 说明：具体任务与输出格式见用户消息末尾 `## 任务` 节
- 通用规则：bid-NNN id、根 bid-root、返回树时须完整 outline、保持已有 id、不破坏 mandatory 结构

**禁止**在 System 中出现 `needs_optimization`、`refinement_plan`、plan/apply 专用输出 schema。

### 4.3 User 共享前缀

函数：`build_node_shared_user_prefix(brief, root, excerpt) -> str`

固定三节标题与顺序：

```text
## 招标概要（tender_brief）
{summary_text + fields JSON}

## 当前完整目录树
{draft.root JSON}

## 招标文件相关摘录
{excerpt}
```

- `tender_brief` 缺失时：**整块省略** `## 招标概要` 节（Plan / Apply 行为一致）
- 三节之间以双换行分隔；JSON `indent=2`，与现有 `context.py` 风格一致

### 4.4 User 任务尾段

**Plan** — `build_node_plan_task_suffix()`：

```text
## 任务：目录优化评估

分析「招标文件相关摘录」是否要求对「当前完整目录树」进行优化或细化。

只输出 JSON：
{"needs_optimization": <bool>, "refinement_plan": "<方案说明>"}

- needs_optimization=false：无需改动，refinement_plan 简述原因
- needs_optimization=true：refinement_plan 描述具体动作（合并、拆分、补充子节等）
- 禁止输出 outline 字段
```

**Apply** — `build_node_apply_task_suffix(refinement_plan)`：

```text
## 优化或细化方案
{refinement_plan}

## 任务：执行目录更新

根据上述方案更新完整目录树。

只输出 JSON：
{"outline": <BidOutlineNode>, "changes_summary": "<本步调整说明>"}

- outline 为完整树，根 id=bid-root，已有 bid-NNN id 保持不变
- 仅执行方案中描述的调整，不超出方案范围
```

组装函数：

```python
def build_node_plan_user_prompt(brief, root, excerpt) -> str:
    return build_node_shared_user_prefix(...) + build_node_plan_task_suffix()

def build_node_apply_user_prompt(brief, root, excerpt, refinement_plan) -> str:
    return build_node_shared_user_prefix(...) + build_node_apply_task_suffix(refinement_plan)
```

### 4.5 废除的提示词

- 删除 `GEN_CATALOG_REFINE_SYSTEM`
- 删除 `build_refine_user_prompt()`（由上述函数替代）

---

## 5. LLM 调用与日志

| call_type | 触发条件 | 响应模型 |
|-----------|----------|----------|
| `gen_catalog_node_plan` | 每个待处理节点 | `BidOutlinePlanLLMResponse` |
| `gen_catalog_node_apply` | `needs_optimization=true` | `BidOutlineLLMResponse` |

`log_llm_prompt` 的 `segment_id` 仍为节点 id；`section_path` 仍为 `[node_title]`。

校验失败重试 ≤ `config.max_retries`（默认 2）。

---

## 6. 数据模型

### 6.1 新增

```python
class BidOutlinePlanLLMResponse(BaseModel):
    needs_optimization: bool
    refinement_plan: str = ""
```

### 6.2 不变

- `BidOutlineLLMResponse` — 仅 Apply 使用
- `BidOutlineFile`、`BidOutlineNode` — 不变

### 6.3 Session 扩展（可选，建议）

`GenCatalogSession` 增加调试/Viewer 展示字段：

```python
last_plan: dict | None = None
# 示例：{"node_id": "bid-003", "needs_optimization": true, "refinement_plan": "…"}
```

每次 Plan 完成后写入；Apply 或跳过后保留至下一节点 Plan 覆盖。

---

## 7. 编排变更（`extractor.py`）

`run_gen_catalog_node` 拆为：

1. `run_gen_catalog_node_plan(workspace, client, …) -> BidOutlinePlanLLMResponse`
2. `run_gen_catalog_node_apply(workspace, client, …, plan) -> BidOutlineFile`

或保留 `run_gen_catalog_node` 为编排入口，内部顺序调用 plan → 条件 apply。

**Apply 跳过时不调用** `save_draft` 写树（树未变）；仍更新 `session.completed_steps` 与 `last_plan`。

**进度回调** `on_progress`：

- `step` 仍为 `gen_catalog_node`
- `detail` 示例：`「投标函」评估：无需优化` 或 `「投标函」评估：需优化 → 执行中`
- `current` / `total` 按节点计，不因 Plan 多一次调用而增加 total

---

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| Plan JSON 解析失败 | 重试；耗尽后 `status=failed` |
| `needs_optimization=true` 且 `refinement_plan` 为空 | 校验失败，重试 |
| Apply JSON 解析失败 | 重试；树不更新、节点不记入 `completed_steps` |
| Apply 成功但 outline 校验失败（如缺 bid-root） | 重试 |

---

## 9. 已知取舍

节点 refine 不再传入废标项 / 评分项 / 模板清单：

- 节点级 `scoring_refs`、`disqualification_refs`、`template_ref` 的**后续补充**能力减弱
- 依赖 `gen_catalog_initial` 一次性填充引用字段
- 换取更短上下文、更高缓存命中率、以及「无需优化则跳过」的成本节省

---

## 10. 测试策略

| 层级 | 范围 |
|------|------|
| 单元 | `build_node_shared_user_prefix` 在 plan/apply 间字节一致；apply 正确追加方案块；brief 缺失时前缀一致省略概要节 |
| 单元 | Plan 响应校验：`needs_optimization=true` 要求非空 `refinement_plan` |
| FakeLLM | `false` 时仅 1 次调用、树 hash 不变；`true` 时 2 次调用、树更新 |
| 集成 | `mode=step` 单节点完成后 session `paused`；`completed_steps` 含节点 id |
| 回归 | `gen_catalog_initial`、accept、queue 逻辑不受影响 |

更新 `tests/helpers/` 中 gen-catalog FakeLLM 以识别 plan/apply 任务尾段。

---

## 11. 文件变更清单

| 文件 | 变更 |
|------|------|
| `gen_catalog/prompts.py` | 新增 `GEN_CATALOG_NODE_SYSTEM`；删除 `GEN_CATALOG_REFINE_SYSTEM` |
| `gen_catalog/context.py` | 共享前缀 + plan/apply 组装函数；删除 `build_refine_user_prompt` |
| `gen_catalog/models.py` | 新增 `BidOutlinePlanLLMResponse`；可选 `GenCatalogSession.last_plan` |
| `gen_catalog/extractor.py` | plan → 条件 apply 编排 |
| `tests/tender_insights/unit/test_gen_catalog*.py` | 覆盖两步与缓存前缀 |
| `tests/helpers/*fake*llm*` | plan/apply 分流 |
| `docs/superpowers/specs/2026-06-25-tender-generate-design.md` | 可选：§4.2 / §5.1 加注「节点完善已升级为 v2，见 2026-06-26 spec」 |

**Viewer**：若 `gen-catalog.js` 展示 LLM call_type，补充 `gen_catalog_node_plan` / `gen_catalog_node_apply` 标签；非必须改 UI 步进逻辑。

---

## 12. 与母规格关系

本 spec **增量修订** `007-tender-generate` 的节点完善子流程，不推翻 initial 步、accept、session 文件布局与 Viewer 路由。母规格 §4.2 Step 1…N 的单步描述以实现本 spec 为准。
