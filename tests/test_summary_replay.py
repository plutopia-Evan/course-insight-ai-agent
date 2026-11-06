import sys
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main_api import app
from llm import ai_summary_generator as generator
from llm import deepseek_feedback_analyzer as classifier


def workbook(rows=None):
    if rows is None:
        rows = [{"course_name": "课程A", "session": f"第{i}期", "respondent_id": str(i),
                 "feedback_id": str(i), "category": "讲师表现", "subcategory": "讲解清晰",
                 "sentiment": "positive", "summary": "讲解清晰", "evidence": "老师讲解清晰"} for i in (1, 2)]
    stream = BytesIO()
    pd.DataFrame(rows).to_excel(stream, sheet_name="AI反馈分类明细", index=False)
    return stream.getvalue()


def test_summary_replay_does_not_classify_or_generate_trends(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", "replay-test")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "deepseek_config", SimpleNamespace(DEEPSEEK_API_KEY="test", DEEPSEEK_BASE_URL="https://example.invalid", DEEPSEEK_MODEL="test"))
    monkeypatch.setattr(classifier, "deepseek_analyze_feedback", lambda **_: pytest.fail("must not classify again"))
    monkeypatch.setattr(generator.time, "sleep", lambda _: None)
    seen = []

    def summary(input_data, prompt, model_type, *args, **kwargs):
        assert model_type is generator.SessionSummary
        assert kwargs["use_cache"] is False
        seen.append(input_data)
        return {"course_name": input_data["course_name"], "session": input_data["session"],
                "overall_assessment": "已生成", "strengths": [], "problems": [], "recommendations": [],
                "management_summary": "已生成"}, {"_cache_hit": False, "_api_called": 1, "_retries": 0}

    monkeypatch.setattr(generator, "_call_llm", summary)
    with TestClient(app, headers={"Authorization": "Bearer replay-test"}) as client:
        response = client.post("/analysis/summary", data={"use_cache": "false", "include_report": "true"},
                               files={"file": ("classification.xlsx", workbook())})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["profile"] == "summary_replay"
        assert result["summary_success_count"] == len(seen) == 2
        assert result["classification_requests"] == 0
        assert result["summary_cache_enabled"] is False
        assert result["report_delivery"] == "inline_and_link"
        assert all(row["top_negative"] == row["top_suggestions"] == [] for row in seen)
        report = client.get(result["download_url"])
        assert "AI反馈分类明细" in pd.ExcelFile(BytesIO(report.content)).sheet_names


@pytest.mark.parametrize("kind", ["missing", "unknown_label", "sentiment", "oversized", "many_sessions", "duplicate"])
def test_bad_replay_input_is_rejected_before_summary(monkeypatch, kind):
    monkeypatch.setenv("SERVICE_API_KEY", "replay-test")
    from core import summary_replay
    monkeypatch.setattr(summary_replay, "generate_summaries", lambda *a, **k: pytest.fail("must reject first"))
    row={"course_name":"A","session":"1","respondent_id":"1","feedback_id":"1","category":"讲师表现",
         "subcategory":"讲解清晰","sentiment":"positive","summary":"清晰","evidence":"讲解清晰"}
    rows=[row]
    if kind=="missing":del row["evidence"]
    elif kind=="unknown_label":row["subcategory"]="新标签"
    elif kind=="sentiment":row["sentiment"]="negative"
    elif kind=="oversized":rows=[{**row,"respondent_id":str(i)} for i in range(501)]
    elif kind=="many_sessions":rows=[{**row,"session":str(i)} for i in range(7)]
    else:rows=[row,row]
    with TestClient(app, headers={"Authorization":"Bearer replay-test"}) as client:
        assert client.post("/analysis/summary", files={"file":("replay.xlsx",workbook(rows))}).status_code==422


def test_replay_requires_auth(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "replay-test")
    with TestClient(app) as client:
        assert client.post("/analysis/summary", files={"file":("replay.xlsx",workbook())}).status_code==401
