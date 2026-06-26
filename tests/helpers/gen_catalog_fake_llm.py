from __future__ import annotations

import json

from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.completion import LLMCompletionResult

_INITIAL = {
    "outline": {
        "id": "bid-root",
        "title": "投标文件",
        "level": 0,
        "order": 0,
        "mandatory": True,
        "summary": "",
        "writing_spec": "",
        "children": [
            {
                "id": "bid-001",
                "title": "投标函",
                "level": 1,
                "order": 1,
                "mandatory": True,
                "summary": "承诺函",
                "writing_spec": "签字盖章",
                "children": [],
            },
            {
                "id": "bid-002",
                "title": "技术方案",
                "level": 1,
                "order": 2,
                "mandatory": True,
                "summary": "技术响应",
                "writing_spec": "详述技术路线",
                "children": [],
            },
        ],
    },
    "changes_summary": "initial",
}


class GenCatalogFakeLLM(FakeLLMClient):
    def complete_with_meta(self, messages, *, response_format="text", timeout=None):
        user = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")

        if "目录优化评估" in user:
            plan_count = sum(
                1
                for c in self.calls
                if "目录优化评估" in "\n".join(
                    str(m.get("content", "")) for m in c.get("messages", []) if m.get("role") == "user"
                )
            )
            if plan_count >= 1:
                payload = {
                    "needs_optimization": True,
                    "refinement_plan": "补充技术方案撰写规范与得分点对应说明",
                }
            else:
                payload = {
                    "needs_optimization": False,
                    "refinement_plan": "摘录未要求调整投标函结构",
                }
        elif "执行目录更新" in user:
            outline = json.loads(json.dumps(_INITIAL["outline"]))
            for child in outline["children"]:
                if child["id"] == "bid-002":
                    child["writing_spec"] = "详述技术路线与得分点对应"
            payload = {"outline": outline, "changes_summary": "refined"}
        else:
            payload = _INITIAL

        text = json.dumps(payload, ensure_ascii=False)
        self.calls.append({"messages": messages, "response_format": response_format, "timeout": timeout})
        return LLMCompletionResult(text=text)
