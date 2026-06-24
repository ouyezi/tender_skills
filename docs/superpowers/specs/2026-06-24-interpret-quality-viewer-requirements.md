# 需求规格：招标解读提取质量与 Viewer 展示完善

**版本**: 1.0  
**日期**: 2026-06-24  
**状态**: 待开发  
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


| 验收项            | 期望                                                                       |
| -------------- | ------------------------------------------------------------------------ |
| 商品方案细则         | `interpretation.json` 中含「契合度、商品规范性 0–2 分」等至少 3 条细则（可位于同一 `children` 父项下） |
| 评分表完整度         | 评分表中「仓储方案、接单方案、配送方案、售后方案」等主要评分项均有 `children` 或独立 `scoring_items`         |
| 不得仅 1 条笼统得分项   | 禁止仅输出「综合评审总分」+ 3 条无分值的商务/技术/价格摘要                                         |
| Viewer 得分项 Tab | 页面可见上述细则全文（`children[].criteria`）                                        |
| 原文可追溯          | 每条细则有 `source_excerpt`，可跳转原文                                             |
| LLM 配置         | 启动 `python -m viewer` 时自动加载仓库根目录 `.env` 中的 `LLM_API_KEY`（**已实现**，回归验证即可） |


---

## 2. 现状与根因（已确认）

### 2.1 提取侧


| 现象               | 根因                                                                             |
| ---------------- | ------------------------------------------------------------------------------ |
| 得分项为空或极少         | 早期 v2 prompt 边界模糊；v2.1 已加强 prompt + 分段附录，但样本仍不达标                               |
| 「5.2 评分」无细则      | **分段错位**：`chunks` 将「5.2评分」切成独立段，送进 LLM 的正文仅 ~14 字（「采购人：…」），**评分表不在该段**         |
| 评分表在「第六章 响应文件格式」 | 完整评分表（含商品方案 0–2 分）落在第 24 段（~1 万 token），与格式范本混合；LLM 优先抽目录，**漏抽或泛化评分**           |
| 细则在原文存在          | `content.md` / `tables/*.json` 的 `llm_text` 中有完整表格行，**数据可达但未进入 scoring_items** |
| 目录零散             | v2.1 已要求 `structure` 树 + `inferred`，需继续验证                                      |


### 2.2 展示侧（Viewer）


| 现象      | 根因                                                                                        |
| ------- | ----------------------------------------------------------------------------------------- |
| 看不到得分细则 | `viewer/viewer/static/interpret.js` **未渲染** `scoring_items[].children[]`，只显示父项 `criteria` |
| 进度误导    | 24/24 后仍有 overview LLM + 模版提取，界面无独立步骤                                                     |
| 末段很慢    | 第 24 段 ~1 万 token；属性能接受但需进度文案更准确                                                          |


### 2.3 已落地（v2.1，勿重复开发）

- schema 1.2：`ScoringCriterionNode`、`ScoringItem.children[]`、`DirectoryRequirement.inferred`
- `merge_scoring_items`、`normalize_directory_requirements`
- Prompt 重写 + `build_segment_appendix`（响应人须知/评分/目录关键词）
- `build_directory_outline` 递归展开
- `viewer.config.load_project_env()` 启动加载 `.env`

---

## 3. 功能需求

### 3.1 分段策略：评分内容可达（P0）

**需求**：送进 LLM 的「评分相关分段」必须包含完整评分表正文（含表格 `llm_text`），不得出现「仅有章节标题、无表体」的空段。

**方案方向（实现时二选一或组合，需在技术方案中说明）：**

- **A. 分段合并**：`plan_segments` 将「5.2评分」与其后紧邻的评分表 chunk/正文合并；或按 outline 将「第三章 评审办法」下评分相关节点合并至 ≥ `segment_min_tokens` 且包含表格
- **B. 表格锚点注入**：检测 segment 的 `section_path` 含「评分/评审办法」但正文过短（如 `< 200` 字符）时，从 `content.blocks.json` / `tables/` 按 `char_range` 注入关联表格的 `llm_text`
- **C. 评分专段**：对含 `【表格:` 且列名含「评分说明/分值」的表格，生成独立 `Segment`（`section_path` 继承最近评分章节）

**验收**：样本中「5.2评分」对应 segment 的 markdown 含「商品方案」「0-2分」关键词。

### 3.2 得分项提取：细则完整（P0）

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
- 大段（如第六章格式章）若同时含评分表与目录，**scoring 与 directory 须同时提取**，不得因目录任务压制评分

**Prompt 补充（若仍一次 LLM/段）**：

- 识别 `【表格:` 中「评分说明」「分值」列，按行生成 `scoring_items` + `children`
- 分号分隔的多条「0-N分」规则须全部进入 `children` 或 `criteria`

**验收**：样本 `interpretation.json` 中 `scoring_items` 总数 ≥ 3 个父项或 ≥ 8 个 `children`；含用户指定的 3 条商品方案 0–2 分描述。

