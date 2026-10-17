"""Report endpoints backed by the same analysis used by /analysis."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agent.orchestrator import CourseInsightAgent
from api.upload_storage import saved_upload
from core.report_storage import report_directory


router = APIRouter(tags=["report"])


@router.post("/generate_report")
async def generate_report(file: UploadFile = File(...)):
    async with saved_upload(file) as file_path:
        result = CourseInsightAgent().run(str(file_path))
    return {
        "status": result["analysis_status"],
        "course_name": result["course_name"],
        "session": result["session"],
        **result["summary"],
        "feedback_errors": result["feedback_errors"],
        "download_url": f"/download/{Path(result['report_path']).name}",
    }


@router.get("/download/{filename}")
def download_file(filename: str):
    if (filename != Path(filename).name or any(char in filename for char in "/\\:\x00")
            or Path(filename).suffix.lower() != ".xlsx"):
        raise HTTPException(status_code=404, detail="Report not found")
    file_path = report_directory() / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path=file_path, filename=filename)
