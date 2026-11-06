from pathlib import Path
from io import BytesIO
import pandas as pd
from fastapi.testclient import TestClient

from api.main_api import app
from core.batch_service import run_batch_analysis
from core.examples import sample_uploads


def test_operator_service_and_batch_api_use_same_report(monkeypatch, tmp_path):
    samples = sample_uploads()
    mapping = Path("config/question_mapping.xlsx").read_bytes()
    output_dir = tmp_path / "ui"
    output_dir.mkdir()
    direct = run_batch_analysis([(f.name, f.data) for f in samples], ("question_mapping.xlsx", mapping), str(output_dir))
    assert direct["total_course_sessions"] == 2
    assert direct["ai_results"] is None
    monkeypatch.setenv("SERVICE_API_KEY", "batch-test")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    with TestClient(app, headers={"Authorization": "Bearer batch-test"}) as client:
        response = client.post("/analysis/batch", files=[("files", (f.name, f.data)) for f in samples])
        assert response.status_code == 200
        result = response.json()
        assert result["profile"] == "batch_statistics"
        assert result["course_session_count"] == 2
        download = client.get(result["download_url"])
        ui = pd.read_excel(BytesIO(direct["complete_xlsx_bytes"]), sheet_name="期次评分统计")
        api = pd.read_excel(BytesIO(download.content), sheet_name="期次评分统计")
        pd.testing.assert_frame_equal(ui, api)
        assert client.get(result["result_url"]).json() == result


def test_unknown_question_only_is_reviewable(tmp_path):
    stream = BytesIO()
    pd.DataFrame({"学员编号": ["one"], "从未配置过的题": ["意见"]}).to_excel(stream, index=False)
    result = run_batch_analysis([("课程_第01期.xlsx", stream.getvalue())],
                                ("question_mapping.xlsx", Path("config/question_mapping.xlsx").read_bytes()), str(tmp_path))
    assert result["analysis_status"] == "partial"
    assert not result["pending_review"].empty


def test_batch_ai_rejects_budget_before_any_model_call(monkeypatch, tmp_path):
    from core import batch_service
    from core.input_validation import SurveyInputError
    import pytest
    stream = BytesIO()
    pd.DataFrame({"学员编号": [str(i) for i in range(101)], "课程反馈": ["讲师讲解清晰"] * 101}).to_excel(stream, index=False)
    monkeypatch.setattr(batch_service, "run_ai_pipeline", lambda *_: pytest.fail("must reject before model calls"))
    with pytest.raises(SurveyInputError, match="100"):
        run_batch_analysis([("课程_第01期.xlsx", stream.getvalue())],
                           ("question_mapping.xlsx", Path("config/question_mapping.xlsx").read_bytes()), str(tmp_path), enable_ai=True)


def test_invalid_mapping_returns_actionable_input_error(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "batch-test")
    sample = sample_uploads()[0]
    with TestClient(app, headers={"Authorization": "Bearer batch-test"}) as client:
        response = client.post("/analysis/batch", files=[
            ("files", (sample.name, sample.data)), ("mapping", ("mapping.xlsx", b"not a workbook")),
        ])
        assert response.status_code == 422
        assert "映射表" in response.json()["detail"]
