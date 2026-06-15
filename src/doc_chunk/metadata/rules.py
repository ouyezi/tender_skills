from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from doc_chunk.errors import ValidationError


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"classification config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValidationError("classification config must be a mapping")
    return data


def load_classification_rules(extension_path: Path | None = None) -> dict[str, Any]:
    default_path = Path(__file__).with_name("default_classification.yaml")
    base = _load_yaml(default_path)
    labels = dict(base.get("labels", {}))
    product_categories = list(base.get("product_categories", []))
    chapter_taxonomies = list(base.get("chapter_taxonomies", []))

    if extension_path is not None:
        ext = _load_yaml(Path(extension_path))
        for key, value in dict(ext.get("labels", {})).items():
            labels[key] = value
        if ext.get("product_categories"):
            product_categories = list(ext.get("product_categories", []))
        if ext.get("chapter_taxonomies"):
            chapter_taxonomies = list(ext.get("chapter_taxonomies", []))

    return {
        "labels": labels,
        "product_categories": product_categories,
        "chapter_taxonomies": chapter_taxonomies,
    }


def match_hint_aliases(text: str, entries: list[dict[str, Any]]) -> list[str]:
    lowered = text.lower()
    hints: list[str] = []
    for entry in entries:
        aliases = [str(item).lower() for item in entry.get("aliases", [])]
        hint = str(entry.get("hint", "")).strip()
        if not hint:
            continue
        if any(alias and alias in lowered for alias in aliases):
            if hint not in hints:
                hints.append(hint)
    return hints


def load_candidate_rules(extension_path: Path | None = None) -> list[dict[str, Any]]:
    default_path = Path(__file__).with_name("candidate_rules.yaml")
    base = _load_yaml(default_path)
    rules = list(base.get("rules", []))
    if extension_path is not None:
        ext = _load_yaml(Path(extension_path))
        if ext.get("rules"):
            rules.extend(ext.get("rules", []))
    return rules


def suggest_candidate_types(
    taxonomy_hints: list[str],
    *,
    classification_config: Path | None = None,
) -> dict[str, str]:
    if not taxonomy_hints:
        return {}
    hint_set = set(taxonomy_hints)
    for rule in load_candidate_rules(classification_config):
        rule_hints = set(rule.get("taxonomy_hints", []))
        if hint_set & rule_hints:
            result: dict[str, Any] = {}
            if rule.get("suggested_candidate_type"):
                result["suggested_candidate_type"] = str(rule["suggested_candidate_type"])
            if "suggested_knowledge_type" in rule:
                knowledge_type = rule.get("suggested_knowledge_type")
                result["suggested_knowledge_type"] = None if knowledge_type is None else str(knowledge_type)
            if result:
                return result
    return {}
