"""A follow-up result/report request reuses the original analysis and status."""

import shutil
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agent.orchestrator import CourseInsightAgent
from api import analysis_runner
from api.main_api import app
from llm.ai_feedback_analyzer import mock_analyze_feedback


def prepare_client(monkeypatch, tmp_path, fail_second=False):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "config", tmp_path / "config")
    mapping = pd.read_excel(tmp_path / "config/question_mapping.xlsx")
    rating = mapping.loc[mapping.question_type == "rating", "original_question"].iloc[0]
    text = mapping.loc[mapping.question_type == "text", "original_question"].iloc[0]
    workbook = BytesIO()
    pd.DataFrame({
        "学员编号": ["S1", "S2", "S3"],
        rating: [5, 4, 9],
        text: ["老师讲解清晰", "课程节奏太快", "无"],
    }).to_excel(workbook, index=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("SERVICE_API_KEY", "test-token")
    calls = []

    def classify(**kwargs):
        calls.append(kwargs["feedback_text"])
        if fail_second and "太快" in kwargs["feedback_text"]:
            return {"items": [], "_error": "model unavailable"}
        return mock_analyze_feedback(**kwargs)

    monkeypatch.setattr(
        analysis_runner, "CourseInsightAgent",
        lambda: CourseInsightAgent(feedback_analyzer=classify),
    )
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    return client, workbook.getvalue(), calls


@pytest.mark.parametrize("endpoint", ["/analysis", "/generate_report", "/dify/analyze"])
@pytest.mark.parametrize("fail_second", [False, True])
def test_uploaded_analysis_is_reused_over_http(monkeypatch, tmp_path, endpoint, fail_second):
    client, workbook, calls = prepare_client(monkeypatch, tmp_path, fail_second)
    with client:
        response = client.post(endpoint, files={"file": ("课程_第01期.xlsx", workbook)})
        assert response.status_code == 200
        original = response.json()
        assert len(calls) == 2
        assert original["status"] == ("partial" if fail_second else "complete")
        assert original["feedback_failed_count"] == int(fail_second)

        # Follow-up operations must work using saved files alone.
        def must_not_analyze(*args, **kwargs):
            pytest.fail("A read-only follow-up reran the analysis")

        monkeypatch.setattr(analysis_runner, "_analyze_path", must_not_analyze)
        stored = client.get(original["result_url"])
        report = client.post("/generate_report", data={"analysis_id": original["analysis_id"]})
        assert stored.status_code == report.status_code == 200
        assert stored.json() == report.json()
        for field in ("analysis_id", "status", "download_url", "feedback_errors", "feedback_results"):
            assert stored.json()[field] == original[field]
        download = client.get(original["download_url"])
        assert download.status_code == 200
        overview = pd.read_excel(BytesIO(download.content), sheet_name="数据总览").iloc[0]
        assert overview["feedback_failed_count"] == int(fail_second)
        assert len(calls) == 2
        assert len(list((tmp_path / "reports").glob("*.xlsx"))) == 1
        assert len(list((tmp_path / "reports/analyses").glob("*.json"))) == 1


def test_report_rejects_ambiguous_or_missing_input_before_analysis(monkeypatch, tmp_path):
    client, workbook, calls = prepare_client(monkeypatch, tmp_path)
    with client:
        assert client.post("/generate_report").status_code == 422
        response = client.post(
            "/generate_report", data={"analysis_id": "a" * 32},
            files={"file": ("课程_第01期.xlsx", workbook)},
        )
        assert response.status_code == 422
        assert calls == []


@pytest.mark.parametrize("analysis_id", ["../outside", "bad-id", "a" * 32])
def test_unknown_or_unsafe_result_is_not_reanalyzed(monkeypatch, tmp_path, analysis_id):
    client, _, calls = prepare_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/generate_report", data={"analysis_id": analysis_id})
        assert response.status_code == 404
        assert calls == []


@pytest.mark.parametrize("broken", ["report", "record"])
def test_missing_or_corrupt_saved_artifact_returns_404(monkeypatch, tmp_path, broken):
    client, workbook, calls = prepare_client(monkeypatch, tmp_path)
    with client:
        result = client.post("/analysis", files={"file": ("课程_第01期.xlsx", workbook)}).json()
        if broken == "report":
            report = tmp_path / "reports" / result["download_url"].split("/")[-1]
            report.unlink()
        else:
            record = tmp_path / "reports/analyses" / f"{result['analysis_id']}.json"
            record.write_text("{broken", encoding="utf-8")
        assert client.get(result["result_url"]).status_code == 404
        assert len(calls) == 2


def test_saved_results_require_service_authentication(monkeypatch, tmp_path):
    client, _, calls = prepare_client(monkeypatch, tmp_path)
    with client:
        client.headers.pop("Authorization")
        assert client.get("/analyses/" + "a" * 32).status_code == 401
        assert client.post("/generate_report", data={"analysis_id": "a" * 32}).status_code == 401
        assert calls == []
