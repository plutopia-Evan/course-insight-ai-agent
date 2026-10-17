"""Generated reports retain their own files and use one download directory."""

from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from agent.report_agent import ReportAgent
from api.report_api import download_file


def _report_context(marker):
    return {
        "course_name": "课程/分析",
        "session": "第01期",
        "summary": {"marker": marker},
        "feedback_results": [],
        "feedback_errors": [],
        "df_long": pd.DataFrame(),
        "session_stats": pd.DataFrame(),
        "anomalies": pd.DataFrame(),
    }


def test_repeated_analysis_keeps_both_reports(monkeypatch, tmp_path):
    output_dir = tmp_path / "reports"
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(output_dir))

    first = Path(ReportAgent().run(_report_context("first"))["report_path"])
    second = Path(ReportAgent().run(_report_context("second"))["report_path"])

    assert first != second
    assert first.parent == second.parent == output_dir
    assert first.is_file() and second.is_file()
    assert "/" not in first.name
    assert pd.read_excel(first, sheet_name="数据总览").loc[0, "marker"] == "first"
    assert pd.read_excel(second, sheet_name="数据总览").loc[0, "marker"] == "second"
    assert Path(download_file(first.name).path) == first
    assert Path(download_file(second.name).path) == second


@pytest.mark.parametrize("filename", ["../outside.xlsx", "..\\outside.xlsx", "C:outside.xlsx", "report.csv"])
def test_download_rejects_unsafe_name(monkeypatch, tmp_path, filename):
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as error:
        download_file(filename)
    assert error.value.status_code == 404
