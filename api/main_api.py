from fastapi import Depends, FastAPI

from api.auth import require_service_token
from api.analysis_api import router as analysis_router
from api.feedback_api import router as feedback_router
from api.report_api import router as report_router


app = FastAPI(
    title="Course Insight AI Agent API"
)

from api.dify_api import router as dify_router


app.include_router(dify_router, dependencies=[Depends(require_service_token)])

@app.get("/")
def root():

    return {
        "message":
        "Course Insight AI Agent API is running"
    }


for protected_router in (analysis_router, feedback_router, report_router):
    app.include_router(protected_router, dependencies=[Depends(require_service_token)])
