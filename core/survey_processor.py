"""
课程问卷数据处理模块

功能:
- 读取 question_mapping.xlsx 配置
- 批量加载 data/input 中的问卷 Excel 文件
- 从文件名解析课程名称和期次
- 宽表转长表
- 题目映射与分类
- 评分异常检测
"""

import os
import re
import logging
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
import openpyxl

logger = logging.getLogger(__name__)


def load_question_mapping(config_path: str) -> pd.DataFrame:
    """读取题目映射配置文件。

    Args:
        config_path: question_mapping.xlsx 文件路径

    Returns:
        包含列 [original_question, standard_question, question_type, max_score, category] 的 DataFrame
    """
    logger.info("加载题目映射配置: %s", config_path)
    df = pd.read_excel(config_path, engine="openpyxl")
    required_cols = {"original_question", "standard_question", "question_type", "max_score", "category"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"question_mapping.xlsx 缺少必要列: {missing}")
    df["max_score"] = df["max_score"].astype("Int64")
    logger.info("题目映射加载完成，共 %d 条映射记录", len(df))
    return df


def parse_filename(filename: str) -> Tuple[str, str]:
    """从文件名解析课程名称和期次。

    支持格式: "课程名称_第XX期.xlsx" 或 "课程名称_第XX期"
    也兼容 "课程名称_第01期.xlsx" 中的中文数字混合。

    Args:
        filename: 不含路径的文件名

    Returns:
        (course_name, session) 元组
    """
    basename = os.path.splitext(filename)[0]
    pattern = r"^(.+?)_第(\d+)期$"
    match = re.match(pattern, basename)
    if match:
        course_name = match.group(1)
        session = f"第{int(match.group(2)):02d}期"
        logger.debug("解析文件名: %s -> course=%s, session=%s", filename, course_name, session)
        return course_name, session
    else:
        logger.warning("文件名格式不符合预期: %s，将使用原始文件名作为课程名", filename)
        return basename, "未知期次"


def detect_question_column_indices(headers: List[str]) -> Tuple[int, int, List[int]]:
    """识别问卷表头中的学员编号列、提交时间列和题目列。

    学员编号列: 包含 '学员' 或 '编号' 或 'ID'（不区分大小写）
    提交时间列: 包含 '提交' 或 '时间' 或 '日期'
    题目列: 其余列

    Args:
        headers: 表头列表

    Returns:
        (student_id_idx, submit_time_idx, question_indices)
    """
    student_id_idx = None
    submit_time_idx = None
    question_indices = []

    for i, h in enumerate(headers):
        h_str = str(h).strip()
        if student_id_idx is None and ("学员" in h_str or "编号" in h_str or h_str.upper() == "ID"):
            student_id_idx = i
        elif submit_time_idx is None and ("提交" in h_str or "时间" in h_str or "日期" in h_str):
            submit_time_idx = i
        else:
            question_indices.append(i)

    if student_id_idx is None:
        student_id_idx = 0
    if submit_time_idx is not None:
        question_indices = [i for i in question_indices if i != student_id_idx]

    return student_id_idx, submit_time_idx, question_indices


def read_survey_file(filepath: str) -> Tuple[str, str, pd.DataFrame, List[str], List[str]]:
    """读取单个问卷文件并返回处理后的数据。

    Args:
        filepath: 文件路径

    Returns:
        (course_name, session, df_raw, question_headers, metadata_headers)
    """
    logger.info("读取文件: %s", filepath)
    df = pd.read_excel(filepath, engine="openpyxl")

    filename = os.path.basename(filepath)
    course_name, session = parse_filename(filename)

    student_id_idx, submit_time_idx, question_indices = detect_question_column_indices(list(df.columns))

    meta_cols = []
    id_col_name = df.columns[student_id_idx]
    meta_cols.append(id_col_name)
    df.rename(columns={id_col_name: "学员编号"}, inplace=True)

    time_col_name = None
    if submit_time_idx is not None:
        time_col_name = df.columns[submit_time_idx]
        meta_cols.append(time_col_name)
        df.rename(columns={time_col_name: "提交时间"}, inplace=True)

    question_headers = [str(df.columns[i]) for i in question_indices]

    df["course_name"] = course_name
    df["session"] = session

    logger.info("文件 %s: %d 行, %d 个题目列", filename, len(df), len(question_headers))
    return course_name, session, df, question_headers, meta_cols


