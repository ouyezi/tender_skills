# 需求规格：招标解读提取质量与 Viewer 展示完善

**版本**: 1.1  
**日期**: 2026-06-24  
**状态**: 待开发  
**Feature ID**: `006-interpret-quality-viewer`  
**前置**: interpret v2（全文分段）、interpret v2.1（schema 1.2 已部分落地）  
**参考设计**: `docs/superpowers/specs/2026-06-24-interpret-v2.1-design.md`  
**验证样本**: 「铁建福利商城员工福利物资谈判采购」类 docx（`ZTGY-WZ-2026-FLCG01`）

---

## 1. 背景与目标

### 1.1 背景

`tender_insights interpret` 已对招标工作区做全文分段 + LLM 结构化提取，产出 `interpretation.json`（schema 1.2）。`viewer` 提供 Web 调试页（`/interpret`）展示解读结果。

在真实样本上验证发现：**提取结果不完整**、**评分细则丢失**、**页面未展示已提取的细则结构**，用户无法依赖解读结果做投标准备。

### 1.2 业务目标

用户上传招标文件并点击「开始解读」后，应获得：

1. **废标项、得分项（含细则）、投标风险、目录要求** 四类明细 + 各维度概要
2. 得分项须包含**可操作的评分细则**（如「商品方案契合度 0–2 分」），不得仅有大类空话
3. 目录要求须为**完整框架树**（有明确章节时）或**推断清单 + 概要**（无明确章节时）
4. **Viewer 页面完整展示** JSON 中所有对用户有意义的字段，尤其是 `scoring_items[].children[]`

### 1.3 成功标准（样本验收）

以「铁建福利商城」工作区为回归样本，解读完成后须满足：

| 验收项 | 期望 |
|--------|------|
| 商品方案细则 | `interpretation.json` 中含「契合度、商品规范性 0–2 分」等**至少 3 条**细则（可位于同一 `children` 父项下） |
| 评分表完整度 | 「仓储方案、接单方案、配送方案、售后方案」等主要评分项均有 `children` 或独立 `scoring_items` |
| 不得仅 1 条笼统得分项 | **禁止**仅输出「综合评审总分」+ 3 条无分值的商务/技术/价格摘要 |
| Viewer 得分项 Tab | 页面可见上述细则全文（`children[].criteria`） |
| 原文可追溯 | 父项可跳转原文；子项至少展示 `source_excerpt`（见 §3.4） |
| LLM 配置 | 启动 `python -m viewer` 时自动加载仓库根目录 `.env` 中的 `LLM_API_KEY`（**已实现**，回归验证即可） |
| 提示词可分析 | 每次 segment / overview LLM 调用的完整 messages 写入日志（见 §3.7） |

**Phase 分阶段验收**：

- **Phase 1（Viewer）**：用含 `children` 的 fixture JSON 验证页面展示；不要求样本全文达标
- **Phase 2（提取）**：铁建样本全文达标（上表全部满足）

---

## 2. 现状与根因（已确认）

### 2.0 解读覆盖策略（已确认，本需求不改造主流程架构）

| 决策 | 说明 |
|------|------|
| 全分段提取 | interpret v2 对 `plan_segments()` 产出的**每一个**非空分段调用 LLM；**不**恢复 v1 的 `SectionRouter` 关键词 gate |
| 关键词用途 | `build_segment_appendix()` 仅按 `section_path` 追加 Prompt 提示，**不**决定是否调用 LLM |
| 结果合并 | 各段 `scoring_items` 累加后经 `merge_scoring_items()` 合并；某段返回空数组不阻止后续段贡献 |

因此：**细则丢失不是因为「5.2 段没抽到就不继续」**，而是下文两类独立问题叠加。

### 2.1 提取侧（两类独立根因）

