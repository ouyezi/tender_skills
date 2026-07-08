from __future__ import annotations

from tender_insights.bid_diagnose.models import TaskDefinition
from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS

TASK_DEFINITIONS: list[TaskDefinition] = [
    TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills=DIAGNOSIS_SKILLS,
        output_requirement=DIAGNOSIS_CHECKLIST,
        output_field="import_diagnose",
    ),
    TaskDefinition(
        step_index=2,
        current_task="diagnose_result",
        task_skills=(
            "你擅长结合诊断重点、累积诊断与分片正文，产出可执行的段级标书诊断结论。"
        ),
        output_requirement=(
            "结合 import_diagnose 诊断重点、diagnose_before 累积诊断、analysis_report 解读概要、"
            "sec_in_total 本分片定位与 current_chunk 正文，输出 Markdown 段级诊断结果。"
        ),
        output_field="diagnose_result",
    ),
    TaskDefinition(
        step_index=3,
        current_task="update_diagnose",
        task_skills="你擅长将段级诊断合并进整体诊断，保持结构清晰、避免重复遗漏。",
        output_requirement=(
            "将本段段级 diagnose_result 合并进 diagnose_before，输出更新后的完整累积诊断 Markdown，"
            "供后续分片继续滚动使用。"
        ),
        output_field="diagnose_result",
    ),
]
