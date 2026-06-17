from __future__ import annotations

import re

LayoutType = str

_PERSONNEL_HEADER = re.compile(
    r"姓名|性别|学历|角色|职务|岗位|本项目工作角色|人员|工号"
)
_PERSONNEL_EXT = re.compile(
    r"级别|年龄|毕业学校|从业年限|资质证书|职称|专业|工作年限"
)


def _match_ratio(cells: list[str], pattern: re.Pattern[str]) -> float:
    if not cells:
        return 0.0
    hits = sum(1 for c in cells if pattern.search(c.strip()))
    return hits / len(cells)


def classify_layout(logical_rows: list[list[str]]) -> tuple[LayoutType, list[list[int]]]:
    if not logical_rows:
        return "fallback", []

    col_count = len(logical_rows[0])

    if (
        len(logical_rows) >= 4
        and len(logical_rows) % 4 == 0
        and all(len(r) == col_count for r in logical_rows)
    ):
        groups: list[list[int]] = []
        ok = True
        for start in range(0, len(logical_rows), 4):
            r0, _, r2, _ = logical_rows[start : start + 4]
            if _match_ratio(r0, _PERSONNEL_HEADER) < 0.5:
                ok = False
                break
            if _match_ratio(r2, _PERSONNEL_EXT) < 0.5:
                ok = False
                break
            groups.append([start, start + 1, start + 2, start + 3])
        if ok:
            return "personnel_dual_row", groups

    if len(logical_rows) >= 2 and all(len(r) == col_count for r in logical_rows):
        if (
            _match_ratio(logical_rows[0], _PERSONNEL_HEADER) < 0.5
            and _match_ratio(logical_rows[0], _PERSONNEL_EXT) < 0.5
        ):
            return "simple", []

    if col_count == 2 and len(logical_rows) >= 2:
        return "key_value", []

    return "fallback", []


def build_records(
    logical_rows: list[list[str]],
    layout: LayoutType,
    record_groups: list[list[int]],
) -> list[dict[str, str]]:
    if layout == "personnel_dual_row":
        records: list[dict[str, str]] = []
        for group in record_groups:
            if len(group) < 4:
                continue
            r0, r1, r2, r3 = (logical_rows[i] for i in group)
            record: dict[str, str] = {}
            for h, v in zip(r0, r1, strict=False):
                if h.strip():
                    record[h.strip()] = v.strip()
            for h, v in zip(r2, r3, strict=False):
                if h.strip():
                    record[h.strip()] = v.strip()
            records.append(record)
        return records

    if layout == "simple" and len(logical_rows) >= 2:
        headers = logical_rows[0]
        out: list[dict[str, str]] = []
        for row in logical_rows[1:]:
            out.append({h.strip(): v.strip() for h, v in zip(headers, row, strict=False) if h.strip()})
        return out

    if layout == "key_value":
        record: dict[str, str] = {}
        for row in logical_rows:
            if len(row) >= 2:
                key, val = row[0].strip(), row[1].strip()
                if key:
                    record[key] = val
        return [record] if record else []

    return []
