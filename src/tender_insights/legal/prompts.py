from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件法务审核专家。从给定章节文本中识别合规风险与待确认事项。
只输出 JSON，字段：
- risk_items: 法务风险（含 description, clause_excerpt, risk_type, severity: high|medium|low）
- pending_confirmations: 待确认事项（含 description, confirm_with, suggested_question）
每条必须有 section_path（章节路径数组）。"""


def build_user_prompt(section_title: str, section_path: list[str], markdown: str) -> str:
    return (
        f"章节: {section_title}\n"
        f"路径: {' > '.join(section_path)}\n\n"
        f"正文:\n{markdown[:12000]}"
    )