def wide_to_long(df: pd.DataFrame, question_headers: List[str]) -> pd.DataFrame:
    """将宽表问卷数据转换为长表。

    Args:
        df: 宽表 DataFrame
        question_headers: 题目列的列名列表

    Returns:
        长表 DataFrame，包含列:
        [学员编号, 提交时间, course_name, session, original_question, response_value]
    """
    id_vars = ["学员编号", "course_name", "session"]
    if "提交时间" in df.columns:
        id_vars.append("提交时间")

    existing_question_cols = [h for h in question_headers if h in df.columns]

    df_long = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=existing_question_cols,
        var_name="original_question",
        value_name="response_value",
    )

    logger.info("宽表转长表完成: %d 行 -> %d 行", len(df), len(df_long))
    return df_long


def map_questions(df_long: pd.DataFrame, mapping_df: pd.DataFrame) -> pd.DataFrame:
    """将原始题目映射为标准题目。

    匹配规则:
    1. 首先尝试精确匹配 original_question
    2. 如果未匹配，尝试模糊匹配（原始题目包含映射表中的关键词）

    Args:
        df_long: 长表 DataFrame
        mapping_df: 题目映射 DataFrame

    Returns:
        添加了 standard_question, question_type, max_score, category 列的长表
    """
    mapping_lookup = mapping_df.set_index("original_question")

    def _match_question(orig_q: str) -> Optional[Dict[str, Any]]:
        orig_q_str = str(orig_q).strip()
        if orig_q_str in mapping_lookup.index:
            row = mapping_lookup.loc[orig_q_str]
            return {
                "standard_question": row["standard_question"],
                "question_type": row["question_type"],
                "max_score": row["max_score"],
                "category": row["category"],
            }
        matched_rows = mapping_df[mapping_df["original_question"].apply(lambda k: str(k).strip() in orig_q_str or orig_q_str in str(k).strip())]
        if not matched_rows.empty:
            row = matched_rows.iloc[0]
            logger.debug("模糊匹配: '%s' -> '%s'", orig_q_str, row["original_question"])
            return {
                "standard_question": row["standard_question"],
                "question_type": row["question_type"],
                "max_score": row["max_score"],
                "category": row["category"],
            }
        return None

    results = df_long["original_question"].apply(_match_question)
    df_long["standard_question"] = results.apply(lambda r: r["standard_question"] if r else None)
    df_long["question_type"] = results.apply(lambda r: r["question_type"] if r else "unknown")
    df_long["max_score"] = results.apply(lambda r: r["max_score"] if r else pd.NA)
    df_long["category"] = results.apply(lambda r: r["category"] if r else "unknown")

    unmatched = df_long[df_long["question_type"] == "unknown"]["original_question"].unique()
    if len(unmatched) > 0:
        logger.warning("未能映射的题目: %s", unmatched.tolist())

    logger.info("题目映射完成，匹配率: %.1f%%",
                (df_long["question_type"] != "unknown").mean() * 100)
    return df_long


def detect_anomalies(df_long: pd.DataFrame) -> pd.DataFrame:
    """检测评分题目中的异常值。

    异常类型:
    - 评分缺失（response_value 为空）
    - 非数字评分（response_value 无法转为数字）
    - 超出 1 到 max_score 范围

    Args:
        df_long: 经过映射的长表

    Returns:
        anomalies_df: 仅包含异常记录的 DataFrame
    """
    rating_mask = df_long["question_type"] == "rating"
    rating_df = df_long[rating_mask].copy()

    anomalies = []

    for idx, row in rating_df.iterrows():
        val = row["response_value"]
        max_score = row["max_score"]
        reason = None

        if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
            reason = "评分缺失"
        elif not isinstance(val, (int, float)):
            try:
                numeric_val = float(str(val).strip())
                if pd.isna(max_score) or pd.isna(numeric_val):
                    reason = "无法判断"
                elif numeric_val < 1 or numeric_val > max_score:
                    reason = f"评分超出范围({numeric_val} not in [1, {max_score}])"
                else:
                    continue
            except (ValueError, TypeError):
                reason = f"非数字评分({val})"
        elif isinstance(val, (int, float)):
            if pd.isna(max_score):
                continue
            if val < 1 or val > max_score:
                reason = f"评分超出范围({val} not in [1, {int(max_score)}])"
            else:
                continue
        else:
            continue

        if reason:
            record = row.to_dict()
            record["anomaly_reason"] = reason
            anomalies.append(record)

    anomalies_df = pd.DataFrame(anomalies)
    if len(anomalies_df) > 0:
        logger.info("检测到 %d 条异常评分记录", len(anomalies_df))
    else:
        logger.info("未检测到异常评分记录")
    return anomalies_df


