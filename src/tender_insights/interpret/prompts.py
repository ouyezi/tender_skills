from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件解读专家。从给定正文片段中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria）
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
- directory_requirements: 目录/文件组成（required_sections, mandatory, structure 可选树形）
每条必须有 id, title, summary, source_excerpt, section_path, confidence。
若无某类内容，对应数组返回 []。"""


def build_segment_prompt(segment_id: str, section_path: list[str], markdown: str) -> str:
    path = " > ".join(section_path) if section_path else "(root)"
    return f"segment_id: {segment_id}\nsection_path: {path}\n\n正文:\n{markdown}"


OVERVIEW_SYSTEM_PROMPT = """你是招标文件解读专家。根据已提取的结构化明细，生成概要描述。
只输出 JSON：{ summary, disqualification_summary, scoring_summary, bid_risk_summary, directory_summary }"""


def build_overview_prompt(items_json: str) -> str:
    return f"已提取明细:\n{items_json}"
