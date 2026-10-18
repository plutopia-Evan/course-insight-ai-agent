"""A failed run must not reuse a previous run's intermediate workbooks."""

from pathlib import Path

import pandas as pd

from scripts import ai_pipeline


def _input():
    return pd.DataFrame([{
        "课程名称": "课程A", "期次": "第1期", "学员编号": "A",
        "清洗后反馈": "课程节奏太快", "反馈类型": "有效反馈",
    }])


def _mock_classification(**kwargs):
    return {
        "feedback_id": kwargs["feedback_id"],
        "course_name": kwargs["course_name"],
        "session": kwargs["session"],
        "respondent_id": kwargs["respondent_id"],
        "items": [{
            "category": "课程", "subcategory": "节奏快", "sentiment": "negative",
            "summary": "节奏快", "evidence": "课程节奏太快",
        }],
    }


def test_statistics_failure_stops_summary_and_records_error(monkeypatch):
    monkeypatch.setattr(ai_pipeline, "deepseek_analyze_feedback", _mock_classification)
    monkeypatch.setattr(ai_pipeline.time, "sleep", lambda _: None)
    paths = []

    def fail_stats(input_path, output_path):
        paths.append((input_path, output_path))
        assert Path(input_path).is_file()
        raise ValueError("模拟统计失败")

    def forbidden_summary(**kwargs):
        raise AssertionError("统计失败后不应生成总结")

    monkeypatch.setattr(ai_pipeline, "generate_statistics", fail_stats)
    monkeypatch.setattr(ai_pipeline, "generate_summaries", forbidden_summary)

    first = ai_pipeline.run_ai_pipeline(_input(), use_cache=False)
    second = ai_pipeline.run_ai_pipeline(_input(), use_cache=False)

    assert len(paths) == 2
    assert paths[0][1] != paths[1][1]
    assert all(not Path(stats_path).exists() for _, stats_path in paths)
    for result in (first, second):
        assert result["course_overview"].empty
        assert result["course_summary"].empty
        assert result["trend_summary"].empty
        assert "模拟统计失败" in result["errors"]["错误详情"].tolist()
        assert result["api_summary"].set_index("指标").loc["备注", "数值"] == "统计失败"


def test_successful_statistics_are_passed_to_summary_in_same_run(monkeypatch):
    monkeypatch.setattr(ai_pipeline, "deepseek_analyze_feedback", _mock_classification)
    monkeypatch.setattr(ai_pipeline.time, "sleep", lambda _: None)
    seen = []

    def mock_summary(input_path, output_path, use_cache):
        stats_path = Path(input_path)
        assert stats_path.is_file()
        overview = pd.read_excel(stats_path, sheet_name="课程期次反馈概览")
        assert overview.iloc[0]["已分类反馈人数"] == 1
        seen.append((stats_path, Path(output_path)))
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            pd.DataFrame([{"课程名称": "课程A", "期次": "第1期"}]).to_excel(
                writer, sheet_name="课程AI总结", index=False)
            pd.DataFrame().to_excel(writer, sheet_name="课程AI总结明细", index=False)
            pd.DataFrame().to_excel(writer, sheet_name="跨期趋势总结", index=False)
            pd.DataFrame().to_excel(writer, sheet_name="API调用错误记录", index=False)

    monkeypatch.setattr(ai_pipeline, "generate_summaries", mock_summary)
    result = ai_pipeline.run_ai_pipeline(_input(), use_cache=False)

    assert len(result["course_overview"]) == 1
    assert len(result["course_summary"]) == 1
    assert result["errors"].empty
    assert len(seen) == 1
    assert seen[0][0].parent == seen[0][1].parent
    assert not seen[0][0].exists()


def test_empty_classification_is_counted_as_failure(monkeypatch):
    monkeypatch.setattr(ai_pipeline, "deepseek_analyze_feedback", lambda **kwargs: {"items": []})
    monkeypatch.setattr(ai_pipeline.time, "sleep", lambda _: None)

    result = ai_pipeline.run_ai_pipeline(_input(), use_cache=False)

    metrics = result["api_summary"].set_index("指标")["数值"]
    assert metrics["分类成功数"] == 0
    assert metrics["分类失败数"] == 1
    assert result["classification_detail"].empty
    assert result["course_summary"].empty
    assert "分类结果为空" in result["errors"]["错误详情"].tolist()