| 现象 | 根因 |
|------|------|
| 「5.2 评分」段无细则 | **问题 A — 空壳段**：chunk 将「5.2 评分」切成独立段，正文仅 ~14 字；评分表不在该段及**紧邻**下一段（表在第六章，物理不相邻）。该段浪费 1 次 LLM，对结果无贡献 |
| 细则全文仍缺失 | **问题 B — 混合大段**（主因）：含完整评分表的第 24 段（~1 万 token，第六章格式范本 + 评分表）**已被提取**，但 LLM 优先抽 `directory_requirements`，评分被泛化为「综合评审总分」等笼统项 |
| 得分项为空或极少（历史） | v2 prompt 边界模糊；v2.1 已加强 prompt + 分段附录，但问题 B 仍导致样本不达标 |
| 细则在原文存在 | `content.md` / `tables/*.json` 的 `llm_text` 中有完整表格行，**数据可达但未进入 scoring_items** |
| 目录零散 | v2.1 已要求 `structure` 树 + `inferred`，需继续验证 |

**铁建样本分段示意**：

```text
第三章 评审办法
  seg-N:  5.2 评分          ← 空壳（问题 A）
  seg-N+1: 5.3 …            ← 仍是第三章，不含那张评分表

…中间多段…

第六章 响应文件格式
  seg-24: 格式范本 + 评分表  ← 已送 LLM，但评分漏抽（问题 B）
```

### 2.2 展示侧（Viewer）

| 现象 | 根因 |
|------|------|
| 看不到得分细则 | `interpret.js` **未渲染** `scoring_items[].children[]`，只显示父项 `criteria` |
| 进度误导 | 24/24 后仍有 overview LLM + 模版提取，界面无独立步骤 |
| 末段很慢 | 第 24 段 ~1 万 token；属性能接受但需进度文案更准确 |

### 2.3 已落地（v2.1，勿重复开发）

- schema 1.2：`ScoringCriterionNode`、`ScoringItem.children[]`、`DirectoryRequirement.inferred`
- `merge_scoring_items`、`normalize_directory_requirements`
- Prompt 重写 + `build_segment_appendix`（响应人须知/评分/目录关键词）
- `build_directory_outline` 递归展开
- `viewer.config.load_project_env()` 启动加载 `.env`

---

## 3. 功能需求

### 3.1 分段策略：空壳评分段修复（P0，问题 A）

**需求**：送进 LLM 的「评分相关分段」不得为仅有章节标题、无表体的空段。

**已确认方案：B（表格锚点注入）为主 + A（相邻小段合并）为辅**

| 方案 | 作用 | 规则 |
|------|------|------|
| **B. 表格锚点注入** | 主方案 | `section_path` 含「评分/评审办法/评标」且正文 `< 200` 字符时，从 `content.blocks.json` / `tables/` 按 `char_range` 注入关联表格的 `llm_text` |
| **A. 分段合并** | 辅方案 | B 注入后仍过短时，与**紧邻**下一段合并（沿用现有 `section_path` 前 2 级相同 + `< segment_min_tokens` 规则） |

**验收**：样本中「5.2 评分」对应 segment 的 markdown 含「商品方案」「0-2 分」关键词。

**范围**：仅修改 `src/tender_insights/common/segment_planner.py`（及必要时 `common/section_slice.py`）；**不**修改 `viewer/viewer/services/section_slice.py`。

### 3.2 混合大段：评分专段 + Prompt 强化（P0，问题 B，已确认）

**需求**：当一段同时含评分表与目录/格式范本时，评分细则不得被目录任务压制。

**已确认方案：C（评分专段）+ Prompt 强化（组合使用）**

#### C. 评分专段

对 workspace 中满足以下条件的表格，在 `plan_segments` 产出主分段列表后**额外**生成独立 `Segment`：

- 表格 `llm_text` / 列名含「评分说明」「分值」「得分」等关键词；或
- 表格行文本含「0-N 分」模式

专段属性：

- `section_path`：继承该表所在位置向上最近的含「评分/评审/评标」祖先章节；若无则继承宿主段 `section_path`
- `segment_id`：如 `seg-scoring-001`（与常规 `seg-NNN` 区分）
- `markdown`：仅含该评分表 `llm_text`（可加简短上下文标题行）

**LLM 次数**：专段各增加 1 次调用。铁建样本预估 +1～3 次；须在实现方案中记录实际上限（建议单文档评分专段 ≤ 5）。

