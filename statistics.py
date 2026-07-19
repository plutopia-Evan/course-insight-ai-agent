"""
课程问卷统计分析模块

功能:
- 评分题目统计：有效样本数、缺失数、平均分、标准差、中位数、最低分、最高分、
  满分率、低分率、百分制标准分
- 按不同维度聚合：全局公共题、课程公共题、单期特有题、各期次
"""

import logging
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def compute_rating_stats(valid_ratings: pd.DataFrame, all_ratings: pd.DataFrame,
                         group_cols: List[str]) -> pd.DataFrame:
    """对评分题按指定分组维度计算统计数据。

    Args:
        valid_ratings: 有效评分数据（已排除异常值），需含 numeric_value 列
        all_ratings: 全部评分数据（含缺失），用于计算缺失数
        group_cols: 分组列名列表

    Returns:
        包含各项统计指标的 DataFrame
    """
    stats_records = []

    for group_keys, group_valid in valid_ratings.groupby(group_cols, dropna=False):
        if not isinstance(group_keys, tuple):
            group_keys = (group_keys,)
        group_key_dict = dict(zip(group_cols, group_keys))

        if len(group_valid) == 0:
            continue

        scores = group_valid["numeric_value"].dropna().astype(float)
        if len(scores) == 0:
            continue

        max_score_val = group_valid["max_score"].iloc[0] if "max_score" in group_valid.columns else None
        if pd.isna(max_score_val):
            max_score_val = 5
        else:
            max_score_val = int(max_score_val)

        all_group = all_ratings.copy()
        for col, val in group_key_dict.items():
            if col in all_group.columns:
                all_group = all_group[all_group[col] == val]
        total_count = len(all_group)
        missing_count = all_group["response_value"].isna().sum() + (
            all_group["response_value"].astype(str).str.strip() == ""
        ).sum()

        n = len(scores)
        mean_val = scores.mean()
        std_val = scores.std(ddof=1) if n > 1 else 0.0
        median_val = scores.median()
        min_val = scores.min()
        max_val = scores.max()
        full_score_count = (scores == max_score_val).sum()
        full_score_rate = full_score_count / n if n > 0 else 0.0
        low_score_count = (scores <= 2).sum()
        low_score_rate = low_score_count / n if n > 0 else 0.0
        percentile_score = (mean_val / max_score_val * 100) if max_score_val > 0 else 0.0

        record = {
            **group_key_dict,
            "有效样本数": n,
            "缺失数": int(missing_count),
            "平均分": round(mean_val, 2),
            "标准差": round(std_val, 4),
            "中位数": round(median_val, 2),
            "最低分": round(min_val, 2),
            "最高分": round(max_val, 2),
            "满分率": round(full_score_rate, 4),
            "低分率": round(low_score_rate, 4),
            "百分制标准分": round(percentile_score, 2),
            "满分人数": int(full_score_count),
            "低分人数(≤2)": int(low_score_count),
            "总样本数": total_count,
        }
        stats_records.append(record)

    result = pd.DataFrame(stats_records)
    logger.info("统计计算完成，共 %d 个分组", len(result))
    return result


def compute_global_common_stats(valid_ratings: pd.DataFrame,
                                all_ratings: pd.DataFrame) -> pd.DataFrame:
    """计算全局公共题统计（所有课程、所有期次汇总）。

    Args:
        valid_ratings: 有效评分数据（需含 auto_category 列）
        all_ratings: 全部评分数据（需含 auto_category 列）

    Returns:
        全局公共题统计 DataFrame
    """
    cat_col = "auto_category" if "auto_category" in valid_ratings.columns else "category"
    common_data = valid_ratings[valid_ratings[cat_col].isin(["common", "global_common"])].copy()
    all_common_data = all_ratings[all_ratings[cat_col].isin(["common", "global_common"])].copy()
    if len(common_data) == 0:
        logger.warning("无全局公共题数据")
        return pd.DataFrame()
    result = compute_rating_stats(common_data, all_common_data, ["standard_question"])
    result.insert(0, "统计维度", "全局公共题")
    logger.info("全局公共题统计: %d 道题目", len(result))
    return result


def compute_course_common_stats(valid_ratings: pd.DataFrame,
                                all_ratings: pd.DataFrame) -> pd.DataFrame:
    """计算课程公共题统计（按课程分组）。

    Args:
        valid_ratings: 有效评分数据
        all_ratings: 全部评分数据

    Returns:
        课程公共题统计 DataFrame
    """
    cat_col = "auto_category" if "auto_category" in valid_ratings.columns else "category"
    course_common_data = valid_ratings[valid_ratings[cat_col] == "course_common"].copy()
    all_course_common = all_ratings[all_ratings[cat_col] == "course_common"].copy()
    if len(course_common_data) == 0:
        logger.warning("无课程公共题数据")
        return pd.DataFrame()
    result = compute_rating_stats(course_common_data, all_course_common,
                                  ["standard_question", "course_name"])
    result.insert(0, "统计维度", "课程公共题")
    logger.info("课程公共题统计: %d 条记录", len(result))
    return result


