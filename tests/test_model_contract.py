"""One DeepSeek response supplies both classification and sentiment fields."""

import json
from pathlib import Path
from types import SimpleNamespace

from llm import deepseek_feedback_analyzer as analyzer
from api import feedback_api


def test_one_model_call_returns_multiple_labeled_opinions(monkeypatch):
    calls = []
    response_body = {
        "feedback_id": "F1",
        "items": [
            {
                "category": "讲师表现", "subcategory": "讲解清晰",
                "sentiment": "positive", "summary": "认可讲解", "evidence": "讲解清晰",
            },
            {
                "category": "课程节奏", "subcategory": "节奏过快",
                "sentiment": "negative", "summary": "课程节奏快", "evidence": "节奏太快",
            },
        ],
    }

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(response_body, ensure_ascii=False))
        )])

    monkeypatch.setattr(
        analyzer, "OpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )),
    )
    root = Path(__file__).resolve().parents[1]
    result = analyzer.deepseek_analyze_feedback(
        feedback_id="F1",
        feedback_text="老师讲解清晰，但课程节奏太快。",
        taxonomy_path=str(root / "config/feedback_taxonomy.yaml"),
        prompt_path=str(root / "prompts/feedback_classification_prompt.md"),
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="deepseek-chat",
        use_cache=False,
    )

    assert "_error" not in result
    assert len(result["items"]) == 2
    assert [item["sentiment"] for item in result["items"]] == ["positive", "negative"]
    assert len(calls) == 1
    assert calls[0]["model"] == "deepseek-chat"


def test_feedback_api_reports_failed_and_extracted_counts(monkeypatch):
    def fake_analysis(feedback_id, feedback_text):
        if feedback_id == "2":
            return {"feedback_id": feedback_id, "items": [], "_error": "模型暂时不可用"}
        return {"feedback_id": feedback_id, "items": [{"sentiment": "positive"}]}

    monkeypatch.setattr(feedback_api, "deepseek_analyze_feedback", fake_analysis)
    result = feedback_api.feedback_analysis(
        feedback_api.FeedbackRequest(feedback_texts=["讲解清晰", "课程节奏太快"])
    )
    assert result["status"] == "partial"
    assert result["feedback_response_count"] == 2
    assert result["feedback_count"] == result["feedback_item_count"] == 1
    assert result["feedback_failed_count"] == 1


def test_prompt_and_cache_follow_taxonomy_content():
    root = Path(__file__).resolve().parents[1]
    taxonomy = analyzer.load_taxonomy(str(root / "config/feedback_taxonomy.yaml"))
    template = analyzer.load_prompt_template(str(root / "prompts/feedback_classification_prompt.md"))
    rendered = analyzer.render_classification_prompt(template, taxonomy)

    assert "{{taxonomy_categories}}" not in rendered
    assert "{{taxonomy_sentiments}}" not in rendered
    for category, labels in taxonomy["categories"].items():
        assert category in rendered
        for label in labels:
            assert label in rendered

    key = analyzer._make_cache_key("deepseek-chat", taxonomy, rendered, "节奏太快")
    changed = json.loads(json.dumps(taxonomy, ensure_ascii=False))
    changed["categories"]["课程节奏"].append("节奏忽快忽慢")
    assert key != analyzer._make_cache_key("deepseek-chat", changed, rendered, "节奏太快")
    assert key != analyzer._make_cache_key("deepseek-chat", taxonomy, rendered + "新规则", "节奏太快")


def test_empty_evidence_is_rejected():
    taxonomy = analyzer.load_taxonomy(str(Path(__file__).resolve().parents[1] / "config/feedback_taxonomy.yaml"))
    categories, subcategories, sentiments = analyzer._build_taxonomy_sets(taxonomy)
    parsed = analyzer.DeepSeekFeedbackAnalysis(
        feedback_id="F1",
        items=[{
            "category": "课程节奏", "subcategory": "节奏过快",
            "sentiment": "negative", "summary": "节奏快", "evidence": "",
        }],
    )
    errors = analyzer.validate_deepseek_analysis(
        parsed, "课程节奏太快", categories, subcategories, sentiments, "F1"
    )
    assert any("evidence 不能为空" in error for error in errors)


