from __future__ import annotations

import json

from tender_insights.template.models import TemplateShard

TEMPLATE_PLAN_SYSTEM = """你是招标文件分析专家。根据目录与各分片摘要，补充模版提取计划说明。
只输出 JSON：{"shard_count": number, "priority_sections": ["..."], "notes": "..."}
不要修改分片边界。"""

TEMPLATE_EXTRACT_SYSTEM = """你是招标文件模版提取专家。
模版 = 发标单位要求投标人填写、签字、盖章并按格式提交的范本/表格/函件。
只输出 JSON：{"templates": [{"title","type","type_label","markdown","confidence","source_excerpt"}]}
其中 markdown 为完整模版正文（Markdown 格式，保留标题层级、表格结构、下划线占位、签章位置）。
从输入正文中逐字提取，不要摘要或省略；若片段内无模版则返回 templates: []。
排除：纯采购需求、合同正文、评审办法说明。"""


def build_plan_user_prompt(*, doc_title: str, shard_summaries: list[dict]) -> str:
    summaries_json = json.dumps(shard_summaries, ensure_ascii=False, indent=2)
    return (
        f"文档标题: {doc_title}\n\n"
        f"分片摘要 ({len(shard_summaries)} 片):\n{summaries_json}\n\n"
        "请根据目录与各分片摘要，补充模版提取计划说明。"
        "只输出 JSON，不要修改分片边界。"
    )


def build_extract_user_prompt(*, shard: TemplateShard, shard_markdown: str) -> str:
    section_path = " > ".join(shard.section_path) if shard.section_path else "(root)"
    return (
        f"模版正文分片编号: {shard.shard_id}\n"
        f"章节路径: {section_path}\n"
        f"分片策略: {shard.strategy}\n"
        f"本分片约 {shard.char_count} 字。\n"
        "请识别本片段内所有投标提交模版，在 markdown 字段输出完整模版正文。\n\n"
        f"正文:\n{shard_markdown}"
    )
