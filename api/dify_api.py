from fastapi import APIRouter, UploadFile, File
import shutil
import os

from agent.orchestrator import CourseInsightAgent


router = APIRouter()



@router.post("/dify/analyze")
async def dify_analyze(
        file: UploadFile = File(...)
):


    # =====================
    # 1. 保存上传文件
    # =====================

    upload_dir = "data/upload"


    os.makedirs(
        upload_dir,
        exist_ok=True
    )


    file_path = (
        f"{upload_dir}/"
        f"{file.filename}"
    )


    with open(
        file_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )



    # =====================
    # 2. 调用Agent
    # =====================

    agent = CourseInsightAgent()


    result = agent.run(
        file_path
    )



    # =====================
    # 3. 处理overview
    # =====================

    overview = result.get(
        "overview",
        {}
    )


    # 如果是DataFrame

    if hasattr(
        overview,
        "to_dict"
    ):

        if len(overview) > 0:

            overview = (
                overview
                .iloc[0]
                .to_dict()
            )

        else:

            overview = {}



    # =====================
    # 4. 返回Dify需要的数据
    # =====================

    return {


        "success": True,


        "course_name":
            result.get(
                "course_name",
                ""
            ),


        "session":
            result.get(
                "session",
                ""
            ),


        "student_count":
            overview.get(
                "student_count",
                0
            ),


        "rating_total":
            overview.get(
                "rating_total",
                0
            ),


        "valid_rating_count":
            overview.get(
                "valid_rating_count",
                0
            ),


        "feedback_summary":
            result.get(
                "feedback_results",
                []
            ),


        "anomaly_count":
            len(
                result.get(
                    "anomalies",
                    []
                )
            ),


        "report_path":
            result.get(
                "report_path",
                ""
            )

    }