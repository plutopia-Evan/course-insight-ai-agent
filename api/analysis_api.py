from datetime import datetime, date

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

import os
import uuid
import numpy as np
import pandas as pd


from agent.course_pipeline import run_course_analysis



app = FastAPI(
    title="Analysis API"
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


@app.post("/analysis")
async def analysis(
        file: UploadFile = File(...)
):


    # ==========================
    # 1. 保存上传文件
    # ==========================

    upload_dir = "data/upload"


    os.makedirs(
        upload_dir,
        exist_ok=True
    )


    filename = file.filename

    file_path = os.path.join(
        upload_dir,
        filename
    )


    with open(
        file_path,
        "wb"
    ) as f:

        content = await file.read()

        f.write(content)



    # ==========================
    # 2. 调用分析pipeline
    # ==========================


    result = run_course_analysis(
        file_path
    )



    # ==========================
    # 3. 返回结果
    # ==========================


    response = {


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