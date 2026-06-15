# Feature: 文档提取与智能分块脚本包

**Feature Branch**: `001-document-extract-chunk`  
**Created**: 2026-06-15  
**Status**: Draft

> **完整需求规格（主文档）**  
> [`docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`](../../docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md)

## 文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| **完整需求** | [`docs/.../2026-06-15-doc-chunk-requirements.md`](../../docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md) | FR/NFR、接口、数据、验收（**主文档**） |
| 实现计划 | [plan.md](./plan.md) | 技术上下文、模块结构、实现阶段 |
| 调研决策 | [research.md](./research.md) | 技术选型与替代方案 |
| 数据模型 | [data-model.md](./data-model.md) | 实体字段与关系 |
| CLI 契约 | [contracts/cli.md](./contracts/cli.md) | 命令行接口 |
| Python API | [contracts/python-api.md](./contracts/python-api.md) | 库接口 |
| JSON Schema | [contracts/workspace-schemas.md](./contracts/workspace-schemas.md) | 工作区文件格式 |
| 验证指南 | [quickstart.md](./quickstart.md) | 端到端验证步骤 |
| 质量清单 | [checklists/requirements.md](./checklists/requirements.md) | 规格质量检查 |

## Clarifications

### Session 2026-06-15

- Q: Skills 集成时，脚本包应以何种方式被消费？ → A: CLI + 可导入的 Python 库 API（既可 pip install 后 import 调用，也可命令行独立运行）
- Q: 章节内续切的默认最大块长度及目录层级深度？ → A: 默认 20,000 token 估算（与 tender_doctor 一致）；目录树与分块须支持最多 8 级章节层级下钻，不限于三层
- Q: 提取阶段对图片的处理深度？ → A: 仅导出原图并在 Markdown 中保留引用；不做 OCR 或 LLM 图像描述（图像语义提取由下游独立 skills 负责）
- Q: 块分类信息的体系范围？ → A: 内置通用类型枚举 + 可通过配置文件扩展自定义分类标签与匹配规则
- Q: 批量处理时单文件失败的默认行为？ → A: 默认继续处理其余文件，最终返回部分成功并汇总成功/失败清单

### Session 2026-06-15（Brainstorming: 目录树 LLM 优化）

- Q: LLM 重构输入形式？ → A: 自然语言指令 + 原始目录树（及当前 refined 树）
- Q: 允许的重构操作？ → A: 合并/拆分/升降级/重命名，新节点必须映射到原始节点或 Markdown 范围
- Q: 重构与分块之间的交互？ → A: 多轮迭代（指令 → 重构 → 预览），满意后 accept 再分块
- Q: 迭代历史保留策略？ → A: 仅保留最终优化树 + 变更摘要，不存每轮完整 JSON
- Q: 分块内容边界依据？ → A: 以优化目录树节点 + 映射范围为准

### Session 2026-06-15（Brainstorming: 完整需求文档）

- Q: 完整需求文档存放位置？ → A: `docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`（合并 outline-refine-design，删除旧设计文档）
- Q: spec.md 处理方式？ → A: 改为索引页，保留 Clarifications 与文档导航
