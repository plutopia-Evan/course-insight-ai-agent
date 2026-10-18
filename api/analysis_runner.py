"""Run the blocking survey and model pipeline outside the API event loop."""

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from agent.orchestrator import CourseInsightAgent
from agent.feedback_agent import FeedbackLimitExceeded
from api.request_limits import MAX_FEEDBACK_CHARS, MAX_FEEDBACK_ITEMS
from api.upload_storage import saved_upload


def _analyze_path(file_path: str) -> dict:
    return CourseInsightAgent().run(
        file_path,
        max_feedback_count=MAX_FEEDBACK_ITEMS,
        max_feedback_chars=MAX_FEEDBACK_CHARS,
    )


async def analyze_upload(file: UploadFile) -> dict:
    async with saved_upload(file) as file_path:
        try:
            return await run_in_threadpool(_analyze_path, str(file_path))
        except FeedbackLimitExceeded as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
