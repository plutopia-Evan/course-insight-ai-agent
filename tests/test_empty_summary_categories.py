"""Real workbook round-trips must support absent feedback categories."""

import pandas as pd
import pytest

from llm.ai_summary_generator import build_session_input, load_statistics
from scripts.ai_feedback_statistics import generate_statistics


EXAMPLES = {
    "positive": ("讲师表现", "讲解清晰"),
    "negative": ("课程节奏", "节奏过快"),
    "suggestion": ("教材与资料", "希望增加课后资料"),
    "neutral": ("其他", "其他问题"),
}


@pytest.mark.parametrize("present", [
    ["positive", "negative"], ["positive", "suggestion"],
    ["negative", "suggestion"], ["positive"], ["negative"],
    ["suggestion"], ["neutral"],
])
def test_missing_categories_survive_excel_round_trip(tmp_path, present):
    source = tmp_path / "classification.xlsx"
    target = tmp_path / "statistics.xlsx"
    rows = [{"course_name": "课程A", "session": "第01期", "respondent_id": str(i),
             "category": EXAMPLES[s][0], "subcategory": EXAMPLES[s][1], "sentiment": s}
            for i, s in enumerate(present)]
    pd.DataFrame(rows).to_excel(source, sheet_name="AI反馈分类明细", index=False)
    generate_statistics(str(source), str(target))
    overview, positive, negative, suggestions = load_statistics(str(target))
    result = build_session_input(overview.iloc[0], positive, negative, suggestions)
    assert result["classified_feedback_people"] == len(present)
    for sentiment, field, frame in [
        ("positive", "top_positive", positive), ("negative", "top_negative", negative),
        ("suggestion", "top_suggestions", suggestions),
    ]:
        assert {"course_name", "session"} <= set(frame.columns)
        assert len(result[field]) == int(sentiment in present)


def test_legacy_empty_sheet_is_supported_but_nonempty_bad_schema_is_rejected():
    row = pd.Series({"course_name": "课程A", "session": "第01期", "已分类反馈人数": 1,
                     "拆分意见总数": 1, "positive意见数": 0, "positive占比": 0,
                     "negative意见数": 0, "negative占比": 0, "suggestion意见数": 0, "suggestion占比": 0})
    empty = pd.DataFrame(columns=["暂无数据"])
    result = build_session_input(row, empty, empty, empty)
    assert result["top_positive"] == result["top_negative"] == result["top_suggestions"] == []
    with pytest.raises(ValueError, match="缺少必要列"):
        build_session_input(row, pd.DataFrame([{"unexpected": "data"}]), empty, empty)
