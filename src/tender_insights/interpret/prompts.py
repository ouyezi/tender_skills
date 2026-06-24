from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件解读专家。从给定正文片段中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria, children[]）
  - children[] 为评分细则：id, title, max_score, score_range, criteria, source_excerpt
  - 响应人须知/投标人须知内嵌的评审办法、分值表、加扣分项也必须提取为 scoring_items
  - 有分值表时建父项+children；细则 criteria 须含评分档位与加扣分规则，禁止笼统摘要
  - 本段有评分相关内容时禁止返回空 scoring_items
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
  - 资格、符合性、实质性响应风险；有明确分值的评分细则不要放这里
- directory_requirements: 目录/文件组成（inferred, required_sections, mandatory, structure 树形）
  - 明确「投标文件组成/格式/目录」章节：inferred=false，输出完整 structure 树，禁止拆成零散 required_sections
  - 无明确目录章节：本段 directory_requirements 返回 []
每条必须有 id, title, summary, source_excerpt, section_path, confidence。
若无某类内容，对应数组返回 []。"""

_SEGMENT_APPENDIX_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("响应人须知", "投标人须知", "供应商须知"),
        "【分段提示】本段常含评审/评分办法，请重点提取 scoring_items（含 children 细则）。",
    ),
    (
        ("评标", "评审", "评分", "分值", "得分"),
        "【分段提示】本段为评分核心章节，须提取完整 scoring_items 树（父项+children 细则）。",
    ),
    (
        ("废标", "无效投标", "否决"),
        "【分段提示】本段重点提取 disqualification_items。",
    ),
    (
        ("投标文件组成", "文件格式", "目录", "装订"),
        "【分段提示】本段重点提取 directory_requirements（inferred=false，完整 structure 树）。",
    ),
]


def build_segment_appendix(section_path: list[str]) -> str:
    haystack = " ".join(section_path).lower()
    lines: list[str] = []
    for keywords, message in _SEGMENT_APPENDIX_RULES:
        if any(kw.lower() in haystack for kw in keywords):
            lines.append(message)
    return "\n".join(lines)


def build_segment_prompt(segment_id: str, section_path: list[str], markdown: str) -> str:
    path = " > ".join(section_path) if section_path else "(root)"
    appendix = build_segment_appendix(section_path)
    parts = [f"segment_id: {segment_id}", f"section_path: {path}"]
    if appendix:
        parts.append(appendix)
    parts.append(f"\n正文:\n{markdown}")
    return "\n".join(parts)


OVERVIEW_SYSTEM_PROMPT = """你是招标文件解读专家。根据已提取的结构化明细，生成概要描述。
只输出 JSON：{ summary, disqualification_summary, scoring_summary, bid_risk_summary, directory_summary }
要求：
- scoring_summary 须写清总分结构、各大类要点及关键评分细则（来自 children）
- directory_summary 须区分明确目录与推断目录（inferred=true 时说明推断性质）"""


def build_overview_prompt(items_json: str) -> str:
    return f"已提取明细:\n{items_json}"
