from fastapi import FastAPI

from api.analysis_api import app as analysis_app
from api.feedback_api import app as feedback_app
from api.report_api import app as report_app


app = FastAPI(
    title="Course Insight AI Agent API"
)


@app.get("/")
def root():

    return {
        "message":
        "Course Insight AI Agent API is running"
    }


# 注册三个接口

for route in analysis_app.routes:
    app.router.routes.append(route)


for route in feedback_app.routes:
    app.router.routes.append(route)


for route in report_app.routes:
    app.router.routes.append(route)