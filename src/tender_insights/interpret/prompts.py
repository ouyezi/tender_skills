from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件解读专家。从给定章节文本中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria）
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
- directory_requirements: 目录/文件组成要求（required_sections 数组, mandatory）
每条必须有 source_excerpt（原文摘录）和 section_path。"""


def build_user_prompt(section_title: str, section_path: list[str], markdown: str) -> str:
    return (
        f"章节: {section_title}\n"
        f"路径: {' > '.join(section_path)}\n\n"
        f"正文:\n{markdown[:12000]}"
    )
