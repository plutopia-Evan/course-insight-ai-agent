"""Report endpoints backed by the same analysis used by /analysis."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.analysis_runner import analyze_upload
from core.report_storage import report_directory
from core.analysis_results import analysis_payload, load_analysis_result


router = APIRouter(tags=["report"])


@router.post("/generate_report")
async def generate_report(
    file: Annotated[UploadFile | None, File()] = None,
    analysis_id: Annotated[str | None, Form()] = None,
):
    """Reuse analysis_id, or accept a file for the legacy one-step upload flow."""
    if (file is None) == (analysis_id is None):
        raise HTTPException(status_code=422, detail="请仅提供 file 或 analysis_id 其中一项")
    if analysis_id is not None:
        try:
            return load_analysis_result(analysis_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis_payload(await analyze_upload(file))


@router.get(
    "/download/{filename}",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Excel report",
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
def download_file(filename: str):
    if (filename != Path(filename).name or any(char in filename for char in "/\\:\x00")
            or Path(filename).suffix.lower() != ".xlsx"):
        raise HTTPException(status_code=404, detail="Report not found")
    file_path = report_directory() / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path=file_path, filename=filename)
