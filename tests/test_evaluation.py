import pytest

from evaluation.evaluate import evaluate, read_jsonl


def example():
    return {"id": "one", "source": "synthetic", "text": "讲解清晰，但节奏过快", "items": [
        {"category": "讲师", "subcategory": "清晰", "sentiment": "positive", "evidence": "讲解清晰"},
        {"category": "节奏", "subcategory": "快", "sentiment": "negative", "evidence": "节奏过快"},
    ]}


def test_missing_prediction_counts_in_recall():
    result = evaluate([example()], [])
    assert result["opinion_extraction"]["recall"] == 0
    assert result["failed_count"] == 1


def test_duplicate_opinion_does_not_earn_extra_credit():
    row = example()
    result = evaluate([row], [{"id": "one", "items": [row["items"][0]] * 2}])
    assert result["opinion_extraction"]["precision"] == 0.5
    assert result["opinion_extraction"]["recall"] == 0.5


def test_literal_evidence_does_not_imply_correct_classification():
    row = example()
    items = [{**item, "sentiment": "neutral"} for item in row["items"]]
    result = evaluate([row], [{"id": "one", "items": items}])
    assert result["literal_evidence_rate"] == 1
    assert result["classification"]["sentiment"]["micro"]["f1"] == 0
    assert result["scope"] == "synthetic_demo_only"


def test_duplicate_and_unknown_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate([example(), example()], [])
    with pytest.raises(ValueError, match="absent"):
        evaluate([example()], [{"id": "other", "items": []}])


def test_gold_evidence_must_exist():
    row = example()
    row["items"][0]["evidence"] = "不存在"
    with pytest.raises(ValueError, match="Gold evidence"):
        evaluate([row], [])
