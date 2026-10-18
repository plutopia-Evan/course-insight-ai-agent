from datetime import datetime, date

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

import os
import numpy as np
import pandas as pd


from api.analysis_runner import analyze_upload


router = APIRouter(
    tags=["analysis"]
)


# ===============================
# numpy / pandas JSON转换
# ===============================

def convert_numpy(obj):

    import math


    if isinstance(obj, np.integer):
        return int(obj)


    elif isinstance(obj, np.floating):

        value = float(obj)

        if math.isnan(value) or math.isinf(value):
            return None

        return value


    elif isinstance(obj, float):

        if math.isnan(obj) or math.isinf(obj):
            return None

        return obj


    elif isinstance(obj, np.ndarray):

        return [
            convert_numpy(x)
            for x in obj.tolist()
        ]


    elif isinstance(obj, pd.DataFrame):

        return [
            convert_numpy(row)
            for row in obj.to_dict(
                orient="records"
            )
        ]


    elif isinstance(obj, pd.Series):

        return [
            convert_numpy(x)
            for x in obj.tolist()
        ]


    elif isinstance(obj, pd.Timestamp):

        return obj.isoformat()


    elif isinstance(obj, (datetime,date)):

        return obj.isoformat()


    elif isinstance(obj, dict):

        return {
            k:convert_numpy(v)
            for k,v in obj.items()
        }


    elif isinstance(obj,list):

        return [
            convert_numpy(x)
            for x in obj
        ]


    else:

        return obj



# ===============================
# 文件上传分析接口
# ===============================


@router.post("/analysis")
async def analysis(
        file: UploadFile = File(...)
):


    # ==========================
    # 1. 保存上传文件
    # ==========================

    result = await analyze_upload(file)



    # ==========================
    # 3. 返回结果
    # ==========================


    response = {

        "status": result["analysis_status"],

        "feedback_analyzed_count": result["feedback_analyzed_count"],

        "feedback_failed_count": result["feedback_failed_count"],

        "feedback_skipped_count": result["feedback_skipped_count"],

        "feedback_response_count": result["feedback_response_count"],

        "feedback_item_count": result["feedback_item_count"],

        "feedback_errors": result["feedback_errors"],

        "download_url": f"/download/{os.path.basename(result['report_path'])}",


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
            result.get(
                "student_count",
                0
            ),


        "rating_total":
            result.get(
                "rating_total",
                0
            ),


        "valid_rating_count":
            result.get(
                "valid_rating_count",
                0
            ),


        "feedback_count":
            result.get(
                "feedback_count",
                0
            ),


        "anomaly_count":
            result.get(
                "anomaly_count",
                0
            ),


        "normalized_long":
            result.get(
                "df_long",
                []
            ),


        "anomalies":
            result.get(
                "anomalies",
                []
            ),


        "feedback_results":
            result.get(
                "feedback_results",
                []
            )

    }



    return JSONResponse(
        content=convert_numpy(response)
    )