def test_invalid_cached_items_are_ignored(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    taxonomy = analyzer.load_taxonomy(str(root / "config/feedback_taxonomy.yaml"))
    template = analyzer.load_prompt_template(str(root / "prompts/feedback_classification_prompt.md"))
    rendered = analyzer.render_classification_prompt(template, taxonomy)
    key = analyzer._make_cache_key("deepseek-chat", taxonomy, rendered, "课程节奏太快")
    monkeypatch.setattr(analyzer, "_load_cache", lambda: {
        key: {"validated_result": {"items": [{
            "category": "课程节奏", "subcategory": "节奏过快",
            "sentiment": "negative", "summary": "节奏快", "evidence": "",
        }]}}
    })

    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "feedback_id": "F1", "items": [{
                "category": "课程节奏", "subcategory": "节奏过快",
                "sentiment": "negative", "summary": "节奏快", "evidence": "节奏太快",
            }],
        }, ensure_ascii=False)))])

    monkeypatch.setattr(analyzer, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))
    monkeypatch.setattr(analyzer, "_save_cache", lambda cache: None)
    result = analyzer.deepseek_analyze_feedback(
        feedback_id="F1", feedback_text="课程节奏太快",
        taxonomy_path=str(root / "config/feedback_taxonomy.yaml"),
        prompt_path=str(root / "prompts/feedback_classification_prompt.md"),
        api_key="test-key", base_url="https://example.invalid/v1",
        model="deepseek-chat", use_cache=True,
    )

    assert len(calls) == 1
    assert result["_cache_hit"] is False
    assert result["items"][0]["evidence"] == "节奏太快"


def test_label_sentiment_must_match_taxonomy_policy():
    root = Path(__file__).resolve().parents[1]
    taxonomy = analyzer.load_taxonomy(str(root / "config/feedback_taxonomy.yaml"))
    categories, subcategories, sentiments = analyzer._build_taxonomy_sets(taxonomy)
    rules = analyzer._build_sentiment_rules(taxonomy)
    assert rules["讲解清晰"] == {"positive"}
    assert rules["节奏过快"] == {"negative", "suggestion"}
    assert rules["希望增加完整案例"] == {"suggestion"}

    def validate(subcategory, sentiment, text):
        category = next(
            name for name, labels in taxonomy["categories"].items()
            if subcategory in labels
        )
        parsed = analyzer.DeepSeekFeedbackAnalysis(
            feedback_id="F1", items=[{
                "category": category, "subcategory": subcategory,
                "sentiment": sentiment, "summary": "反馈", "evidence": text,
            }]
        )
        return analyzer.validate_deepseek_analysis(
            parsed, text, categories, subcategories, sentiments, "F1", rules
        )

    assert any("不允许" in error for error in validate("节奏过快", "positive", "节奏太快"))
    assert any("不允许" in error for error in validate("讲解清晰", "negative", "讲解清晰"))
    assert validate("练习不足", "suggestion", "希望增加练习") == []
    assert validate("其他问题", "neutral", "课程安排在周一") == []


def test_conflicting_sentiment_is_retried_before_acceptance(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        sentiment = "positive" if len(calls) == 1 else "negative"
        body = {
            "feedback_id": "F1", "items": [{
                "category": "课程节奏", "subcategory": "节奏过快",
                "sentiment": sentiment, "summary": "节奏快", "evidence": "节奏太快",
            }],
        }
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(body, ensure_ascii=False))
        )])

    monkeypatch.setattr(analyzer, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))
    result = analyzer.deepseek_analyze_feedback(
        feedback_id="F1", feedback_text="节奏太快",
        taxonomy_path=str(root / "config/feedback_taxonomy.yaml"),
        prompt_path=str(root / "prompts/feedback_classification_prompt.md"),
        api_key="test-key", base_url="https://example.invalid/v1",
        model="deepseek-chat", use_cache=False,
    )

    assert len(calls) == 2
    assert result["_retries"] == 1
    assert result["items"][0]["sentiment"] == "negative"
