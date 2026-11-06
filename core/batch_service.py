"""Shared batch analysis used by the operator UI and the batch API."""
import os
from pathlib import Path
from io import BytesIO
import pandas as pd
from core.input_validation import SurveyInputError
from scripts.batch_deepseek_feedback import filter_valid_feedback
from llm.usage import capture_usage
from core.survey_processor import (
    load_question_mapping,
    read_survey_file,
    wide_to_long,
    map_questions,
    detect_anomalies,
    get_valid_ratings,
    split_rating_and_text,
    classify_questions,
    compute_auto_coverage,
    apply_auto_category,
)
from core.statistics import (
    compute_global_common_stats,
    compute_course_common_stats,
    compute_period_specific_stats,
    compute_session_stats,
    compute_overview_stats,
    compute_feedback_overview,
)
from core.text_cleaner import (
    clean_text_feedback,
    generate_feedback_summary,
)
from core.output_writer import (
    write_output_excel,
    build_file_identification,
    build_pending_review,
    build_feedback_frequency,
)
from scripts.ai_pipeline import run_ai_pipeline


class Progress:
    def __init__(self, callback=None):
        self.callback = callback or (lambda message: None)
    def info(self, message):
        self.callback(message)
    warning = error = info
    def empty(self):
        pass


def run_base_analysis(survey_files, mapping_file, temp_dir, progress=None):
    names = [name for name, data in survey_files] + [mapping_file[0]]
    if len(names) != len(set(names)):
        raise SurveyInputError("Duplicate upload filenames")
    for name in names:
        if name != Path(name).name or any(char in name for char in '/\\:\0') or not name.lower().endswith('.xlsx'):
            raise SurveyInputError("Invalid workbook filename")
    progress_container = Progress(progress)
    saved_survey_paths = []
    for fname, fdata in survey_files:
        save_path = os.path.join(temp_dir, fname)
        with open(save_path, "wb") as f:
            f.write(fdata)
        saved_survey_paths.append(save_path)

    config_path = os.path.join(temp_dir, mapping_file[0])
    with open(config_path, "wb") as f:
        f.write(mapping_file[1])

    progress_container.info("正在加载题目映射配置...")
    mapping_df = load_question_mapping(config_path)

    all_long_tables = []
    all_question_headers = []
    file_course_sessions = []
    all_anomalies = []
    filename_issues = []

    file_count = len(saved_survey_paths)
    for i, filepath in enumerate(saved_survey_paths):
        fname = os.path.basename(filepath)
        progress_container.info(f"正在处理文件 ({i+1}/{file_count}): {fname}")
        try:
            cn, sn, df_raw, qh, mc = read_survey_file(filepath)
            if sn == "未知期次":
                filename_issues.append({"文件名": fname, "原因": "无法识别课程期次，请使用 课程名称_第XX期.xlsx"})
            if (cn, sn) in [(row[0], row[1]) for row in file_course_sessions]:
                raise SurveyInputError("同一课程期次存在多个文件，请合并并确认答卷唯一性")
            file_course_sessions.append((cn, sn, len(df_raw), len(qh)))
            df_long = wide_to_long(df_raw, qh)
            df_long = map_questions(df_long, mapping_df)
            anomalies = detect_anomalies(df_long)
            if not anomalies.empty:
                all_anomalies.append(anomalies)
            all_long_tables.append(df_long)
            all_question_headers.extend(qh)
        except Exception as e:
            filename_issues.append({"文件名": fname, "原因": f"处理异常: {e}"})
            progress_container.warning(f"文件 {fname} 处理异常: {e}")
            continue

    if not all_long_tables:
        progress_container.error("没有文件被成功处理")
        return None

    progress_container.info("正在合并数据...")
    df_all_long = pd.concat(all_long_tables, ignore_index=True)
    anomalies_combined = pd.concat(all_anomalies, ignore_index=True) if all_anomalies else pd.DataFrame()

    progress_container.info("正在检测异常评分...")
    valid_ratings = get_valid_ratings(df_all_long)
    all_ratings = df_all_long[df_all_long["question_type"] == "rating"].copy()
    _, text_df = split_rating_and_text(df_all_long)

    progress_container.info("正在分类题目...")
    auto_coverage_df, auto_category_map = compute_auto_coverage(df_all_long, mapping_df)
    df_all_long, valid_ratings = apply_auto_category(df_all_long, valid_ratings, auto_category_map)
    all_ratings["auto_category"] = all_ratings["standard_question"].map(auto_category_map)
    all_ratings["auto_category"] = all_ratings["auto_category"].fillna("unknown")

    all_course_sessions_data = df_all_long[["course_name", "session"]].drop_duplicates()
    total_course_sessions = len(all_course_sessions_data)
    unique_session_labels = df_all_long["session"].nunique()

    question_coverage = classify_questions(mapping_df, all_question_headers)
    file_identification = build_file_identification(saved_survey_paths, file_course_sessions)

    progress_container.info("正在计算统计数据...")
    global_stats = compute_global_common_stats(valid_ratings, all_ratings)
    course_common_stats = compute_course_common_stats(valid_ratings, all_ratings)
    period_specific_stats = compute_period_specific_stats(valid_ratings, all_ratings)
    session_stats = compute_session_stats(valid_ratings, all_ratings)

    progress_container.info("正在清洗文本反馈...")
    cleaned_feedback = clean_text_feedback(text_df)
    feedback_summary = generate_feedback_summary(cleaned_feedback)
    feedback_overview = compute_feedback_overview(text_df, cleaned_feedback)
    feedback_frequency = build_feedback_frequency(cleaned_feedback)

    progress_container.info("正在生成数据总览...")
    overview = compute_overview_stats(
        valid_ratings, df_all_long, text_df, anomalies_combined, saved_survey_paths,
        feedback_overview=feedback_overview,
        total_course_sessions=total_course_sessions,
        unique_session_labels=unique_session_labels,
    )

    progress_container.info("正在构建待确认列表...")
    pending_review = build_pending_review(df_all_long, anomalies_combined, filename_issues,
                                         auto_coverage_df=auto_coverage_df)

    feedback_detail_cols = [
        "course_name", "session", "学员编号",
        "response_value", "feedback_clean", "feedback_label", "duplicate_count",
    ]
    feedback_detail = cleaned_feedback[[c for c in feedback_detail_cols if c in cleaned_feedback.columns]].copy()
    feedback_detail.rename(columns={
        "course_name": "课程名称",
        "session": "期次",
        "response_value": "原始反馈",
        "feedback_clean": "清洗后反馈",
        "feedback_label": "反馈类型",
        "duplicate_count": "重复次数",
    }, inplace=True)
    feedback_detail["是否空白"] = feedback_detail["反馈类型"].apply(lambda x: "是" if x == "纯空白反馈" else "否")
    feedback_detail["是否低信息"] = feedback_detail["反馈类型"].apply(lambda x: "是" if x == "低信息量反馈" else "否")

    normalized_long = df_all_long.copy()
    if "response_value" in normalized_long.columns:
        normalized_long["response_value"] = normalized_long["response_value"].astype(str)
    output_cols = [
        "学员编号", "course_name", "session", "original_question",
        "standard_question", "question_type", "max_score", "category", "response_value",
    ]
    normalized_long_output = normalized_long[[c for c in output_cols if c in normalized_long.columns]]

    mapping_detail = mapping_df.copy()
    if "max_score" in mapping_detail.columns:
        mapping_detail["max_score"] = mapping_detail["max_score"].astype(str)

    output_xlsx_path = os.path.join(temp_dir, "course_survey_analysis.xlsx")
    output_data = {
        "overview": overview,
        "file_identification": file_identification,
        "normalized_long": normalized_long_output,
        "question_mapping_result": mapping_detail,
        "question_coverage": question_coverage,
        "auto_coverage": auto_coverage_df,
        "global_common_stats": global_stats,
        "course_common_stats": course_common_stats,
        "period_specific_stats": period_specific_stats,
        "session_stats": session_stats,
        "feedback_summary": feedback_summary,
        "feedback_frequency": feedback_frequency,
        "feedback_detail": feedback_detail,
        "anomalies": anomalies_combined,
        "pending_review": pending_review,
    }

    progress_container.info("正在生成 Excel 报告...")
    write_output_excel(output_xlsx_path, output_data)

    progress_container.empty()

    return {
        "overview": overview,
        "file_identification": file_identification,
        "question_coverage": question_coverage,
        "auto_coverage": auto_coverage_df,
        "global_common_stats": global_stats,
        "course_common_stats": course_common_stats,
        "period_specific_stats": period_specific_stats,
        "session_stats": session_stats,
        "feedback_summary": feedback_summary,
        "feedback_frequency": feedback_frequency,
        "feedback_overview": feedback_overview,
        "feedback_detail": feedback_detail,
        "anomalies": anomalies_combined,
        "pending_review": pending_review,
        "output_xlsx_path": output_xlsx_path,
        "total_course_sessions": total_course_sessions,
        "unique_session_labels": unique_session_labels,
    }


