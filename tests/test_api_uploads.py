"""Upload paths stay isolated and the Dify response uses the analysis summary."""

import json
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
import pandas as pd

from api import analysis_api, analysis_runner, dify_api, report_api
from api import upload_storage
from api.feedback_api import FeedbackRequest
from api.upload_storage import saved_upload
from agent.feedback_agent import FeedbackAgent, FeedbackLimitExceeded


class MemoryUpload(UploadFile):
    async def read(self, size=-1):
        return self.file.read(size)

    async def close(self):
        self.file.close()


def run_in_memory_upload(coroutine):
    """Drive an in-memory upload, whose async methods do not suspend."""
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    raise AssertionError("The in-memory upload unexpectedly suspended")


def test_upload_is_removed_after_analysis(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    async def check():
        first = MemoryUpload(file=BytesIO(b"first"), filename="课程_第01期.xlsx")
        second = MemoryUpload(file=BytesIO(b"second"), filename="课程_第01期.xlsx")
        async with saved_upload(first) as first_path:
            async with saved_upload(second) as second_path:
                assert first_path != second_path
                assert first_path.read_bytes() == b"first"
                assert second_path.read_bytes() == b"second"
            assert not second_path.exists()
        assert not first_path.exists()

    run_in_memory_upload(check())


def test_upload_is_cleaned_up_when_read_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    class BrokenUpload(MemoryUpload):
        async def read(self, size=-1):
            raise OSError("upload interrupted")

    async def check():
        file = BrokenUpload(file=BytesIO(b"data"), filename="survey.xlsx")
        with pytest.raises(OSError, match="upload interrupted"):
            async with saved_upload(file):
                pass
        assert file.file.closed
        assert list((tmp_path / "data/upload").iterdir()) == []

    run_in_memory_upload(check())


@pytest.mark.parametrize("filename", ["../escape.xlsx", "..\\escape.xlsx", "C:escape.xlsx", "bad.csv"])
def test_upload_rejects_unsafe_filename(monkeypatch, tmp_path, filename):
    monkeypatch.chdir(tmp_path)

    async def check():
        file = MemoryUpload(file=BytesIO(b"data"), filename=filename)
        with pytest.raises(HTTPException) as error:
            async with saved_upload(file):
                pass
        assert error.value.status_code == 400

    run_in_memory_upload(check())


def test_upload_rejects_oversized_file_and_removes_temporary_copy(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upload_storage, "MAX_UPLOAD_BYTES", 4)

    async def check():
        file = MemoryUpload(file=BytesIO(b"12345"), filename="survey.xlsx")
        with pytest.raises(HTTPException) as error:
            async with saved_upload(file):
                pass
        assert error.value.status_code == 413
        assert file.file.closed
        assert list((tmp_path / "data/upload").iterdir()) == []

    run_in_memory_upload(check())


@pytest.mark.parametrize(
    ("texts", "max_count", "max_chars"),
    [
        (["老师讲解清晰"] * 101, 100, 2000),
        (["老师讲解清晰" + "好" * 2000], 100, 2000),
    ],
)
def test_survey_feedback_limit_prevents_any_model_calls(texts, max_count, max_chars):
    calls = []
    agent = FeedbackAgent(analyze_feedback=lambda **kwargs: calls.append(kwargs))
    survey = {
        "df_long": pd.DataFrame({
            "question_type": ["text"] * len(texts),
            "response_value": texts,
            "学员编号": [str(i) for i in range(len(texts))],
        })
    }

    with pytest.raises(FeedbackLimitExceeded):
        agent.run(
            survey,
            max_feedback_count=max_count,
            max_feedback_chars=max_chars,
        )
    assert calls == []


@pytest.mark.parametrize(
    "texts",
    [["反馈"] * 101, ["课" * 2001]],
)
def test_direct_feedback_request_rejects_oversized_input(texts):
    with pytest.raises(ValidationError):
        FeedbackRequest(feedback_texts=texts)


def test_dify_endpoint_returns_summary_without_name_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    uploaded_paths = []
    threadpool_calls = []

    class FakeAgent:
        def run(self, file_path, **limits):
            from pathlib import Path

            assert limits == {"max_feedback_count": 100, "max_feedback_chars": 2000}
            path = Path(file_path)
            assert path.read_bytes() == b"survey"
            uploaded_paths.append(path)
            return {
                "summary": {
                    "analysis_status": "partial",
                    "feedback_failed_count": 1,
                    "feedback_response_count": 2,
                    "feedback_item_count": 3,
                    "anomaly_count": 0,
                    "student_count": 2,
                    "rating_total": 4,
                    "valid_rating_count": 4,
                },
                "feedback_errors": [{"reason": "model unavailable"}],
                "feedback_results": [],
                "course_name": "课程",
                "session": "第01期",
                "report_path": "data/output/report.xlsx",
            }

    async def fake_threadpool(function, *args):
        threadpool_calls.append((function, args))
        return function(*args)

    monkeypatch.setattr(analysis_runner, "CourseInsightAgent", FakeAgent)
    monkeypatch.setattr(analysis_runner, "run_in_threadpool", fake_threadpool)
    upload = MemoryUpload(file=BytesIO(b"survey"), filename="课程_第01期.xlsx")
    result = run_in_memory_upload(dify_api.dify_analyze(upload))

    assert result["status"] == "partial"
    assert result["success"] is False
    assert result["feedback_failed_count"] == 1
    assert result["feedback_item_count"] == 3
    assert len(threadpool_calls) == 1
    assert not uploaded_paths[0].exists()


def test_analysis_and_report_endpoints_use_shared_runner(monkeypatch):
    calls = []
    summary = {
        "analysis_status": "complete",
        "feedback_analyzed_count": 1,
        "feedback_failed_count": 0,
        "feedback_skipped_count": 0,
        "feedback_response_count": 1,
        "feedback_item_count": 1,
        "feedback_count": 1,
        "anomaly_count": 0,
    }
    result = {
        **summary,
        "summary": summary,
        "course_name": "课程",
        "session": "第01期",
        "feedback_errors": [],
        "feedback_results": [],
        "report_path": "data/output/report.xlsx",
    }

    async def fake_runner(file):
        calls.append(file.filename)
        return result

    monkeypatch.setattr(analysis_api, "analyze_upload", fake_runner)
    monkeypatch.setattr(report_api, "analyze_upload", fake_runner)
    upload = MemoryUpload(file=BytesIO(b"survey"), filename="survey.xlsx")

    analysis_response = run_in_memory_upload(analysis_api.analysis(upload))
    report_response = run_in_memory_upload(report_api.generate_report(upload))

    assert calls == ["survey.xlsx", "survey.xlsx"]
    assert json.loads(analysis_response.body)["download_url"] == "/download/report.xlsx"
    assert report_response["download_url"] == "/download/report.xlsx"
