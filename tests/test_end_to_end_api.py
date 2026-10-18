"""Acceptance test for upload, analysis, API summaries, and report download."""

import json
import shutil
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import UploadFile

from agent.orchestrator import CourseInsightAgent
from api import analysis_api, analysis_runner, dify_api, report_api
from llm.ai_feedback_analyzer import mock_analyze_feedback


class MemoryUpload(UploadFile):
    async def read(self, size=-1):
        return self.file.read(size)

    async def close(self):
        self.file.close()


def run_without_network(coroutine):
    """Run in-memory upload coroutines without opening local sockets."""
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    raise AssertionError("The in-memory request unexpectedly suspended")


def test_survey_upload_analysis_and_download(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copyfile(root / "config/question_mapping.xlsx", config_dir / "question_mapping.xlsx")
    shutil.copyfile(root / "config/feedback_taxonomy.yaml", config_dir / "feedback_taxonomy.yaml")

    mapping = pd.read_excel(config_dir / "question_mapping.xlsx")
    rating_question = mapping.loc[mapping.question_type == "rating", "original_question"].iloc[0]
    text_question = mapping.loc[mapping.question_type == "text", "original_question"].iloc[0]
    survey = pd.DataFrame({
        "学员编号": ["S1", "S2", "S3"],
        rating_question: [5, 4, 9],
        text_question: ["老师讲解清晰", "课程节奏太快", "无"],
    })
    workbook = BytesIO()
    survey.to_excel(workbook, index=False)
    file_bytes = workbook.getvalue()
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        analysis_runner,
        "CourseInsightAgent",
        lambda: CourseInsightAgent(feedback_analyzer=mock_analyze_feedback),
    )

    async def immediate_threadpool(function, *args):
        return function(*args)

    monkeypatch.setattr(analysis_runner, "run_in_threadpool", immediate_threadpool)

    def upload():
        return MemoryUpload(file=BytesIO(file_bytes), filename="验收课程_第01期.xlsx")

    analysis_response = run_without_network(analysis_api.analysis(upload()))
    analysis = json.loads(analysis_response.body)
    report = run_without_network(report_api.generate_report(upload()))
    dify = run_without_network(dify_api.dify_analyze(upload()))

    expected = {
        "status": "complete",
        "student_count": 3,
        "rating_total": 3,
        "valid_rating_count": 2,
        "feedback_response_count": 3,
        "feedback_item_count": 2,
        "feedback_failed_count": 0,
        "anomaly_count": 1,
    }
    for key, value in expected.items():
        assert analysis[key] == report[key] == dify[key] == value
    assert analysis["feedback_skipped_count"] == 1
    assert [item["items"][0]["sentiment"] for item in analysis["feedback_results"]] == [
        "positive", "negative"
    ]

    analysis_filename = analysis["download_url"].removeprefix("/download/")
    report_filename = report["download_url"].removeprefix("/download/")
    assert analysis_filename != report_filename
    downloaded = report_api.download_file(analysis_filename)
    report_path = Path(downloaded.path)
    assert report_path.is_file()
    overview = pd.read_excel(report_path, sheet_name="数据总览").iloc[0]
    assert overview["student_count"] == 3
    assert overview["feedback_item_count"] == 2
    assert len(pd.read_excel(report_path, sheet_name="开放式反馈明细")) == 2
    assert len(pd.read_excel(report_path, sheet_name="异常数据")) == 1
    assert Path(dify["report_path"]).is_file()
    assert list((tmp_path / "data/upload").iterdir()) == []