#### Prompt 强化（与 C 并行，作用于含评分表的宿主段与专段）

在 `prompts.py` 补充：

1. **混合段双任务**：`section_path` 含「格式/响应文件」且正文含 `【表格:` + 分值列时，appendix 追加：
   > 「本段同时含投标文件格式与评分表，须**同时**提取 `directory_requirements`（structure 树）与 `scoring_items`（含 children 细则），禁止只提取目录而忽略评分表。」
2. **表格行级规则**（延续 v2.1）：识别「评分说明」「分值」列，按行生成 `children`；分号分隔的多条「0-N 分」规则须全部保留
3. **专段 appendix**：评分专段固定追加「本段仅含评分表，须完整提取全部 scoring_items + children，directory_requirements 返回 []」

**验收**：

- 样本 `interpretation.json` **必须**含 3 条商品方案 0–2 分描述
- **且**禁止仅 1 条笼统「综合评审总分」
- `scoring_items` 父项 ≥ 3 **或** `children` 总数 ≥ 8（二者满足其一且内容验收通过即可）

### 3.3 得分项提取：细则完整（P0）

**需求**：按 schema 1.2 两层树输出评分结果。

**父项**：评审大类（如「技术及服务能力」「商务部分」），含 `max_score` / `weight`。

**子项 `children[]`**：每个可独立打分的细则一条，例如：

```json
{
  "id": "sc-001-01",
  "title": "商品方案-需求契合度与规范性",
  "max_score": 2.0,
  "score_range": "0-2",
  "criteria": "根据响应人提供的商品方案，评估与采购需求契合度、商品规范性综合评估得分0-2分",
  "source_excerpt": "（原文表格行摘录）"
}
```

**规则**：

- 评分表中一行多项细则（分号分隔）应拆为多条 `children`，或单条 `criteria` 保留全文——**至少全文不丢失**
- 同一段含评分表时 **禁止** 返回空 `scoring_items`
- 大段若同时含评分表与目录，**scoring 与 directory 须同时提取**（见 §3.2）

### 3.4 Viewer：完整展示解读结果（P0）

**文件**：`viewer/viewer/static/interpret.js`（及必要时 `style.css`）

**得分项 Tab**：

- 父项：标题、分值、权重、summary、父级 criteria（如有）
- **子项列表**：遍历 `item.children[]`，展示：
  - `title`
  - `max_score` / `score_range`
  - `criteria`（细则全文）
  - `source_excerpt`（可折叠）
- 无 `children` 时保持现有父项展示
- 子项「查看原文」：继承父项 `section_path` 匹配的 outline 节点（`ScoringCriterionNode` 无独立 `char_start`）

**其他 Tab**：

- `directory_requirements`：展示 `inferred` 标记；有 `structure` 时树形或缩进列表展示
- `overview`：五段概要；若无入口，增加「概要」折叠区或顶栏摘要

**验收**：不读 JSON 文件，仅在页面可见商品方案 0–2 分细则全文。

### 3.5 目录要求（P1，v2.1 延续验证）

- 有「投标文件组成 / 格式」章节 → `inferred: false` + 完整 `structure` 树
- 无明确章节 → `inferred: true` 推断清单 + `overview.directory_summary`
- Viewer 展示 `directory_requirements[].structure` 树形

### 3.6 进度与体验（P2）

- interpret 阶段在末段完成后、`build_overview()` 期间，显示「正在生成概要…」（`extractor.py` 在 overview 调用前增加 `on_progress` 回调）
- 模版提取阶段保持现有「提取模版」文案

### 3.7 LLM 提示词日志（P1，已确认）

**目的**：每次解读的完整 Prompt 写入日志，便于事后分析提取质量与分段问题。

**范围**：以下每次 LLM 调用均记录：

| 调用点 | 标识字段 |
|--------|----------|
| 分段提取 | `segment_id`、`section_path`、`call_type=segment` |
| 概要生成 | `call_type=overview` |
| 评分专段（§3.2 C） | `segment_id`、`call_type=scoring_table` |

**日志内容**（每条调用 1 条或多条结构化日志）：

