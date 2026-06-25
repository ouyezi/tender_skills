from __future__ import annotations

import json

from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.completion import LLMCompletionResult


class BriefFakeLLM(FakeLLMClient):
  def __init__(self, *, brief_json: str | None = None, partial_json: str | None = None) -> None:
    super().__init__()
    default = json.dumps(
      {
        "fields": {
          "issuer_company": "某某有限公司",
          "procurement_subject": "办公用品采购",
          "budget_info": "预算 100 万元",
          "qualification_requirements": "具有独立法人资格",
          "key_timelines": "工期 30 日，2026-07-01 开标",
        },
        "summary_text": "【招标人】某某有限公司。【标的】办公用品采购。【预算】100 万元。【资质】独立法人。【时间】2026-07-01 开标。",
      },
      ensure_ascii=False,
    )
    self._brief_json = brief_json or default
    self._partial_json = partial_json or json.dumps(
      {
        "issuer_company": ["某某有限公司"],
        "procurement_subject": ["办公用品采购"],
        "budget_info": ["预算 100 万元"],
        "qualification_requirements": ["具有独立法人资格"],
        "key_timelines": ["2026-07-01 开标"],
      },
      ensure_ascii=False,
    )

  def complete_with_meta(
    self,
    messages: list[dict[str, str]],
    *,
    response_format: str = "text",
    timeout: float | None = None,
  ) -> LLMCompletionResult:
    user = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
    if "分片提取的事实" in user:
      text = self._brief_json
    elif "分片 " in user[:20]:
      text = self._partial_json
    else:
      text = self._brief_json
    self.calls.append({"messages": messages, "response_format": response_format, "timeout": timeout})
    return LLMCompletionResult(text=text)
