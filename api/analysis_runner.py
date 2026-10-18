"""Run the blocking survey and model pipeline outside the API event loop."""

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from agent.orchestrator import CourseInsightAgent
from api.upload_storage import saved_upload


def _analyze_path(file_path: str) -> dict:
    return CourseInsightAgent().run(file_path)


async def analyze_upload(file: UploadFile) -> dict:
    async with saved_upload(file) as file_path:
        return await run_in_threadpool(_analyze_path, str(file_path))
