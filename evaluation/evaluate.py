"""Score opinion extraction independently of labels using evidence spans."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate example IDs")
    return rows


def span(item, text):
    evidence = item.get("evidence", "")
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    start = item.get("evidence_start", text.find(evidence))
    if not isinstance(start, int) or start < 0 or text[start:start + len(evidence)] != evidence:
        return None
    return start, start + len(evidence)


def overlap(a, b):
    if a is None or b is None:
        return 0.0
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    return intersection / (max(a[1], b[1]) - min(a[0], b[0]))


def match_opinions(expected, predicted, text, threshold=0.5):
    """Maximum-cardinality one-to-one matching, not repeated greedy credit."""
    edges = {}
    for index, item in enumerate(expected):
        candidates = [(overlap(span(item, text), span(other, text)), j) for j, other in enumerate(predicted)]
        edges[index] = [j for score, j in sorted(candidates, reverse=True) if score >= threshold]
    assigned = {}

    def augment(index, seen):
        for candidate in edges[index]:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate not in assigned or augment(assigned[candidate], seen):
                assigned[candidate] = index
                return True
        return False

    for index in edges:
        augment(index, set())
    return [(gold, prediction) for prediction, gold in assigned.items()]


def scores(correct, predicted, expected):
    precision = correct / predicted if predicted else 0.0
    recall = correct / expected if expected else 0.0
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "correct": correct, "predicted": predicted, "expected": expected}


def evaluate(gold_rows, prediction_rows, threshold=0.5):
    if not 0 < threshold <= 1 or not gold_rows:
        raise ValueError("Need a nonempty dataset and 0 < overlap threshold <= 1")
    gold = {row["id"]: row for row in gold_rows}
    predictions = {row["id"]: row for row in prediction_rows}
    if len(gold) != len(gold_rows) or len(predictions) != len(prediction_rows):
        raise ValueError("Duplicate example IDs")
    if predictions.keys() - gold.keys():
        raise ValueError("Predictions contain IDs absent from the gold dataset")
    counters = {name: [Counter(), Counter(), Counter()] for name in ("category", "label", "sentiment")}
    expected_total = predicted_total = matched_total = valid_evidence = failed = 0
    bad_cases = []
    for key, row in gold.items():
        text, expected = row["text"], row["items"]
        if row.get("source") not in {"synthetic", "real"}:
            raise ValueError("Each gold row must declare source=synthetic or real")
        if any(span(item, text) is None for item in expected):
            raise ValueError(f"Gold evidence must be a literal source span: {key}")
        prediction = predictions.get(key, {"error": "missing prediction"})
        error = prediction.get("error") or prediction.get("_error")
        predicted = prediction.get("items", [])
        if not isinstance(predicted, list) or any(not isinstance(item, dict) for item in predicted):
            predicted, error = [], "invalid prediction structure"
        # A failed result is not silently removed from the recall denominator.
        if error:
            predicted = []
            failed += 1
        pairs = match_opinions(expected, predicted, text, threshold)
        expected_total += len(expected)
        predicted_total += len(predicted)
        matched_total += len(pairs)
        valid_evidence += sum(span(item, text) is not None for item in predicted)

        def value(item, metric):
            if metric == "label":
                return str(item.get("category", "")) + "/" + str(item.get("subcategory", ""))
            return str(item.get(metric, ""))

        incorrect = []
        for metric, (truth, guesses, correct) in counters.items():
            truth.update(value(item, metric) for item in expected)
            guesses.update(value(item, metric) for item in predicted)
            for left, right in pairs:
                label = value(expected[left], metric)
                if label == value(predicted[right], metric):
                    correct[label] += 1
                else:
                    incorrect.append({"metric": metric, "expected": label, "predicted": value(predicted[right], metric)})
        if error or incorrect or len(pairs) != len(expected) or len(pairs) != len(predicted):
            bad_cases.append({"id": key, "error": error, "missing_opinions": len(expected) - len(pairs),
                              "extra_opinions": len(predicted) - len(pairs), "label_errors": incorrect})
    metrics = {}
    for name, (truth, guesses, correct) in counters.items():
        labels = truth.keys() | guesses.keys()
        per_label = {label: scores(correct[label], guesses[label], truth[label]) for label in sorted(labels)}
        metrics[name] = {"micro": scores(sum(correct.values()), predicted_total, expected_total),
                         "macro_f1": sum(v["f1"] for v in per_label.values()) / len(labels) if labels else 0.0,
                         "per_label": per_label}
    sources = sorted({row["source"] for row in gold_rows})
    return {
        "dataset_sources": sources,
        "scope": "synthetic_demo_only" if sources == ["synthetic"] else "declared_real_or_mixed_requires_annotation_review",
        "sample_count": len(gold), "failed_count": failed, "failure_rate": failed / len(gold),
        "evidence_overlap_threshold": threshold,
        "opinion_extraction": scores(matched_total, predicted_total, expected_total),
        "literal_evidence_rate": valid_evidence / predicted_total if predicted_total else 0.0,
        "classification": metrics, "bad_cases": bad_cases,
        "limitations": ["Evidence overlap is a matching heuristic, not proof of semantic support.",
                        "Human review of evidence, summaries and recommendations is still required.",
                        "Synthetic examples do not measure real-world model accuracy."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(read_jsonl(args.gold), read_jsonl(args.predictions))
    result["gold_sha256"] = hashlib.sha256(Path(args.gold).read_bytes()).hexdigest()
    result["predictions_sha256"] = hashlib.sha256(Path(args.predictions).read_bytes()).hexdigest()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["scope"], "samples:", result["sample_count"], "report:", path)


if __name__ == "__main__":
    main()
