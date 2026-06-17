from __future__ import annotations


def logical_to_markdown(logical_rows: list[list[str]]) -> str:
    if not logical_rows:
        return ""
    col_count = max(len(r) for r in logical_rows)
    normalized = [r + [""] * (col_count - len(r)) for r in logical_rows]
    header = normalized[0]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join('---' for _ in range(col_count))} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in normalized[1:])
    return "\n".join(lines)


def logical_to_llm_fallback(logical_rows: list[list[str]]) -> str:
    lines = ["【表格:原始】"]
    for i, row in enumerate(logical_rows, start=1):
        lines.append(f"行{i}: " + " | ".join(row))
    return "\n".join(lines)


def records_to_llm_text(
    layout: str,
    records: list[dict[str, str]],
    *,
    logical_rows: list[list[str]],
) -> str:
    if layout == "personnel_dual_row":
        lines = ["【表格:人员信息】"]
        for i, rec in enumerate(records, start=1):
            lines.append(f"--- 记录 {i} ---")
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if layout == "simple":
        lines = ["【表格:列表】"]
        for i, rec in enumerate(records, start=1):
            lines.append(f"--- 行 {i} ---")
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if layout == "key_value":
        lines = ["【表格:键值】"]
        for rec in records:
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return logical_to_llm_fallback(logical_rows)
