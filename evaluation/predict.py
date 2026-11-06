"""Explicit opt-in runner for paid model evaluation, never used in CI."""

import argparse
import json
from pathlib import Path

from evaluation.evaluate import read_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-api", action="store_true", help="Authorize actual model calls for this run")
    args = parser.parse_args()
    if not args.allow_api:
        parser.error("Real model calls require --allow-api; use saved predictions for offline evaluation")
    from llm.deepseek_feedback_analyzer import deepseek_analyze_feedback
    rows = read_jsonl(args.dataset)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for row in rows:
            result = deepseek_analyze_feedback(feedback_id=row["id"], feedback_text=row["text"], use_cache=False)
            stream.write(json.dumps({"id": row["id"], "items": result.get("items", []),
                                     "error": result.get("_error"), "cache_enabled": False}, ensure_ascii=False) + "\n")
            stream.flush()


if __name__ == "__main__":
    main()
