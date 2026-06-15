from __future__ import annotations

from doc_chunk.llm.client import LLMClient


def describe_chunk(*, title: str, markdown: str, llm_client: LLMClient | None) -> str | None:
    if llm_client is None:
        return None

    prompt = (
        "请基于以下文档块生成1-3句中文摘要，突出核心信息，避免臆测。\n"
        f"标题: {title}\n"
        "正文:\n"
        f"{markdown[:4000]}"
    )
    text = llm_client.complete(
        [{"role": "user", "content": prompt}],
        response_format="text",
        timeout=60.0,
    ).strip()
    return text or None
