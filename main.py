"""
课程问卷智能分析工具 - 主入口

功能: 批量读取课程问卷 Excel，清洗、映射、统计、生成分析报告

用法:
    python main.py

配置:
    - 输入目录: data/input
    - 题目映射: config/question_mapping.xlsx
    - 输出目录: data/output
"""

import os
import sys
import logging
import glob
from datetime import datetime

import pandas as pd

from survey_processor import (
    load_question_mapping,
    read_survey_file,
    wide_to_long,
    map_questions,
    detect_anomalies,
    get_valid_ratings,
    split_rating_and_text,
    classify_questions,
    parse_filename,
    compute_auto_coverage,
    apply_auto_category,
)
from statistics import (
    compute_global_common_stats,
    compute_course_common_stats,
    compute_period_specific_stats,
    compute_session_stats,
    compute_overview_stats,
    compute_feedback_overview,
)
from text_cleaner import (
    clean_text_feedback,
    generate_feedback_summary,
)
from output_writer import (
    write_output_excel,
    build_file_identification,
    build_pending_review,
    build_feedback_frequency,
)


def setup_logging(log_dir: str = "data/output") -> logging.Logger:
    """配置日志系统。

    Args:
        log_dir: 日志目录

    Returns:
        根 logger
    """
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, f"survey_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter("[%(levelname)-5s] %(message)s")
    console_handler.setFormatter(console_fmt)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def main():
    """主流程：按顺序执行所有分析步骤并生成最终输出。"""
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("课程问卷智能分析工具 v1.0")
    logger.info("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, "data", "input")
    config_path = os.path.join(base_dir, "config", "question_mapping.xlsx")
    output_dir = os.path.join(base_dir, "data", "output")
    output_file = os.path.join(output_dir, "course_survey_analysis.xlsx")

    os.makedirs(output_dir, exist_ok=True)

    file_list = sorted(glob.glob(os.path.join(input_dir, "*.xlsx")))
    if not file_list:
        logger.error("data/input 目录中未找到 xlsx 文件")
        sys.exit(1)
    logger.info("找到 %d 个问卷文件", len(file_list))

    try:
        mapping_df = load_question_mapping(config_path)
    except Exception as e:
        logger.error("加载题目映射失败: %s", e)
        sys.exit(1)

    all_long_tables = []
    all_question_headers = []
    file_course_sessions = []
    all_anomalies = []
    filename_issues = []

    for filepath in file_list:
        try:
            filename = os.path.basename(filepath)
            course_name, session = parse_filename(filename)
            if session == "未知期次":
                filename_issues.append({"文件名": filename, "原因": "文件名格式不符合预期，无法解析期次"})

            course_name_raw, session_raw, df_raw, question_headers, meta_cols = read_survey_file(filepath)
            row_count = len(df_raw)
            q_count = len(question_headers)
            file_course_sessions.append((course_name_raw, session_raw, row_count, q_count))

            df_long = wide_to_long(df_raw, question_headers)
            df_long = map_questions(df_long, mapping_df)

            anomalies = detect_anomalies(df_long)
            if not anomalies.empty:
                all_anomalies.append(anomalies)

            all_long_tables.append(df_long)
            all_question_headers.extend(question_headers)
        except Exception as e:
            logger.error("处理文件 %s 时出错: %s", filepath, e)
            filename_issues.append({"文件名": os.path.basename(filepath), "原因": f"文件处理异常: {e}"})
            continue

    if not all_long_tables:
        logger.error("没有任何文件成功处理")
        sys.exit(1)

    df_all_long = pd.concat(all_long_tables, ignore_index=True)
    logger.info("合并后长表共 %d 行", len(df_all_long))

    anomalies_combined = pd.DataFrame()
    if all_anomalies:
        anomalies_combined = pd.concat(all_anomalies, ignore_index=True)
        logger.info("异常数据总计 %d 条", len(anomalies_combined))

    valid_ratings = get_valid_ratings(df_all_long)
    all_ratings = df_all_long[df_all_long["question_type"] == "rating"].copy()
    _, text_df = split_rating_and_text(df_all_long)

    auto_coverage_df, auto_category_map = compute_auto_coverage(df_all_long, mapping_df)
    df_all_long, valid_ratings = apply_auto_category(df_all_long, valid_ratings, auto_category_map)
    all_ratings["auto_category"] = all_ratings["standard_question"].map(auto_category_map)
    all_ratings["auto_category"] = all_ratings["auto_category"].fillna("unknown")

    all_course_sessions = df_all_long[["course_name", "session"]].drop_duplicates()
    total_course_sessions = len(all_course_sessions)
    unique_session_labels = df_all_long["session"].nunique()

    question_coverage = classify_questions(mapping_df, all_question_headers)

    file_identification = build_file_identification(file_list, file_course_sessions)

    global_stats = compute_global_common_stats(valid_ratings, all_ratings)
    course_common_stats = compute_course_common_stats(valid_ratings, all_ratings)
    period_specific_stats = compute_period_specific_stats(valid_ratings, all_ratings)
    session_stats = compute_session_stats(valid_ratings, all_ratings)

    cleaned_feedback = clean_text_feedback(text_df)
    feedback_summary = generate_feedback_summary(cleaned_feedback)
    feedback_overview = compute_feedback_overview(text_df, cleaned_feedback)
    feedback_frequency = build_feedback_frequency(cleaned_feedback)

    overview = compute_overview_stats(
        valid_ratings, df_all_long, text_df, anomalies_combined, file_list,
        feedback_overview=feedback_overview,
        total_course_sessions=total_course_sessions,
        unique_session_labels=unique_session_labels,
    )

    pending_review = build_pending_review(df_all_long, anomalies_combined, filename_issues,
                                         auto_coverage_df=auto_coverage_df)

    normalized_long = df_all_long.copy()
    if "response_value" in normalized_long.columns:
        normalized_long["response_value"] = normalized_long["response_value"].astype(str)

    output_cols = ["学员编号", "course_name", "session", "original_question",
                   "standard_question", "question_type", "max_score", "category",
                   "response_value"]
    normalized_long_output = normalized_long[[c for c in output_cols if c in normalized_long.columns]]

    question_mapping_result = mapping_df.copy()

    mapping_detail = mapping_df.copy()
    if "max_score" in mapping_detail.columns:
        mapping_detail["max_score"] = mapping_detail["max_score"].astype(str)

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

    try:
        write_output_excel(output_file, output_data)
    except Exception as e:
        logger.error("写入输出文件失败: %s", e)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("分析完成！输出文件: %s", output_file)
    logger.info("  - 数据总览: %d 项指标", len(overview))
    logger.info("  - 文件识别: %d 个文件", len(file_identification))
    logger.info("  - 标准化长表: %d 行", len(normalized_long_output))
    logger.info("  - 异常数据: %d 条", len(anomalies_combined))
    logger.info("  - 全局公共题统计: %d 道题", len(global_stats))
    logger.info("  - 课程公共题统计: %d 条", len(course_common_stats))
    logger.info("  - 单期特有题统计: %d 条", len(period_specific_stats))
    logger.info("  - 期次评分统计: %d 条", len(session_stats))
    logger.info("  - 开放式反馈: %d 条 (空白:%d 低信息:%d 有效:%d 重复组:%d)",
                len(feedback_summary),
                feedback_overview["空白反馈数"],
                feedback_overview["低信息反馈数"],
                feedback_overview["有效反馈数"],
                feedback_overview["重复反馈组数"])
    logger.info("  - 反馈频次汇总: %d 条", len(feedback_frequency))
    logger.info("  - 人工待确认: %d 条", len(pending_review))
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
