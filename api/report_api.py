from fastapi import FastAPI
from pydantic import BaseModel

import os
import pandas as pd

from agent.course_pipeline import run_course_analysis
from output_writer import write_output_excel


app = FastAPI(
    title="Report Generation Tool"
)


class ReportRequest(BaseModel):

    file_path: str



@app.post("/generate_report")
def generate_report(
        request: ReportRequest
):

    # ==========================
    # 1. 调用分析Pipeline
    # ==========================

    result = run_course_analysis(
        request.file_path
    )


    course_name = result["course_name"]

    session = result["session"]



    # ==========================
    # 2. 输出路径
    # ==========================

    output_path = (
        "data/output/"
        f"{course_name}_{session}_分析报告.xlsx"
    )


    os.makedirs(
        "data/output",
        exist_ok=True
    )



    # ==========================
    # 3. 构造Excel数据
    # ==========================

    data = {}



    # 课程概览

    data["overview"] = pd.DataFrame(
        [
            {
                "课程名称":
                    course_name,

                "期次":
                    session,

                "异常数量":
                    len(
                        result["anomalies"]
                    ),

                "反馈数量":
                    len(
                        result["feedback_results"]
                    )
            }
        ]
    )



    # ==========================
    # 反馈分析结果
    # ==========================

    feedback_rows = []


    for item in result["feedback_results"]:

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
                        item.get(
                            "course_name",
                            course_name
                        ),

                    "session":
                        item.get(
                            "session",
                            session
                        ),

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


    data["feedback_detail"] = pd.DataFrame(
        feedback_rows
    )



    # ==========================
    # 原始长表
    # ==========================

    data["normalized_long"] = (
        result["df_long"]
    )



    # ==========================
    # 异常数据
    # ==========================

    data["anomalies"] = pd.DataFrame(
        result["anomalies"]
    )



    # ==========================
    # 补充Excel Sheet
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

        if sheet not in data:

            data[sheet] = pd.DataFrame()



    # ==========================
    # 写入Excel
    # ==========================

    write_output_excel(
        output_path,
        data
    )



    return {

        "status":
            "success",

        "course_name":
            course_name,

        "session":
            session,

        "file_path":
            output_path

    }