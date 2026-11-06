"""An authorized response can retain a report beyond server file lifetime."""

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from api import batch_api
from api.main_api import app
from core.examples import sample_uploads


def test_inline_report_matches_download_and_survives_server_cleanup(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", "inline-test")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path))
    sample = sample_uploads()[0]
    with TestClient(app, headers={"Authorization": "Bearer inline-test"}) as client:
        response = client.post("/analysis/batch", data={"include_report": "true"},
                               files={"files": (sample.name, sample.data)})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        copied = base64.b64decode(data["report_file"]["content_base64"], validate=True)
        assert len(copied) == data["report_file"]["size_bytes"]
        assert hashlib.sha256(copied).hexdigest() == data["report_file"]["sha256"]
        assert copied == client.get(data["download_url"]).content
        record_path = tmp_path / "analyses" / f"{data['analysis_id']}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert "report_file" not in record["result"]
        (tmp_path / data["report_file"]["filename"]).unlink()
        record_path.unlink()
        assert client.get(data["download_url"]).status_code == 404
        assert client.get(data["result_url"]).status_code == 404
        # The already authorized copy remains a complete, readable workbook.
        assert not pd.read_excel(BytesIO(copied), sheet_name="期次评分统计").empty


def test_report_copy_is_opt_in_and_size_bounded(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", "inline-test")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path))
    sample = sample_uploads()[0]
    with TestClient(app, headers={"Authorization": "Bearer inline-test"}) as client:
        result = client.post("/analysis/batch", files={"files": (sample.name, sample.data)}).json()
        assert "report_file" not in result
        monkeypatch.setattr(batch_api, "MAX_INLINE_REPORT_BYTES", 1)
        result = client.post("/analysis/batch", data={"include_report": "true"},
                             files={"files": (sample.name, sample.data)}).json()
        assert "report_file" not in result
        assert result["report_inline_reason"] == "size_limit"
        assert client.get(result["download_url"]).status_code == 200


def test_report_copy_does_not_bypass_authorization(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "inline-test")
    sample = sample_uploads()[0]
    with TestClient(app) as client:
        response = client.post("/analysis/batch", data={"include_report": "true"},
                               files={"files": (sample.name, sample.data)})
        assert response.status_code == 401
