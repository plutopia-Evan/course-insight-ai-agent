from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse

import os
import pandas as pd

from agent.course_pipeline import run_course_analysis
from core.output_writer import write_output_excel


app = FastAPI(
    title="Report Generation Tool"
)



# ==========================
# 生成报告接口
# ==========================

@app.post("/generate_report")
async def generate_report(
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
    # 2. 调用分析Pipeline
    # ==========================

    result = run_course_analysis(
        file_path
    )



    course_name = result.get(
        "course_name",
        ""
    )


    session = result.get(
        "session",
        ""
    )



    # ==========================
    # 3. 输出路径
    # ==========================

    output_dir = "data/output"


    os.makedirs(
        output_dir,
        exist_ok=True
    )


    output_path = (
        f"{output_dir}/"
        f"{course_name}_{session}_分析报告.xlsx"
    )



    # ==========================
    # 4. 构造Excel数据
    # ==========================

    data = {}



    # --------------------------
    # 数据总览
    # --------------------------

    data["overview"] = pd.DataFrame(
        [
            {

                "课程名称":
                    course_name,


                "期次":
                    session,


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
                    )

            }
        ]
    )



    # --------------------------
    # AI反馈分析
    # --------------------------

    # --------------------------
    # AI反馈分析
    # --------------------------

    feedback_rows = []

    for item in result.get(
            "feedback_results",
            []
    ):

        # 情况1：
        # 存在items，多分类反馈

        if "items" in item:

            for feedback in item.get(
                    "items",
                    []
            ):
                feedback_rows.append(
                    {

                        "feedback_id":
                            item.get(
                                "feedback_id",
                                ""
                            ),

                        "course_name":
                            course_name,

                        "session":
                            session,

                        "category":
                            feedback.get(
                                "category",
                                ""
                            ),

                        "subcategory":
                            feedback.get(
                                "subcategory",
                                ""
                            ),

                        "sentiment":
                            feedback.get(
                                "sentiment",
                                ""
                            ),

                        "summary":
                            feedback.get(
                                "summary",
                                ""
                            ),

                        "evidence":
                            feedback.get(
                                "evidence",
                                ""
                            )

                    }
                )


        # 情况2：
        # 单条反馈直接返回

        else:

            feedback_rows.append(
                {

                    "feedback_id":
                        item.get(
                            "feedback_id",
                            ""
                        ),

                    "course_name":
                        course_name,

                    "session":
                        session,

                    "category":
                        item.get(
                            "category",
                            ""
                        ),

                    "subcategory":
                        item.get(
                            "subcategory",
                            ""
                        ),

                    "sentiment":
                        item.get(
                            "sentiment",
                            ""
                        ),

                    "summary":
                        item.get(
                            "summary",
                            ""
                        ),

                    "evidence":
                        item.get(
                            "evidence",
                            ""
                        )

                }
            )

    data["feedback_detail"] = pd.DataFrame(
        feedback_rows
    )


    # --------------------------
    # 标准化长表
    # --------------------------

    df_long = result.get(
        "df_long",
        pd.DataFrame()
    )


    if isinstance(
        df_long,
        pd.DataFrame
    ):

        data["normalized_long"] = df_long

    else:

        data["normalized_long"] = pd.DataFrame()



    # --------------------------
    # 异常数据
    # --------------------------

    anomalies = result.get(
        "anomalies",
        []
    )


    data["anomalies"] = pd.DataFrame(
        anomalies
    )



    # ==========================
    # 5. 补齐Excel Sheet
    # ==========================

    empty_sheets = [

        "file_identification",

        "question_mapping_result",

        "question_coverage",

        "auto_coverage",

        "global_common_stats",

        "course_common_stats",

        "period_specific_stats",

        "session_stats",

        "feedback_frequency",

        "pending_review"

    ]


    for sheet in empty_sheets:

        data[sheet] = pd.DataFrame()



    # ==========================
    # 6. 写入Excel
    # ==========================

    write_output_excel(
        output_path,
        data
    )



    # ==========================
    # 7. 返回结果
    # ==========================

    return {

        "status":
            "success",

        "course_name":
            course_name,

        "session":
            session,

        "download_url":
            f"/download/{os.path.basename(output_path)}"

    }

# ==========================
# 文件下载接口
# ==========================

@app.get("/download/{filename}")
def download_file(
        filename: str
):

    file_path = os.path.join(
        "data/output",
        filename
    )


    return FileResponse(
        path=file_path,
        filename=filename
    )