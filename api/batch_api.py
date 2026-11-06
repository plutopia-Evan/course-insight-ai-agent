"""Batch endpoint sharing the exact operator UI analysis service."""

import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Response
from starlette.concurrency import run_in_threadpool

from api.upload_storage import saved_upload
from core.batch_service import run_batch_analysis
from core.input_validation import SurveyInputError
from core.analysis_results import save_analysis_result
from core.report_storage import new_report_path
from core.report_delivery import attach_report_copy, MAX_INLINE_REPORT_BYTES


router = APIRouter(tags=["batch"])


def records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def analyze_batch_files(files, mapping, enable_ai, include_report=False):
    with tempfile.TemporaryDirectory(prefix="course-batch-") as directory:
        result = run_batch_analysis(files, mapping, directory, enable_ai=enable_ai)
        path = new_report_path("批量课程", "多期")
        path.write_bytes(result["complete_xlsx_bytes"])
        overview = dict(zip(result["overview"]["指标"], result["overview"]["数值"]))
        ai = result.get("ai_results")
        errors = records(ai["errors"]) if ai else []
        details = records(ai["classification_detail"]) if ai else []
        summary = {
            "analysis_status": result["analysis_status"],
            "profile": "batch_ai" if enable_ai else "batch_statistics",
            "course_session_count": result["total_course_sessions"],
            "student_count": int(overview.get("总学员人次", 0)),
            "valid_rating_count": int(overview.get("有效评分数", 0)),
            "anomaly_count": int(len(result["anomalies"])),
            "feedback_response_count": len(result["feedback_detail"]),
            "feedback_item_count": len(details),
            "feedback_failed_count": sum(bool(row.get("feedback_id")) for row in errors),
        }
        context = {
            "course_name": "批量课程", "session": "多期", "summary": summary,
            "report_path": str(path), "feedback_results": details, "feedback_errors": errors,
            "data_quality_issues": records(result["pending_review"]),
            "ai_tables": {name: records(frame) for name, frame in (ai or {}).items()},
        }
        payload = save_analysis_result(context)
        return attach_report_copy(payload, path.name, result["complete_xlsx_bytes"], include_report, MAX_INLINE_REPORT_BYTES)


@router.post("/analysis/batch")
async def batch_analysis(
    files: Annotated[list[UploadFile], File()],
    response: Response,
    mapping: Annotated[UploadFile | None, File()] = None,
    enable_ai: Annotated[bool, Form()] = False,
    include_report: Annotated[bool, Form()] = False,
):
    response.headers["Cache-Control"] = "no-store"
    if not 1 <= len(files) <= 10:
        raise HTTPException(status_code=422, detail="每次请上传 1—10 份问卷")
    total = 0
    payloads = []
    for file in files:
        async with saved_upload(file) as path:
            data = path.read_bytes()
            total += len(data)
            if total > 10 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="本次上传合计不能超过 10 MB")
            payloads.append((file.filename, data))
    mapping_data = ("question_mapping.xlsx", Path("config/question_mapping.xlsx").read_bytes())
    if mapping is not None:
        async with saved_upload(mapping) as path:
            mapping_data = (mapping.filename, path.read_bytes())
    try:
        return await run_in_threadpool(analyze_batch_files, payloads, mapping_data, enable_ai, include_report)
    except SurveyInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
