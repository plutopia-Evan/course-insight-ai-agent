from fastapi import APIRouter
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from api.request_limits import MAX_FEEDBACK_CHARS, MAX_FEEDBACK_ITEMS

from llm.deepseek_feedback_analyzer import (
    deepseek_analyze_feedback
)


router = APIRouter(
    tags=["feedback"]
)

class FeedbackRequest(BaseModel):
    feedback_texts: list[
        Annotated[str, StringConstraints(max_length=MAX_FEEDBACK_CHARS)]
    ] = Field(max_length=MAX_FEEDBACK_ITEMS)


@router.post("/feedback_analysis")
def feedback_analysis(
        request:FeedbackRequest
):

    results=[]


    for idx,text in enumerate(
        request.feedback_texts
    ):
        result = deepseek_analyze_feedback(
            feedback_id=str(idx + 1),
            feedback_text=text,
        )

        results.append(result)

    errors = [
        {"feedback_id": result["feedback_id"], "error": result["_error"]}
        for result in results if result.get("_error")
    ]
    return {
        "status": "partial" if errors else "complete",
        "feedback_response_count": len(results),

        "feedback_item_count": sum(len(result.get("items", [])) for result in results),

        "feedback_count": sum(len(result.get("items", [])) for result in results),

        "feedback_failed_count": len(errors),

        "feedback_errors": errors,

        "analysis":
            results
    }
