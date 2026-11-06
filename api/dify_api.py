"""Dify-compatible upload response sharing the standard analysis contract."""

from fastapi import APIRouter, UploadFile, File

from api.analysis_runner import analyze_upload
from core.analysis_results import analysis_payload


router = APIRouter()


@router.post("/dify/analyze")
async def dify_analyze(file: UploadFile = File(...)):
    result = await analyze_upload(file)
    return {
        **analysis_payload(result),
        "success": result["summary"]["analysis_status"] == "complete",
        # Keep aliases for existing integrations; new clients use the common fields.
        "feedback_summary": result.get("feedback_results", []),
        "report_path": result.get("report_path", ""),
    }
