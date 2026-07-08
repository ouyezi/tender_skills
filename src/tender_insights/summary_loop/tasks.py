from __future__ import annotations

from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS
from tender_insights.summary_loop.models import TaskDefinition

TASK_DEFINITIONS: list[TaskDefinition] = [
    TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="你擅长阅读政府采购/招投标文件，能准确提炼项目背景、采购范围、时间节点与关键要求。",
        output_requirement="输出结构化 Markdown 标书概要，包含：项目名称、采购人、预算/限价（如有）、时间节点、采购内容摘要。",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    ),
    TaskDefinition(
        step_index=2,
        current_task="get_score_points",
        task_skills="你擅长从招标文件评审办法/评分标准章节提取得分项与分值构成。",
        output_requirement="输出 Markdown 列表，每条得分项包含：名称、分值、评分要点、证明材料要求（如有）。",
        output_field="score_points",
        step_filename="02_score_points.txt",
    ),
    TaskDefinition(
        step_index=3,
        current_task="get_disqualification_items",
        task_skills="你擅长识别招标文件中的废标条款、否决投标情形与实质性要求。",
        output_requirement="输出 Markdown 列表，每条废标项包含：条款来源（章节/条款号）、废标情形、投标人注意事项。",
        output_field="disqualification_items",
        step_filename="03_disqualification_items.txt",
    ),
    TaskDefinition(
        step_index=4,
        current_task="get_tender_responds",
        task_skills="你擅长梳理投标文件格式要求、响应性条款与必须提交的证明材料。",
        output_requirement="输出 Markdown，分节列出：投标文件组成、格式要求、必须响应的条款、证明材料清单。",
        output_field="tender_responds",
        step_filename="04_tender_responds.txt",
    ),
    TaskDefinition(
        step_index=5,
        current_task="clearify_needs",
        task_skills="你擅长识别招标文件中描述不清晰、存在歧义或信息缺失的条款，判断哪些内容需要向发标方澄清确认。",
        output_requirement="从招标文件中找出需与发标方确认的不清晰内容。若无，仅输出「无」；若有，逐条给出问题描述、条款出处及建议确认事项。",
        output_field="needs_clarify",
        step_filename="05_clarify_needs.txt",
    ),
    TaskDefinition(
        step_index=6,
        current_task="diagnosis_criteria",
        task_skills=DIAGNOSIS_SKILLS,
        output_requirement=DIAGNOSIS_CHECKLIST,
        output_field="diagnosis_criteria",
        step_filename="06_diagnosis_criteria.md",
    ),
    TaskDefinition(
        step_index=7,
        current_task="generate_report",
        task_skills="你擅长将招标解读与标书诊断结果整合为面向投标团队的完整解读报告。",
        output_requirement=(
            "综合 tender_summary、score_points、disqualification_items、tender_responds、"
            "needs_clearify、diagnosis_criteria，输出完整 Markdown 解读报告，"
            "含执行摘要、得分策略建议、废标风险提示、澄清事项、诊断要点摘要与投标准备清单。"
        ),
        output_field="analysis_report",
        step_filename="07_analysis_report.md",
    ),
]
