"""Upload paths stay isolated and the Dify response uses the analysis summary."""

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from api import dify_api
from api.upload_storage import saved_upload


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


def test_dify_endpoint_returns_summary_without_name_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    uploaded_paths = []

    class FakeAgent:
        def run(self, file_path):
            from pathlib import Path

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

    monkeypatch.setattr(dify_api, "CourseInsightAgent", FakeAgent)
    upload = MemoryUpload(file=BytesIO(b"survey"), filename="课程_第01期.xlsx")
    result = run_in_memory_upload(dify_api.dify_analyze(upload))

    assert result["status"] == "partial"
    assert result["success"] is False
    assert result["feedback_failed_count"] == 1
    assert result["feedback_item_count"] == 3
    assert not uploaded_paths[0].exists()
