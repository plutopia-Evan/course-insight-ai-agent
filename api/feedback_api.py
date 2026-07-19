from fastapi import FastAPI
from pydantic import BaseModel

from deepseek_feedback_analyzer import (
    deepseek_analyze_feedback
)


app = FastAPI(
    title="Feedback Analysis Tool"
)


class FeedbackRequest(BaseModel):

    course_name:str

    session:str

    feedback_texts:list[str]


@app.post("/feedback_analysis")
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
            course_name=request.course_name,
            session=request.session
        )

        results.append(result)

    return {

        "course_name":
            request.course_name,

        "session":
            request.session,

        "feedback_count":
            len(results),

        "analysis":
            results
    }