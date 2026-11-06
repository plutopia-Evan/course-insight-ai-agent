"""Explicit input contracts: ambiguous mappings never silently choose a row."""

import pandas as pd


class SurveyInputError(ValueError):
    pass


def validate_mapping(df):
    required = {"original_question", "standard_question", "question_type", "max_score", "category"}
    missing = required - set(df.columns)
    if missing:
        raise SurveyInputError(f"题目映射表缺少列：{sorted(missing)}")
    if df.empty:
        raise SurveyInputError("题目映射表为空")
    df = df.copy()
    for name in required - {"max_score"}:
        if df[name].isna().any() or df[name].astype(str).str.strip().eq("").any():
            raise SurveyInputError(f"映射表 {name} 不能为空")
        df[name] = df[name].astype(str).str.strip()
    if df.original_question.duplicated().any():
        raise SurveyInputError("映射表存在重复的原始题目，请合并或修正后上传")
    if not df.question_type.isin(["rating", "text"]).all():
        raise SurveyInputError("question_type 只能是 rating 或 text")
    if not df.category.isin(["common", "global_common", "course_common", "period_specific", "feedback"]).all():
        raise SurveyInputError("映射表 category 不在支持的分类范围内")
    numbers = pd.to_numeric(df.max_score, errors="coerce")
    ratings = df.question_type.eq("rating")
    if (numbers[ratings].isna() | numbers[ratings].le(0) | numbers[ratings].mod(1).ne(0)).any():
        raise SurveyInputError("评分题 max_score 必须是正整数")
    df["max_score"] = numbers.where(ratings).astype("Int64")
    return df


def detect_metadata_columns(headers):
    labels = [str(value).strip().lower() for value in headers]
    ids = {"学员编号", "学员id", "学号", "学生编号", "respondent_id", "id"}
    times = {"提交时间", "提交日期", "填写时间", "答卷时间", "时间戳", "submit_time", "timestamp"}
    id_indices = [i for i, label in enumerate(labels) if label in ids]
    if not id_indices:
        id_indices = [i for i, label in enumerate(labels) if label.endswith("编号")]
    if len(id_indices) != 1:
        raise SurveyInputError("请提供唯一的学员编号列；不会自动把第一列当作学员编号")
    time_indices = [i for i, label in enumerate(labels) if label in times]
    if len(time_indices) > 1:
        raise SurveyInputError("存在多个提交时间列，请确认唯一的提交时间")
    time_index = time_indices[0] if time_indices else None
    questions = [i for i in range(len(headers)) if i not in {id_indices[0], time_index}]
    if not questions:
        raise SurveyInputError("问卷没有评分或反馈题目")
    return id_indices[0], time_index, questions


def match_question(question, mapping):
    question = str(question).strip()
    exact = mapping[mapping.original_question.eq(question)]
    candidates = exact if not exact.empty else mapping[
        mapping.original_question.map(lambda key: bool(question) and (key in question or question in key))
    ]
    if candidates.empty:
        return {"standard_question": None, "question_type": "unknown", "max_score": pd.NA,
                "category": "unknown", "mapping_status": "unmapped", "mapping_candidates": ""}
    choices = candidates[["standard_question", "question_type", "max_score", "category"]].drop_duplicates()
    if len(choices) > 1:
        return {"standard_question": None, "question_type": "unknown", "max_score": pd.NA,
                "category": "unknown", "mapping_status": "ambiguous",
                "mapping_candidates": " | ".join(candidates.standard_question.unique())}
    return {**choices.iloc[0].to_dict(), "mapping_status": "exact" if not exact.empty else "contains",
            "mapping_candidates": ""}
