"""Regression checks for the population used in ratios and cross-session wording."""

import pandas as pd

from scripts.ai_feedback_statistics import (
    _compute_course_session_overview,
    _compute_label_stats,
    _compute_sentiment_summary,
)
from llm.ai_summary_generator import (
    _cache_key,
    _compute_cross_session_trends,
    _normalize_columns,
    _session_sort_key,
    build_session_input,
)


def test_ratios_use_distinct_classified_respondents_and_show_denominator():
    detail = pd.DataFrame([
        {"course_name": "课程A", "session": "第2期", "respondent_id": "A", "category": "课程", "subcategory": "节奏快", "sentiment": "negative"},
        {"course_name": "课程A", "session": "第2期", "respondent_id": "A", "category": "课程", "subcategory": "节奏快", "sentiment": "negative"},
        {"course_name": "课程A", "session": "第2期", "respondent_id": "B", "category": "讲师", "subcategory": "讲解好", "sentiment": "positive"},
    ])
    people = {("课程A", "第2期"): 2}
    labels = _compute_label_stats(detail, people)
    negative = _compute_sentiment_summary(detail, "negative", people)
    overview = _compute_course_session_overview(detail)

    assert labels.loc[labels["subcategory"] == "节奏快", "反馈人数占比"].iloc[0] == 0.5
    assert labels["已分类反馈人数"].eq(2).all()
    assert negative.iloc[0]["反馈人数"] == 1
    assert negative.iloc[0]["反馈次数"] == 2
    assert negative.iloc[0]["人数占比"] == 0.5
    assert negative.iloc[0]["已分类反馈人数"] == 2
    assert overview.iloc[0]["已分类反馈人数"] == 2
    assert build_session_input(_normalize_columns(overview).iloc[0],
                               pd.DataFrame(columns=["course_name", "session"]),
                               pd.DataFrame(columns=["course_name", "session"]),
                               pd.DataFrame(columns=["course_name", "session"]))["classified_feedback_people"] == 2


def test_absent_latest_is_not_an_improvement_or_zero_ratio():
    sessions = [
        {"session": "第2期", "classified_feedback_people": 10, "top_negative": [
            {"subcategory": "节奏快", "ratio": 0.4},
            {"subcategory": "资料晚", "ratio": 0.2},
        ]},
        {"session": "第10期", "classified_feedback_people": 5, "top_negative": [
            {"subcategory": "节奏快", "ratio": 0.2},
            {"subcategory": "互动少", "ratio": 0.4},
        ]},
    ]
    result = _compute_cross_session_trends("课程A", sessions)

    assert "improved_problems" not in result
    assert result["not_observed_latest"] == [{
        "label": "资料晚", "last_observed_session": "第2期", "last_observed_ratio": 0.2,
    }]
    assert result["new_problems"][0]["label"] == "互动少"
    assert result["persistent_problems"][0]["trend"] == "decreased"
    assert "10人" in result["persistent_problems"][0]["evidence"]
    assert "5人" in result["persistent_problems"][0]["evidence"]
    assert sorted(["第10期", "第2期"], key=_session_sort_key) == ["第2期", "第10期"]


def test_prompt_change_invalidates_cached_summary():
    assert _cache_key("model", "{}", "old") != _cache_key("model", "{}", "new")
