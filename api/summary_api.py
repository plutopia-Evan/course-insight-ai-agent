"""Protected, bounded summary-only retry endpoint."""
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from api.upload_storage import saved_upload
from core.input_validation import SurveyInputError
from core.summary_replay import replay_summaries

router = APIRouter(tags=["summary"])


@router.post("/analysis/summary")
async def regenerate_summary(
    file: Annotated[UploadFile, File()], response: Response,
    include_report: Annotated[bool, Form()] = False,
    use_cache: Annotated[bool, Form()] = True,
):
    response.headers["Cache-Control"] = "no-store"
    async with saved_upload(file) as path:
        try:
            return await run_in_threadpool(replay_summaries, str(path), include_report, use_cache)
        except SurveyInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
