from fastapi import FastAPI

from api.analysis_api import router as analysis_router
from api.feedback_api import router as feedback_router
from api.report_api import router as report_router


app = FastAPI(
    title="Course Insight AI Agent API"
)

from api.dify_api import router as dify_router


app.include_router(
    dify_router
)

@app.get("/")
def root():

    return {
        "message":
        "Course Insight AI Agent API is running"
    }


app.include_router(
    analysis_router
)


app.include_router(
    feedback_router
)


app.include_router(
    report_router
)