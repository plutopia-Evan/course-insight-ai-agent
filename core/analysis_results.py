"""Persist one analysis so follow-up reads never rerun the model pipeline."""

import json
import re
from pathlib import Path
from uuid import uuid4

from core.report_storage import report_directory


def analysis_payload(result: dict) -> dict:
    """Common result contract for upload, report and Dify endpoints."""
    payload = {
        "course_name": result.get("course_name", ""),
        "session": result.get("session", ""),
        **result["summary"],
        "status": result["summary"]["analysis_status"],
        "feedback_errors": result.get("feedback_errors", []),
        "feedback_results": result.get("feedback_results", []),
        "download_url": f"/download/{Path(result['report_path']).name}",
    }
    if result.get("analysis_id"):
        payload["analysis_id"] = result["analysis_id"]
        payload["result_url"] = f"/analyses/{result['analysis_id']}"
    return payload


def save_analysis_result(result: dict) -> dict:
    """Save only JSON-ready results beside the existing report, not the upload."""
    directory = report_directory().resolve()
    report = Path(result["report_path"]).resolve()
    if report.parent != directory or not report.is_file() or report.suffix.lower() != ".xlsx":
        raise ValueError("分析报告未生成，无法保存分析结果")

    analysis_id = uuid4().hex
    payload = analysis_payload({**result, "analysis_id": analysis_id})
    record = {"version": 1, "report_filename": report.name, "result": payload}
    content = json.dumps(record, ensure_ascii=False, allow_nan=False)
    records = directory / "analyses"
    records.mkdir(parents=True, exist_ok=True)
    with (records / f"{analysis_id}.json").open("x", encoding="utf-8") as stream:
        stream.write(content)
    return payload


def load_analysis_result(analysis_id: str) -> dict:
    """Read a saved result; missing/corrupt artifacts are never regenerated."""
    if not isinstance(analysis_id, str) or not re.fullmatch(r"[0-9a-f]{32}", analysis_id):
        raise LookupError("分析结果不存在或已失效")
    directory = report_directory().resolve()
    try:
        record = json.loads((directory / "analyses" / f"{analysis_id}.json").read_text(encoding="utf-8"))
        filename = record["report_filename"]
        payload = record["result"]
        if (
            record["version"] != 1
            or payload["analysis_id"] != analysis_id
            or not isinstance(filename, str)
            or any(char in filename for char in "/\\:\x00")
            or Path(filename).suffix.lower() != ".xlsx"
            or not (directory / filename).is_file()
        ):
            raise ValueError("Invalid analysis record")
        return {
            **payload,
            "result_url": f"/analyses/{analysis_id}",
            "download_url": f"/download/{filename}",
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LookupError("分析结果不存在或已失效") from exc
