from fastapi import APIRouter
from pydantic import BaseModel

from llm.deepseek_feedback_analyzer import (
    deepseek_analyze_feedback
)


router = APIRouter(
    tags=["feedback"]
)

class FeedbackRequest(BaseModel):
    feedback_texts:list[str]


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

    return {
        "feedback_count":
            len(results),

        "analysis":
            results
    }