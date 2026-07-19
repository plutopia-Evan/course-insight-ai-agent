from fastapi import FastAPI
from pydantic import BaseModel

import os

from survey_processor import (
    load_question_mapping,
    read_survey_file,
    wide_to_long,
    map_questions,
    detect_anomalies,
    get_valid_ratings,
    split_rating_and_text
)

from statistics import (
    compute_overview_stats
)


app = FastAPI(
    title="Course Survey Analysis Tool"
)


class AnalysisRequest(BaseModel):
    file_path: str


@app.post("/analysis")
def analysis(request: AnalysisRequest):

    file_path = request.file_path


    # 1. 检查文件
    if not os.path.exists(file_path):
        return {
            "error": "文件不存在",
            "file_path": file_path
        }


    # 2. 加载题目映射
    mapping_path = "config/question_mapping.xlsx"

    mapping_df = load_question_mapping(
        mapping_path
    )


    # 3. 读取问卷
    course_name, session, df, questions, meta = read_survey_file(
        file_path
    )


    # 4. 宽表转长表
    df_long = wide_to_long(
        df,
        questions
    )


    # 5. 题目映射
    df_long = map_questions(
        df_long,
        mapping_df
    )


    # 6. 异常检测
    anomalies = detect_anomalies(
        df_long
    )


    # 7. 获取有效评分
    valid_ratings = get_valid_ratings(
        df_long
    )


    # 8. 文本反馈
    rating_df, text_df = split_rating_and_text(
        df_long
    )


    # 9. 计算基础指标

    student_count = (
        df_long[
            ["学员编号",
             "course_name",
             "session"]
        ]
        .drop_duplicates()
        .shape[0]
    )


    result = {

        "course_name": course_name,

        "session": session,

        "student_count": student_count,

        "rating_total":
            len(rating_df),

        "valid_rating_count":
            len(valid_ratings),

        "feedback_count":
            len(text_df),

        "anomaly_count":
            len(anomalies)

    }


    return result