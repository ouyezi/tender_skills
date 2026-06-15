from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_chunk.llm.client import LLMClient
from doc_chunk.metadata.rules import load_classification_rules, match_hint_aliases, suggest_candidate_types

BUILTIN_TYPES = {"scheme", "product", "qualification", "other", "ignore"}
DIRECT_CANDIDATE_MAP = {
    "scheme": ("scheme", "scheme"),
    "product": ("product", "product"),
    "qualification": ("qualification", "qualification"),
    "ignore": ("ignore", None),
}


def _apply_direct_candidate_mapping(result: dict[str, Any]) -> dict[str, Any]:
    label = str(result.get("knowledge_type", ""))
    mapping = DIRECT_CANDIDATE_MAP.get(label)
    if mapping is None:
        return result
    candidate_type, knowledge_type = mapping
    result.setdefault("suggested_candidate_type", candidate_type)
    if knowledge_type is not None:
        result.setdefault("suggested_knowledge_type", knowledge_type)
    else:
        result.setdefault("suggested_knowledge_type", None)
    return result


def _attach_candidate_suggestions(result: dict[str, Any], classification_config: Any) -> dict[str, Any]:
    taxonomy_hints = result.get("chapter_taxonomy_hints", [])
    if taxonomy_hints:
        suggestions = suggest_candidate_types(
            taxonomy_hints,
            classification_config=Path(classification_config) if classification_config else None,
        )
        result.update(suggestions)
    return result


def _match_rule(text: str, rules: dict[str, Any]) -> tuple[str, str, float, str] | None:
    labels = dict(rules.get("labels", {}))
    lowered = text.lower()
    best: tuple[str, str, float, str] | None = None

    for label, cfg in labels.items():
        keywords = [str(item).lower() for item in cfg.get("keywords", [])]
        if not keywords:
            continue
        hits = [kw for kw in keywords if kw and kw in lowered]
        if not hits:
            continue
        confidence = min(0.99, 0.55 + 0.1 * len(hits))
        chapter_type = str(cfg.get("chapter_type", label))
        rationale = f"rule keywords matched: {', '.join(hits[:3])}"
        if best is None or confidence > best[2]:
            best = (label, chapter_type, confidence, rationale)

    return best


def _llm_classify(text: str, llm_client: LLMClient | None) -> tuple[str, str, float, str] | None:
    if llm_client is None:
        return None
    prompt = (
        "请将以下文本分类为 scheme/product/qualification/other 或自定义标签。"
        "返回JSON：knowledge_type, chapter_type, confidence, rationale。\n"
        f"{text[:3000]}"
    )
    raw = llm_client.complete(
        [{"role": "user", "content": prompt}],
        response_format="json",
        timeout=60.0,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    label = str(payload.get("knowledge_type", "other")).strip() or "other"
    chapter_type = str(payload.get("chapter_type", label)).strip() or label
    confidence = float(payload.get("confidence", 0.5))
    rationale = str(payload.get("rationale", "llm classification"))
    return (label, chapter_type, max(0.0, min(1.0, confidence)), rationale)


def classify_chunk(
    *,
    title: str,
    markdown: str,
    llm_client: LLMClient | None = None,
    classification_config: Any = None,
) -> dict[str, Any]:
    rules = load_classification_rules(classification_config)
    text = f"{title}\n{markdown}"

    product_hints = match_hint_aliases(text, rules.get("product_categories", []))
    taxonomy_hints = match_hint_aliases(text, rules.get("chapter_taxonomies", []))

    rule_result = _match_rule(text, rules)
    if rule_result is not None:
        label, chapter_type, confidence, rationale = rule_result
        result = {
            "knowledge_type": label if label in BUILTIN_TYPES else label,
            "chapter_type": chapter_type,
            "classification_confidence": confidence,
            "classification_source": "rule",
            "classification_rationale": rationale,
        }
        if product_hints:
            result["product_category_hints"] = product_hints
        if taxonomy_hints:
            result["chapter_taxonomy_hints"] = taxonomy_hints
        return _attach_candidate_suggestions(_apply_direct_candidate_mapping(result), classification_config)

    llm_result = _llm_classify(text, llm_client)
    if llm_result is not None:
        label, chapter_type, confidence, rationale = llm_result
        result = {
            "knowledge_type": label if label in BUILTIN_TYPES else label,
            "chapter_type": chapter_type,
            "classification_confidence": confidence,
            "classification_source": "llm",
            "classification_rationale": rationale,
        }
        if product_hints:
            result["product_category_hints"] = product_hints
        if taxonomy_hints:
            result["chapter_taxonomy_hints"] = taxonomy_hints
        return _attach_candidate_suggestions(_apply_direct_candidate_mapping(result), classification_config)

    result = {
        "knowledge_type": "other",
        "chapter_type": "其他",
        "classification_confidence": 0.2,
        "classification_source": "rule",
        "classification_rationale": "fallback default classification",
    }
    if product_hints:
        result["product_category_hints"] = product_hints
    if taxonomy_hints:
        result["chapter_taxonomy_hints"] = taxonomy_hints
    return _attach_candidate_suggestions(_apply_direct_candidate_mapping(result), classification_config)
