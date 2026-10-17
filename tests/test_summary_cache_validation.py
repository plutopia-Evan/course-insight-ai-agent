"""Cached AI summaries must satisfy the same contract as fresh responses."""

import json
from types import SimpleNamespace

from llm import ai_summary_generator as summary


def _session_input():
    return {
        "course_name": "课程A", "session": "第2期",
        "classified_feedback_people": 5, "total_items": 5,
        "positive_count": 0, "positive_ratio": 0.0,
        "negative_count": 0, "negative_ratio": 0.0,
        "suggestion_count": 0, "suggestion_ratio": 0.0,
        "top_positive": [], "top_negative": [], "top_suggestions": [],
    }


def _valid_session_result():
    return {
        "course_name": "课程A", "session": "第2期",
        "overall_assessment": "反馈不足", "strengths": [], "problems": [],
        "recommendations": [], "management_summary": "暂无足够信息",
    }


def test_invalid_cached_session_is_recomputed(monkeypatch):
    input_data = _session_input()
    cached = _valid_session_result()
    cached["course_name"] = "另一门课"
    cached["strengths"] = [{
        "title": "虚构优点", "description": "虚构", "people": 99, "ratio": 0.99,
    }]
    cache = {summary._cache_key("model", json.dumps(input_data, ensure_ascii=False), "prompt"): cached}
    monkeypatch.setattr(summary, "_load_cache", lambda: cache)
    monkeypatch.setattr(summary, "_save_cache", lambda value: None)

    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(_valid_session_result(), ensure_ascii=False))
        )])
    monkeypatch.setattr(summary, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))

    result, meta = summary._call_llm(
        input_data, "prompt", summary.SessionSummary,
        "test-key", "https://example.invalid/v1", "model", use_cache=True,
    )
    assert len(calls) == 1
    assert meta["_cache_hit"] is False
    assert result["course_name"] == "课程A"
    assert result["strengths"] == []


def test_valid_cached_session_skips_model(monkeypatch):
    input_data = _session_input()
    cached = _valid_session_result()
    cache = {summary._cache_key("model", json.dumps(input_data, ensure_ascii=False), "prompt"): cached}
    monkeypatch.setattr(summary, "_load_cache", lambda: cache)
    monkeypatch.setattr(summary, "OpenAI", lambda **kwargs: (_ for _ in ()).throw(AssertionError("不应调用模型")))

    result, meta = summary._call_llm(
        input_data, "prompt", summary.SessionSummary,
        "test-key", "https://example.invalid/v1", "model", use_cache=True,
    )
    assert meta["_cache_hit"] is True
    assert result == cached


def test_trend_course_and_priority_sequence_are_checked():
    parsed = summary.TrendSummary(
        course_name="另一门课", trend_summary="待观察",
        next_session_priorities=[
            {"priority": 1, "action": "检查节奏", "reason": "学员提及"},
            {"priority": 1, "action": "检查资料", "reason": "学员提及"},
        ],
    )
    errors = summary._validate_summary_result(parsed, {"course_name": "课程A"})
    assert any("course_name 不一致" in error for error in errors)
    assert any("不重复" in error for error in errors)


def test_numeric_claims_preserve_units_and_exact_values():
    data = _session_input()
    data["classified_feedback_people"] = 3
    data["top_negative"] = [{"subcategory": "节奏过快", "people": 3, "ratio": 0.2}]

    assert summary._audit_text_numbers([
        ("text", "第2期有3人提到该问题，占比20%")
    ], data) == []
    for claim in ("3天能掌握", "0.2小时", "23人提到", "占比21%", "第7期出现"):
        assert summary._audit_text_numbers([("text", claim)], data), claim


def test_cross_session_narrative_numbers_are_audited():
    data = {
        "course_name": "课程A",
        "sessions": [
            {"session": "第1期", "classified_feedback_people": 10,
             "top_negative": [{"subcategory": "节奏过快", "people": 4, "ratio": 0.4}]},
            {"session": "第2期", "classified_feedback_people": 5,
             "top_negative": [{"subcategory": "节奏过快", "people": 1, "ratio": 0.2}]},
        ],
        "computed_trends": {"persistent_problems": [{
            "label": "节奏过快", "trend": "decreased",
        }]},
    }
    valid = summary.TrendSummary(
        course_name="课程A", trend_summary="从第1期的40%降至第2期的20%",
        next_session_priorities=[],
    )
    invalid = summary.TrendSummary(
        course_name="课程A", trend_summary="预计3天解决",
        next_session_priorities=[],
    )
    assert summary._validate_summary_result(valid, data) == []
    assert any("3天" in error for error in summary._validate_summary_result(invalid, data))