def compute_period_specific_stats(valid_ratings: pd.DataFrame,
                                  all_ratings: pd.DataFrame) -> pd.DataFrame:
    """计算单期特有题统计。

    Args:
        valid_ratings: 有效评分数据
        all_ratings: 全部评分数据

    Returns:
        单期特有题统计 DataFrame
    """
    cat_col = "auto_category" if "auto_category" in valid_ratings.columns else "category"
    period_data = valid_ratings[valid_ratings[cat_col] == "period_specific"].copy()
    all_period = all_ratings[all_ratings[cat_col] == "period_specific"].copy()
    if len(period_data) == 0:
        logger.warning("无单期特有题数据")
        return pd.DataFrame()
    result = compute_rating_stats(period_data, all_period,
                                  ["standard_question", "course_name", "session"])
    result.insert(0, "统计维度", "单期特有题")
    logger.info("单期特有题统计: %d 条记录", len(result))
    return result


def compute_session_stats(valid_ratings: pd.DataFrame,
                          all_ratings: pd.DataFrame) -> pd.DataFrame:
    """按期次计算所有评分题统计。

    Args:
        valid_ratings: 有效评分数据
        all_ratings: 全部评分数据

    Returns:
        各期次统计 DataFrame
    """
    result = compute_rating_stats(valid_ratings, all_ratings,
                                  ["course_name", "session", "standard_question"])
    result.insert(0, "统计维度", "期次评分")
    logger.info("期次评分统计: %d 条记录", len(result))
    return result


def compute_feedback_overview(text_feedback: pd.DataFrame,
                              cleaned_feedback: pd.DataFrame) -> dict:
    """计算反馈统计数据，返回清晰、含义一致的指标字典。

    Returns:
        dict with keys: 总问卷数, 空白反馈数, 非空反馈数, 低信息反馈数, 有效反馈数, 重复反馈组数
    """
    total_surveys = len(text_feedback)
    blank_count = (cleaned_feedback["feedback_label"] == "纯空白反馈").sum() if "feedback_label" in cleaned_feedback.columns else 0
    non_blank_count = len(text_feedback) - blank_count
    low_info_count = (cleaned_feedback["feedback_label"] == "低信息量反馈").sum() if "feedback_label" in cleaned_feedback.columns else 0
    valid_count = (cleaned_feedback["feedback_label"] == "有效反馈").sum() if "feedback_label" in cleaned_feedback.columns else 0
    dup_groups = cleaned_feedback[cleaned_feedback["duplicate_count"] > 1]["feedback_clean"].nunique() if "duplicate_count" in cleaned_feedback.columns else 0

    return {
        "总问卷数": int(total_surveys),
        "空白反馈数": int(blank_count),
        "非空反馈数": int(non_blank_count),
        "低信息反馈数": int(low_info_count),
        "有效反馈数": int(valid_count),
        "重复反馈组数": int(dup_groups),
    }


def compute_overview_stats(valid_ratings: pd.DataFrame,
                           all_ratings_long: pd.DataFrame,
                           text_feedback: pd.DataFrame,
                           anomalies: pd.DataFrame,
                           file_list: List[str],
                           feedback_overview: dict = None,
                           total_course_sessions: int = None,
                           unique_session_labels: int = None) -> pd.DataFrame:
    """生成数据总览统计。

    Args:
        valid_ratings: 有效评分数据
        all_ratings_long: 全部长表数据
        text_feedback: 文本反馈数据
        anomalies: 异常数据
        file_list: 文件列表
        feedback_overview: 反馈统计概览 dict
        total_course_sessions: （课程, 期次）唯一组合数
        unique_session_labels: 唯一期次标签数

    Returns:
        数据总览 DataFrame
    """
    unique_courses = all_ratings_long["course_name"].nunique()
    total_respondents = all_ratings_long[["学员编号", "course_name", "session"]].drop_duplicates().shape[0]
    total_ratings = len(all_ratings_long[all_ratings_long["question_type"] == "rating"])
    total_valid = len(valid_ratings)
    total_anomalies = len(anomalies)
    unique_questions = all_ratings_long["standard_question"].nunique()

    if total_course_sessions is None:
        total_course_sessions = all_ratings_long[["course_name", "session"]].drop_duplicates().shape[0]
    if unique_session_labels is None:
        unique_session_labels = all_ratings_long["session"].nunique()

    overview_rows = [
        {"指标": "分析文件数", "数值": len(file_list)},
        {"指标": "课程数", "数值": unique_courses},
        {"指标": "课程期次数", "数值": total_course_sessions},
        {"指标": "唯一期次标签数", "数值": unique_session_labels},
        {"指标": "总学员人次", "数值": total_respondents},
        {"指标": "评分题条目总数", "数值": total_ratings},
        {"指标": "有效评分数", "数值": total_valid},
        {"指标": "异常评分数", "数值": total_anomalies},
        {"指标": "标准题目数", "数值": int(unique_questions) if not pd.isna(unique_questions) else 0},
    ]

    if feedback_overview:
        feedback_metrics = [
            {"指标": "开放式反馈 - 总问卷数", "数值": feedback_overview["总问卷数"]},
            {"指标": "开放式反馈 - 空白反馈数", "数值": feedback_overview["空白反馈数"]},
            {"指标": "开放式反馈 - 非空反馈数", "数值": feedback_overview["非空反馈数"]},
            {"指标": "开放式反馈 - 低信息反馈数", "数值": feedback_overview["低信息反馈数"]},
            {"指标": "开放式反馈 - 有效反馈数", "数值": feedback_overview["有效反馈数"]},
            {"指标": "开放式反馈 - 重复反馈组数", "数值": feedback_overview["重复反馈组数"]},
        ]
        overview_rows.extend(feedback_metrics)

    overview = pd.DataFrame(overview_rows)
    logger.info("数据总览生成完成")
    return overview
