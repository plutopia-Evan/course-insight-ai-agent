from fastapi import APIRouter, UploadFile, File

from api.analysis_runner import analyze_upload


router = APIRouter()



@router.post("/dify/analyze")
async def dify_analyze(
        file: UploadFile = File(...)
):


    # =====================
    # 1. 保存上传文件
    # =====================

    result = await analyze_upload(file)



    # =====================
    # 3. 处理overview
    # =====================

    overview = result["summary"]



    # =====================
    # 4. 返回Dify需要的数据
    # =====================

    return {


        "success": overview["analysis_status"] == "complete",

        "status": overview["analysis_status"],

        "feedback_failed_count": overview["feedback_failed_count"],

        "feedback_response_count": overview["feedback_response_count"],

        "feedback_item_count": overview["feedback_item_count"],

        "feedback_errors": result["feedback_errors"],


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
            overview["anomaly_count"],


        "report_path":
            result.get(
                "report_path",
                ""
            )

    }