AI_SHEETS = {
    "classification_detail": "AI反馈分类明细", "label_stats": "AI标签统计",
    "positive_summary": "AI正向评价", "negative_summary": "AI负向问题",
    "suggestion_summary": "AI改进建议", "course_overview": "课程期次反馈概览",
    "course_summary": "课程AI总结", "course_summary_detail": "课程AI总结明细",
    "trend_summary": "跨期趋势总结", "api_summary": "AI调用汇总", "errors": "AI错误记录",
    "model_usage": "模型调用明细",
    "review_plan": "建议人工审核",
}


def merge_ai_report(base_bytes, ai_results):
    output = BytesIO(base_bytes)
    with pd.ExcelWriter(output, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        for key, sheet in AI_SHEETS.items():
            frame = ai_results.get(key)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frame.to_excel(writer, sheet_name=sheet, index=False)
    return output.getvalue()


def run_batch_analysis(survey_files, mapping_file, temp_dir, enable_ai=False, progress=None):
    """One UI/API workflow, with explicit AI opt-in and a shared request budget."""
    if not survey_files or len(survey_files) > 10:
        raise SurveyInputError("每次请上传 1—10 份问卷")
    if sum(len(data) for _, data in survey_files) + len(mapping_file[1]) > 10 * 1024 * 1024:
        raise SurveyInputError("本次问卷与映射文件合计不能超过 10 MB")
    result = run_base_analysis(survey_files, mapping_file, temp_dir, progress)
    if result is None:
        raise SurveyInputError("没有成功读取的问卷，请检查格式与学员编号")
    base_bytes = Path(result["output_xlsx_path"]).read_bytes()
    result["base_xlsx_bytes"] = base_bytes
    result["complete_xlsx_bytes"] = base_bytes
    result["ai_results"] = None
    pending = result["pending_review"]
    result["analysis_status"] = "partial" if not pending.empty else "complete"
    if enable_ai:
        ai, report = run_feedback_analysis(result["feedback_detail"], base_bytes)
        result["ai_results"] = ai
        result["complete_xlsx_bytes"] = report
        if not ai["errors"].empty:
            result["analysis_status"] = "partial"
    return result


def run_feedback_analysis(feedback, base_bytes):
    """The initial run and later AI opt-in share limits, metrics and output."""
    effective = filter_valid_feedback(feedback)
    if len(effective) > 100:
        raise SurveyInputError("单次 AI 分析最多 100 条有效反馈，请缩小批次")
    if not effective.empty and effective["清洗后反馈"].astype(str).str.len().gt(2000).any():
        raise SurveyInputError("单条有效反馈不能超过 2000 字符")
    with capture_usage() as usage:
        ai = run_ai_pipeline(feedback)
    ai["model_usage"] = pd.DataFrame(usage)
    review_rows = []
    for kind in ("negative_summary", "suggestion_summary"):
        frame = ai.get(kind)
        if frame is None:
            continue
        for _, row in frame.iterrows():
            review_rows.append({
                "课程名称": row.get("课程名称", row.get("course_name", "")),
                "期次": row.get("期次", row.get("session", "")),
                "问题或建议": row.get("subcategory", ""),
                "涉及人数": row.get("反馈人数", 0),
                "统计分母人数": row.get("已分类反馈人数", 0),
                "人数占比": row.get("人数占比", 0),
                "严重程度": "待人工确认", "整改成本": "待人工确认",
                "负责人": "待指定", "是否采纳": "待审核",
            })
    ai["review_plan"] = pd.DataFrame(review_rows)
    actual_calls = len(usage)
    metrics = ai.get("api_summary")
    if metrics is not None and not metrics.empty:
        metrics.loc[metrics["指标"] == "API实际调用数", "指标"] = "分类阶段未命中缓存记录数"
        ai["api_summary"] = pd.concat([metrics, pd.DataFrame([
            {"指标": "模型实际请求次数（含总结与重试）", "数值": actual_calls},
            {"指标": "有 token 记录的请求数", "数值": sum(event["input_tokens"] is not None for event in usage)},
        ])], ignore_index=True)
    return ai, merge_ai_report(base_bytes, ai)
