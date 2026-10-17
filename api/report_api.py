"""Report endpoints backed by the same analysis used by /analysis."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agent.orchestrator import CourseInsightAgent


router = APIRouter(tags=["report"])


@router.post("/generate_report")
async def generate_report(file: UploadFile = File(...)):
    upload_dir = Path("data/upload")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / Path(file.filename or "survey.xlsx").name
    with file_path.open("wb") as output:
        output.write(await file.read())

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
    file_path = Path("data/output") / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path=file_path, filename=filename)