def get_valid_ratings(df_long: pd.DataFrame) -> pd.DataFrame:
    """获取有效的评分数据（排除异常评分）。

    Args:
        df_long: 经过映射的长表

    Returns:
        仅包含有效评分的 DataFrame
    """
    rating_mask = df_long["question_type"] == "rating"
    rating_df = df_long[rating_mask].copy()

    valid_mask = pd.Series(True, index=rating_df.index)

    for idx, row in rating_df.iterrows():
        val = row["response_value"]
        max_score = row["max_score"]

        if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
            valid_mask[idx] = False
            continue
        if not isinstance(val, (int, float)):
            try:
                numeric_val = float(str(val).strip())
            except (ValueError, TypeError):
                valid_mask[idx] = False
                continue
        else:
            numeric_val = float(val)

        if pd.isna(max_score):
            valid_mask[idx] = False
            continue
        if numeric_val < 1 or numeric_val > max_score:
            valid_mask[idx] = False

    valid = rating_df[valid_mask].copy()
    valid["numeric_value"] = pd.to_numeric(valid["response_value"], errors="coerce")
    valid = valid.dropna(subset=["numeric_value"])
    logger.info("有效评分: %d 条 / 总评分: %d 条", len(valid), len(rating_df))
    return valid


def split_rating_and_text(df_long: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """将长表数据拆分为评分数据和文本反馈数据。

    Args:
        df_long: 经过映射的长表

    Returns:
        (rating_df, text_df) 元组
    """
    rating_df = df_long[df_long["question_type"] == "rating"].copy()
    text_df = df_long[df_long["question_type"] == "text"].copy()
    logger.info("数据拆分: 评分题 %d 条, 文本题 %d 条", len(rating_df), len(text_df))
    return rating_df, text_df


def classify_questions(mapping_df: pd.DataFrame, all_question_headers: List[str]) -> pd.DataFrame:
    """基于 category 字段识别题目覆盖情况。

    类别说明:
    - common: 全局公共题（所有课程、所有期次均出现）
    - course_common: 课程公共题（同一课程的各期次均出现）
    - period_specific: 单期特有题（仅在某期次出现）
    - feedback: 开放式反馈题

    Args:
        mapping_df: 题目映射 DataFrame
        all_question_headers: 所有文件中出现的原始题目列表（去重）

    Returns:
        覆盖情况 DataFrame
    """
    unique_questions = list(set(all_question_headers))

    records = []
    for orig_q in unique_questions:
        matched = mapping_df[mapping_df["original_question"] == orig_q]
        if not matched.empty:
            row = matched.iloc[0]
            records.append({
                "original_question": orig_q,
                "standard_question": row["standard_question"],
                "question_type": row["question_type"],
                "max_score": row["max_score"],
                "category": row["category"],
            })
        else:
            records.append({
                "original_question": orig_q,
                "standard_question": None,
                "question_type": "unknown",
                "max_score": None,
                "category": "unknown",
            })

    result = pd.DataFrame(records)
    orig_common = (result["category"] == "common").sum()
    orig_course = (result["category"] == "course_common").sum()
    orig_period = (result["category"] == "period_specific").sum()
    orig_feedback = (result["category"] == "feedback").sum()
    std_common = result[result["category"] == "common"]["standard_question"].nunique()
    std_course = result[result["category"] == "course_common"]["standard_question"].nunique()
    std_period = result[result["category"] == "period_specific"]["standard_question"].nunique()
    std_feedback = result[result["category"] == "feedback"]["standard_question"].nunique()
    logger.info("题目分类完成: 原始题目 %d 个 -> 标准题目 %d 个", len(result),
                result["standard_question"].nunique())
    logger.info("  全局公共题: %d个标准题(来自%d个原始题目)", std_common, orig_common)
    logger.info("  课程公共题: %d个标准题(来自%d个原始题目)", std_course, orig_course)
    logger.info("  单期特有题: %d个标准题(来自%d个原始题目)", std_period, orig_period)
    logger.info("  反馈题: %d个标准题(来自%d个原始题目)", std_feedback, orig_feedback)
    return result


def compute_auto_coverage(df_all_long: pd.DataFrame, mapping_df: pd.DataFrame) -> pd.DataFrame:
    """基于实际上传数据计算每个 standard_question 的覆盖情况并自动判定题目类型。

    自动判定规则:
    - 覆盖全部课程全部期次: global_common
    - 某课程有>=2个期次，且题目覆盖该课程全部期次: course_common
    - 某课程只有1个期次：评分题暂判定 period_specific，标记需人工确认
    - 只覆盖部分课程期次: period_specific
    - question_type=text: feedback

    Args:
        df_all_long: 经映射后的全部长表数据
        mapping_df: 题目映射配置

    Returns:
        (auto_coverage_df, auto_category_map) 元组:
        - auto_coverage_df: 覆盖情况表
        - auto_category_map: {standard_question: auto_category} 映射字典
    """
    all_courses = sorted(df_all_long["course_name"].unique().tolist())
    all_course_sessions_full = df_all_long[["course_name", "session"]].drop_duplicates()
    all_cs_set = set(all_course_sessions_full.apply(
        lambda r: f"{r['course_name']}_{r['session']}", axis=1).tolist())
    total_courses = len(all_courses)
    total_sessions = len(all_cs_set)

    course_session_counts = df_all_long.groupby("course_name")["session"].nunique().to_dict()

    records = []
    auto_category_map = {}

    for std_q in sorted(df_all_long["standard_question"].dropna().unique()):
        subset = df_all_long[df_all_long["standard_question"] == std_q]
        q_type = subset["question_type"].iloc[0] if not subset.empty else "unknown"
        config_cat = subset["category"].iloc[0] if "category" in subset.columns else "unknown"

        covered_courses = sorted(subset["course_name"].unique().tolist())
        covered_cs = subset[["course_name", "session"]].drop_duplicates()
        covered_cs_list = sorted(covered_cs.apply(
            lambda r: f"{r['course_name']}_{r['session']}", axis=1).tolist())

        note = ""
        auto_cat = None

        if q_type == "text":
            auto_cat = "feedback"
        elif set(covered_cs_list) == all_cs_set:
            auto_cat = "global_common"
        else:
            is_course_common = True
            single_session_courses = []
            for c in covered_courses:
                c_total_sessions = course_session_counts.get(c, 0)
                c_covered = set(cs for cs in covered_cs_list if cs.startswith(f"{c}_"))
                c_all = set(f"{c}_{s}" for s in
                            sorted(df_all_long[df_all_long["course_name"] == c]["session"].unique()))
                if c_total_sessions < 2:
                    single_session_courses.append(c)
                    is_course_common = False
                elif c_covered != c_all:
                    is_course_common = False

            if is_course_common:
                auto_cat = "course_common"
            else:
                auto_cat = "period_specific"
                if single_session_courses:
                    note = f"课程[{', '.join(single_session_courses)}]仅有1个期次，无法可靠判定course_common，暂归为period_specific，建议人工确认"

        cat_normalize = {"common": "common", "global_common": "common",
                         "course_common": "course_common", "period_specific": "period_specific",
                         "feedback": "feedback", "unknown": "unknown"}
        config_normalized = cat_normalize.get(str(config_cat), str(config_cat))
        auto_normalized = cat_normalize.get(str(auto_cat), str(auto_cat))
        consistent = "是" if auto_normalized == config_normalized else "否"

        records.append({
            "standard_question": std_q,
            "question_type": q_type,
            "配置category": config_cat,
            "覆盖课程数": len(covered_courses),
            "覆盖课程列表": ", ".join(covered_courses),
            "覆盖课程期次数": len(covered_cs_list),
            "课程期次列表": ", ".join(covered_cs_list),
            "总课程数": total_courses,
            "总课程期次数": total_sessions,
            "自动分类": auto_cat,
            "配置与自动是否一致": consistent,
        })

        auto_category_map[std_q] = auto_cat

    result = pd.DataFrame(records)
    logger.info("自动覆盖分析完成: %d 个标准题目", len(result))
    logger.info("  global_common: %d, course_common: %d, period_specific: %d, feedback: %d",
                (result["自动分类"] == "global_common").sum(),
                (result["自动分类"] == "course_common").sum(),
                (result["自动分类"] == "period_specific").sum(),
                (result["自动分类"] == "feedback").sum())
    return result, auto_category_map


def apply_auto_category(df_all_long: pd.DataFrame, valid_ratings: pd.DataFrame,
                        auto_category_map: dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """将自动分类映射回数据，添加 auto_category 字段。

    Args:
        df_all_long: 全部长表数据
        valid_ratings: 有效评分数据
        auto_category_map: {standard_question: auto_category} 映射

    Returns:
        (df_all_long, valid_ratings) 均新增 auto_category 列
    """
    df_all_long = df_all_long.copy()
    df_all_long["auto_category"] = df_all_long["standard_question"].map(auto_category_map)
    df_all_long["auto_category"] = df_all_long["auto_category"].fillna("unknown")

    valid_ratings = valid_ratings.copy()
    valid_ratings["auto_category"] = valid_ratings["standard_question"].map(auto_category_map)
    valid_ratings["auto_category"] = valid_ratings["auto_category"].fillna("unknown")

    return df_all_long, valid_ratings
