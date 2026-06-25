from __future__ import annotations

import json

EXTRACT_SYSTEM_PROMPT = """你是招标文档事实提取助手。仅根据用户提供的正文客观提取关键事实。
禁止推测、延伸解读、建议或总结性发挥。只摘录正文中明确出现的信息。
输出严格 JSON，字段均为字符串数组；本段未出现的类别返回空数组 []。"""

MERGE_SYSTEM_PROMPT = """你是招标基础概要合成助手。根据各分片已提取的事实，生成标准化招标基础概要。
要求：
1. fields 五个字段均需填写；无事实时写「未提及」
2. summary_text 为面向下游 AI 的精炼背景摘要，总字数不超过 {max_chars} 字（按字符计）
3. 语言直白，删除修饰与重复，只客观罗列关键事实
4. summary_text 分段呈现五个信息层级，不展开延伸解读
输出严格 JSON。"""

SINGLE_SYSTEM_PROMPT = """你是招标基础概要提取助手。阅读全部招标文件正文，生成标准化招标基础概要。
必须提取：
- issuer_company：招标发起企业全称
- procurement_subject：本次招标标的/采购完整核心内容
- budget_info：项目总预算、招标控制价、预估金额
- qualification_requirements：投标人硬性准入资质、资格基本要求
- key_timelines：项目工期、交付、开标核心时间节点

要求：
1. 仅根据正文客观提取，禁止推测与延伸解读
2. fields 五个字段均需填写；无事实时写「未提及」
3. summary_text 总字数不超过 {max_chars} 字，精炼分段，信息层级清晰
输出严格 JSON。"""


def build_extract_prompt(*, segment_index: int, segment_total: int, markdown: str) -> str:
    return (
        f"分片 {segment_index}/{segment_total}\n"
        "请从本段正文提取下列事实（原文表述或简短摘录，每条一个数组元素）：\n"
        "- issuer_company：招标发起企业全称\n"
        "- procurement_subject：招标标的/采购核心内容\n"
        "- budget_info：预算、控制价、预估金额\n"
        "- qualification_requirements：硬性准入资质、资格基本要求\n"
        "- key_timelines：工期、交付、开标等时间节点\n\n"
        f"正文:\n{markdown}"
    )


def build_merge_prompt(*, partials: list[dict], max_chars: int) -> str:
    payload = json.dumps(partials, ensure_ascii=False, indent=2)
    return (
        f"以下为 {len(partials)} 个分片提取的事实（JSON 数组）。"
        f"请去重合并，生成最终 fields 与不超过 {max_chars} 字的 summary_text。\n\n"
        f"{payload}"
    )


def build_single_prompt(*, markdown: str, max_chars: int) -> str:
    return (
        f"请阅读全部正文并生成招标基础概要（summary_text 不超过 {max_chars} 字）。\n\n"
        f"正文:\n{markdown}"
    )