- `workspace` 路径（或 `session_id`，viewer 场景）
- `call_type`、`segment_id`、`section_path`
- **完整 `messages` 列表**（`system` + `user` 全文，含 appendix 与正文）
- `token_estimate`（若有）
- 时间戳

**实现要求**：

- 使用 Python 标准库 `logging`，logger 名：`tender_insights.interpret.llm`
- 默认级别 **INFO**（开启即输出完整 prompt，便于 viewer 调试）
- 环境变量 `INTERPRET_LOG_PROMPTS`：`1`（默认）输出；`0` 关闭（避免生产环境日志过大）
- 日志输出到 **stderr**（`python -m viewer` 终端可见）
- **可选持久化**：当 `INTERPRET_LOG_PROMPTS_DIR` 指向目录时，额外将每次调用的 JSON 写入 `{dir}/{segment_id or overview}.json`（便于离线对比）

**涉及文件**：

- `src/tender_insights/interpret/extractor.py` — segment 循环内、overview 前
- `src/tender_insights/interpret/overview.py` — overview 调用前
- `viewer/viewer/__main__.py` 或 `main.py` — 配置 `logging.basicConfig(level=INFO)` 确保终端可见

**验收**：铁建样本跑一遍解读后，终端日志中可找到 24+ 条 segment 记录及 1 条 overview 记录，每条含完整 system/user 正文。

### 3.8 环境与配置（P1，已实现需回归）

- `python -m viewer` 自动加载 `{repo_root}/.env`
- 不覆盖已设置的环境变量
- README / viewer README 注明 `INTERPRET_LOG_PROMPTS` 与 `LLM_API_KEY`

---

## 4. 非功能需求

| 项 | 要求 |
|----|------|
| LLM 调用次数 | 基线 N 段 + 1 overview；评分专段（§3.2 C）允许增加，单文档专段 ≤ 5，须在实现记录中说明 |
| 包边界 | 不修改 `doc_chunk` 核心提取逻辑；分段增强在 `tender_insights/common/segment_planner.py` |
| 向后兼容 | schema 1.2 消费者；1.1 JSON 仍可解析 |
| 测试 | 单元测试覆盖分段注入/合并、评分专段；契约测试；集成测试断言 `children` 非空；日志单测断言 messages 被记录 |
| 性能 | 允许末段 1–3 分钟；避免无上限增大单段 token |
| 日志体积 | 单段 prompt 可达数万字符；`INTERPRET_LOG_PROMPTS=0` 可关闭；持久化目录需文档说明磁盘占用 |

---

## 5. 范围外

- 法务审核 `legal_review`
- 多文件工作区合并解读
- 解读结果在线编辑 / 导出
- 恢复 v1 `SectionRouter` 选择性提取
- 新增二次 LLM「补漏扫描」（除非 P0 方案证明仍无法达标）
- Viewer 鉴权、远程部署

---

## 6. 涉及模块与文件

| 模块 | 文件 | 变更类型 |
|------|------|----------|
| 分段 | `src/tender_insights/common/segment_planner.py` | B+A 空壳修复 + C 评分专段 |
| 表格切片 | `src/tender_insights/common/section_slice.py` | 可能扩展按表格类型选取 `llm_text` |
| 提取 | `src/tender_insights/interpret/prompts.py` | 混合段双任务 + 专段 appendix |
| 提取 | `src/tender_insights/interpret/extractor.py` | overview 进度回调 + 调用日志钩子 |
| 提取 | `src/tender_insights/interpret/overview.py` | overview 日志 |
| 日志 | `src/tender_insights/interpret/llm_logging.py`（新建） | 统一记录 messages |
| 模型 | `src/tender_insights/interpret/models.py` | 已 1.2，一般无需改 |
| Viewer UI | `viewer/viewer/static/interpret.js` | 渲染 `children`、目录树、`inferred` |
| Viewer UI | `viewer/viewer/static/style.css` | 子项列表样式 |
| Viewer 启动 | `viewer/viewer/__main__.py` | logging 配置 |
| 配置 | `viewer/viewer/config.py` | `.env` 加载（已完成） |
| 测试 | `tests/tender_insights/unit/test_segment_planner.py` | 空壳段 + 评分专段 |
| 测试 | `tests/tender_insights/unit/test_interpret_llm_logging.py`（新建） | 日志内容 |
| 测试 | `viewer/tests/` | 展示逻辑或 API 夹具 |
| 文档 | `.cursor/skills/tender-interpret/SKILL.md` | 与实现对齐 |
| 文档 | `viewer/README.md` | `INTERPRET_LOG_PROMPTS` 说明 |