### 3.3 目录要求（P1，v2.1 延续验证）

- 有「投标文件组成 / 格式」章节 → `inferred: false` + 完整 `structure` 树
- 无明确章节 → `inferred: true` 推断清单 + `overview.directory_summary`
- Viewer 展示 `directory_requirements[].structure` 树形（当前可能仅扁平列表，需确认并补齐）

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

**其他 Tab（建议一并检查）**：

- `directory_requirements`：展示 `inferred` 标记；有 `structure` 时树形或缩进列表展示
- `overview`：五段概要是否已有入口；若无，增加「概要」折叠区或顶栏摘要

**验收**：不读 JSON 文件，仅在页面可见商品方案 0–2 分细则全文。

### 3.5 进度与体验（P2）

- interpret 阶段在「24/24」之后、overview 调用期间，显示「正在生成概要…」（`extractor.py` 增加 `on_progress` 回调点）
- 模版提取阶段保持现有「提取模版」文案
- 可选：展示当前分段 `detail`（章节名）——已有，保持即可

### 3.6 环境与配置（P1，已实现需回归）

- `python -m viewer` 自动加载 `{repo_root}/.env`
- 不覆盖已设置的环境变量
- README / viewer README 注明无需手动 `export LLM_API_KEY`

---

## 4. 非功能需求


| 项        | 要求                                                                       |
| -------- | ------------------------------------------------------------------------ |
| LLM 调用次数 | 优先不增加每文档 LLM 次数（仍 N 段 + 1 overview）；若分段修复导致段数变化，需在方案中说明上限                |
| 包边界      | 不修改 `doc_chunk` 核心提取逻辑；分段增强在 `tender_insights/common/segment_planner.py` |
| 向后兼容     | schema 1.2 消费者；1.1 JSON 仍可解析                                             |
| 测试       | 单元测试覆盖分段注入/合并；契约测试；集成测试用表格样本断言 `children` 非空；viewer 前端测试或手动清单            |
| 性能       | 允许末段 1–3 分钟；避免无上限增大单段 token                                              |


---

## 5. 范围外

- 法务审核 `legal_review`
- 多文件工作区合并解读
- 解读结果在线编辑 / 导出
- 新增二次 LLM「补漏扫描」（除非 P0 方案证明 prompt+分段仍无法达标）
- Viewer 鉴权、远程部署

---

## 6. 涉及模块与文件


| 模块        | 文件                                                   | 变更类型                         |
| --------- | ---------------------------------------------------- | ---------------------------- |
| 分段        | `src/tender_insights/common/segment_planner.py`      | 评分段合并 / 表格注入                 |
| 表格切片      | `src/tender_insights/common/section_slice.py`        | 可能扩展按表格类型选取 `llm_text`       |
| 提取        | `src/tender_insights/interpret/prompts.py`           | 评分表行级提取指令                    |
| 提取        | `src/tender_insights/interpret/extractor.py`         | overview 前进度回调               |
| 模型        | `src/tender_insights/interpret/models.py`            | 已 1.2，一般无需改                  |
| Viewer UI | `viewer/viewer/static/interpret.js`                  | 渲染 `children`、目录树、`inferred` |
| Viewer UI | `viewer/viewer/static/style.css`                     | 子项列表样式                       |
| 配置        | `viewer/viewer/config.py`                            | `.env` 加载（已完成）               |
| 测试        | `tests/tender_insights/unit/test_segment_planner.py` | 评分段含表体                       |
| 测试        | `viewer/tests/`                                      | 展示逻辑或 API 夹具                 |
| 文档        | `.cursor/skills/tender-interpret/SKILL.md`           | 与实现对齐                        |


---

## 7. 建议实施顺序

```text
Phase 1（P0 展示）
  → interpret.js 渲染 scoring children + 目录 structure/inferred
  → 用现有 JSON 验证 UI（即使 children 笼统也应可见）

Phase 2（P0 提取）
  → segment_planner 修复评分段空壳问题（表格注入或合并）
  → prompts 强化表格行 → children 规则
  → 样本回归至验收标准

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

# Viewer
.venv/bin/pytest viewer/tests/ -v
```

新增用例建议：

- `test_plan_segments_scoring_section_includes_table_llm_text`：构造含空标题段 + 表格侧车的 workspace fixture
- `test_interpretation_contains_scoring_children_for_table_rows`：FakeLLM 或 snapshot 断言字段存在

### 8.2 手工（铁建福利商城样本）

1. 启动 `python -m viewer`，打开 `/interpret`
2. 上传同一份 docx，等待完成
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

> 请阅读 `docs/superpowers/specs/2026-06-24-interpret-quality-viewer-requirements.md`，按 Phase 1→2 实现招标解读提取质量与 Viewer 展示完善；样本用铁建福利商城 docx 验收，重点修复评分段空壳与 `children` 页面展示。

