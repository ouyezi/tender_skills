from __future__ import annotations

import base64

from openai import OpenAI

from doc_chunk.llm.openai_client import llm_extra_body, resolve_llm_settings_from_env


class OcrClient:
    def __init__(self, *, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_env(cls, *, model: str) -> OcrClient:
        api_key, _, base_url = resolve_llm_settings_from_env()
        return cls(model=model, api_key=api_key, base_url=base_url)

    def recognize_image_bytes(self, image_bytes: bytes, *, mime: str = "image/png") -> str:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        extra = llm_extra_body(base_url=self.base_url)
        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的全部文字，按阅读顺序输出纯文本，不要解释。",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "timeout": 120.0,
        }
        if extra is not None:
            kwargs["extra_body"] = extra
        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()
