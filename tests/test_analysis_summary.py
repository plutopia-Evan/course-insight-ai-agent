"""The main analysis and exported workbook must agree on their counts."""

from pathlib import Path
import shutil

import pandas as pd

from agent.orchestrator import CourseInsightAgent
from llm.ai_feedback_analyzer import mock_analyze_feedback
from llm.deepseek_feedback_analyzer import deepseek_analyze_feedback


def test_analysis_counts_match_report(tmp_path, monkeypatch):
    source_mapping = Path(__file__).resolve().parents[1] / "config/question_mapping.xlsx"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copyfile(source_mapping, config_dir / "question_mapping.xlsx")
    shutil.copyfile(
        source_mapping.parent / "feedback_taxonomy.yaml",
        config_dir / "feedback_taxonomy.yaml",
    )

    mapping = pd.read_excel(source_mapping)
    rating_question = mapping.loc[mapping.question_type == "rating", "original_question"].iloc[0]
    text_question = mapping.loc[mapping.question_type == "text", "original_question"].iloc[0]
    survey = pd.DataFrame({
        "学员编号": ["S1", "S2"],
        rating_question: [5, 9],
        text_question: ["讲解清晰", "节奏太快"],
    })
    survey_path = tmp_path / "demo_第01期.xlsx"
    survey.to_excel(survey_path, index=False)

    monkeypatch.chdir(tmp_path)
    assert CourseInsightAgent().feedback_agent.analyze_feedback is deepseek_analyze_feedback
    result = CourseInsightAgent(feedback_analyzer=mock_analyze_feedback).run(str(survey_path))
    summary = result["summary"]

    assert summary == {
        "analysis_status": "complete",
        "student_count": 2,
        "rating_total": 2,
        "valid_rating_count": 1,
        "feedback_response_count": 2,
        "feedback_item_count": 2,
        "feedback_count": 2,
        "feedback_analyzed_count": 2,
        "feedback_failed_count": 0,
        "feedback_skipped_count": 0,
        "anomaly_count": 1,
    }
    assert all(result[key] == value for key, value in summary.items())

    report = pd.ExcelFile(result["report_path"])
    assert set(report.sheet_names) == {
        "数据总览", "标准化长表", "期次评分统计", "开放式反馈明细", "异常数据"
    }
    report_summary = pd.read_excel(report, sheet_name="数据总览").iloc[0]
    assert all(report_summary[key] == value for key, value in summary.items())
    assert len(pd.read_excel(report, sheet_name="开放式反馈明细")) == 2


def test_model_failure_is_visible_in_report(tmp_path, monkeypatch):
    source_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copyfile(source_config / "question_mapping.xlsx", config_dir / "question_mapping.xlsx")

    mapping = pd.read_excel(source_config / "question_mapping.xlsx")
    text_question = mapping.loc[mapping.question_type == "text", "original_question"].iloc[0]
    survey_path = tmp_path / "demo_第01期.xlsx"
    pd.DataFrame({
        "学员编号": ["S1", "S2", "S3"],
        text_question: ["老师讲解清晰", "无", "课程节奏太快"],
    }).to_excel(survey_path, index=False)

    calls = []

    def fake_analyzer(**kwargs):
        calls.append(kwargs["feedback_text"])
        if "节奏" in kwargs["feedback_text"]:
            return {"items": [], "_error": "模型暂时不可用"}
        return {"items": [{
            "category": "讲师表现", "subcategory": "讲解清晰",
            "sentiment": "positive", "summary": "认可讲解", "evidence": "讲解清晰",
        }]}

    monkeypatch.chdir(tmp_path)
    result = CourseInsightAgent(feedback_analyzer=fake_analyzer).run(str(survey_path))
    assert len(calls) == 2  # The low-information response was skipped.
    assert result["analysis_status"] == "partial"
    assert result["feedback_analyzed_count"] == 1
    assert result["feedback_failed_count"] == 1
    assert result["feedback_skipped_count"] == 1
    assert result["feedback_count"] == 1
    assert result["feedback_errors"][0]["feedback_text"] == "课程节奏太快"

    report = pd.ExcelFile(result["report_path"])
    assert "AI分析错误" in report.sheet_names
    assert len(pd.read_excel(report, sheet_name="AI分析错误")) == 1
