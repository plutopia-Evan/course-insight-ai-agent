"""Regenerate summaries from existing classifications, without reclassification."""

import json
import tempfile
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

from core.input_validation import SurveyInputError
from core.analysis_results import save_analysis_result
from core.report_storage import new_report_path
from core.report_delivery import attach_report_copy
from llm.usage import capture_usage
from llm.deepseek_feedback_analyzer import load_taxonomy, _build_sentiment_rules
from llm.ai_summary_generator import generate_summaries
from scripts.ai_feedback_statistics import generate_statistics

FIELDS = ["course_name", "session", "respondent_id", "feedback_id", "category", "subcategory", "sentiment", "summary", "evidence"]


def read_classifications(path):
    try:
        frame = pd.read_excel(path, sheet_name="AI反馈分类明细", dtype=object, nrows=501)
    except (ValueError, OSError, BadZipFile) as exc:
        raise SurveyInputError("请上传包含“AI反馈分类明细”工作表的有效 Excel 报告") from exc
    if not 1 <= len(frame) <= 500:
        raise SurveyInputError("总结重生成每次接受 1—500 条已分类意见")
    missing = set(FIELDS) - set(frame.columns)
    if missing:
        raise SurveyInputError(f"分类明细缺少必要列：{sorted(missing)}")
    frame = frame[FIELDS].copy()
    for name in FIELDS:
        if frame[name].isna().any() or frame[name].astype(str).str.strip().eq("").any():
            raise SurveyInputError(f"分类明细 {name} 不能为空")
        frame[name] = frame[name].astype(str)
        limit = 2000 if name == "evidence" else 20 if name == "summary" else 128
        if frame[name].str.len().gt(limit).any():
            raise SurveyInputError(f"分类明细 {name} 超过 {limit} 字符限制")
    if len(frame[["course_name", "session"]].drop_duplicates()) > 6:
        raise SurveyInputError("每次最多重新生成 6 个课程期次的总结")
    if frame.duplicated(subset=[name for name in FIELDS if name != "summary"]).any():
        raise SurveyInputError("分类明细有完全重复的意见，请先确认重复记录")
    taxonomy = load_taxonomy()
    rules = _build_sentiment_rules(taxonomy)
    for _, row in frame.iterrows():
        if row["subcategory"] not in taxonomy["categories"].get(row["category"], []):
            raise SurveyInputError("分类明细包含不属于当前标签体系的分类")
        if row["sentiment"] not in rules[row["subcategory"]]:
            raise SurveyInputError("分类明细的标签与反馈类型不一致")
    return frame


def replay_summaries(path, include_report=False, use_cache=True):
    frame = read_classifications(path)
    with tempfile.TemporaryDirectory(prefix="summary-replay-") as directory:
        work = Path(directory)
        classified = work / "classified.xlsx"
        statistics_path = work / "statistics.xlsx"
        summary_path = work / "summaries.xlsx"
        frame.to_excel(classified, sheet_name="AI反馈分类明细", index=False)
        generate_statistics(str(classified), str(statistics_path))
        with capture_usage() as usage:
            generate_summaries(str(statistics_path), str(summary_path), use_cache=use_cache, include_trends=False)
        tables = {
            "course_summary": pd.read_excel(summary_path, sheet_name="课程AI总结"),
            "course_summary_detail": pd.read_excel(summary_path, sheet_name="课程AI总结明细"),
            "errors": pd.read_excel(summary_path, sheet_name="API调用错误记录"),
            "api_summary": pd.read_excel(summary_path, sheet_name="生成汇总"),
            "course_overview": pd.read_excel(statistics_path, sheet_name="课程期次反馈概览"),
            "classification_detail": frame,
            "model_usage": pd.DataFrame(usage),
        }
        with pd.ExcelWriter(summary_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            frame.to_excel(writer, sheet_name="AI反馈分类明细", index=False)
            tables["model_usage"].to_excel(writer, sheet_name="模型调用明细", index=False)
            tables["course_overview"].to_excel(writer, sheet_name="源统计概览", index=False)
        report = new_report_path("课程总结重生成", "多期")
        content = summary_path.read_bytes()
        report.write_bytes(content)
        as_records = lambda data: json.loads(data.to_json(orient="records", force_ascii=False))
        errors = as_records(tables["errors"])
        payload = {
            "course_name": "课程总结重生成", "session": "多期", "report_path": str(report),
            "summary": {
                "analysis_status": "partial" if errors else "complete", "profile": "summary_replay",
                "course_session_count": len(frame[["course_name", "session"]].drop_duplicates()),
                "student_count": len(frame[["course_name", "session", "respondent_id"]].drop_duplicates()),
                "feedback_response_count": len(frame[["course_name", "session", "feedback_id"]].drop_duplicates()),
                "feedback_item_count": len(frame), "summary_success_count": len(tables["course_summary"]),
                "summary_failed_count": len(errors), "classification_requests": 0,
                "summary_requests": len(usage), "summary_cache_enabled": use_cache,
                "source_kind": "uploaded_classification_results",
            },
            "feedback_errors": errors, "feedback_results": as_records(frame), "model_usage": usage,
            "ai_tables": {name: as_records(data) for name, data in tables.items()},
        }
        return attach_report_copy(save_analysis_result(payload), report.name, content, include_report)