---

## 7. 建议实施顺序

```text
Phase 1（P0 展示）
  → interpret.js 渲染 scoring children + 目录 structure/inferred
  → 用含 children 的 fixture JSON 验证 UI

Phase 2（P0 提取 + 可观测性）
  → llm_logging.py + extractor/overview 挂钩 + viewer logging 配置
  → segment_planner：B+A 空壳修复
  → segment_planner：C 评分专段
  → prompts：混合段双任务 + 专段 appendix
  → 铁建样本回归至验收标准

Phase 3（P1/P2）
  → overview 进度文案
  → directory Tab 树形展示
  → 文档与 SKILL 更新
```

---

## 8. 测试计划

### 8.1 自动化

```bash
# 单元 + 契约
.venv/bin/pytest tests/tender_insights/unit/test_segment_planner.py -v
.venv/bin/pytest tests/tender_insights/unit/test_interpret_merger.py -v
.venv/bin/pytest tests/tender_insights/contract/test_interpretation_schema.py -v
.venv/bin/pytest tests/tender_insights/unit/test_interpret_llm_logging.py -v

# Viewer
.venv/bin/pytest viewer/tests/ -v
```

新增用例建议：

- `test_plan_segments_scoring_section_includes_table_llm_text`：空标题段 + 表格侧车 fixture
- `test_plan_segments_scoring_table_spawns_dedicated_segment`：混合段中的评分表产出专段
- `test_interpretation_contains_scoring_children_for_table_rows`：FakeLLM 或 snapshot 断言字段存在
- `test_log_llm_prompts_emits_full_messages`：caplog 断言 system/user 全文存在

### 8.2 手工（铁建福利商城样本）

1. `INTERPRET_LOG_PROMPTS=1 python -m viewer`，打开 `/interpret`
2. 上传 docx，等待完成；**检查终端**是否有每段完整 prompt 日志
3. 得分项 Tab：确认可见「商品方案」三条 0–2 分细则
4. 目录 Tab：确认第六章格式树或 `inferred` 标记合理
5. 点击「查看原文」能定位到评分表

---

## 9. 附录：样本中的关键原文（验收对照）

**评分表 — 商品方案（须出现在 `scoring_items` 的 `children` 或 `criteria` 中）：**

1. 根据响应人提供的商品方案，评估与采购需求契合度、商品规范性综合评估得分 **0–2 分**
2. 根据响应人商品管理及服务能力，综合评估得分 **0–2 分**
3. 根据响应人提供的商品的核心价值及竞争力情况，综合评估得分 **0–2 分**

**同表其他行（建议一并提取）：** 仓储方案、接单方案、配送方案、售后方案等（各含分值与档位说明）。

**当前错误输出示例（须消除）：**

- 仅 1 条 `scoring_items`：「综合评审总分」
- `children` 为「商务评审 / 技术评审 / 价格评审」三条无具体分值的笼统说明
- JSON 全文搜索「商品方案」「0-2分」为 **missing**

---

## 10. 关联文档

- 设计（已批准）：`docs/superpowers/specs/2026-06-24-interpret-v2.1-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-24-interpret-v2.1.md`
- Viewer 设计：`docs/superpowers/specs/2026-06-24-interpret-viewer-design.md`

**给新会话的启动语建议：**

> 请阅读 `docs/superpowers/specs/2026-06-24-interpret-quality-viewer-requirements.md`（v1.1），按 Phase 1→2 实现；重点：B+A 空壳段修复、C 评分专段 + 混合段 Prompt、Viewer children 展示、`INTERPRET_LOG_PROMPTS` 完整日志。样本：铁建福利商城 docx。
