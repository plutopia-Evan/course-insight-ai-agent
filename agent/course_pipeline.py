"""
课程分析Agent Pipeline

负责:
1.读取问卷
2.评分统计
3.反馈分析
4.生成报告
"""


from survey_processor import (
    read_survey_file,
    load_question_mapping,
    wide_to_long,
    map_questions,
    detect_anomalies,
    get_valid_ratings,
    split_rating_and_text
)


from statistics import (
    compute_overview_stats,
    compute_session_stats
)


from ai_feedback_analyzer import (
    mock_analyze_feedback
)


def run_course_analysis(file_path):

    # ======================
    # 1.读取问卷
    # ======================

    (
        course_name,
        session,
        df,
        question_headers,
        meta_headers

    ) = read_survey_file(file_path)


    # ======================
    # 2.读取题目映射
    # ======================

    mapping = load_question_mapping(
        "config/question_mapping.xlsx"
    )


    # ======================
    # 3.宽表转长表
    # ======================

    df_long = wide_to_long(
        df,
        question_headers
    )


    # ======================
    # 4.题目映射
    # ======================

    df_long = map_questions(
        df_long,
        mapping
    )


    # ======================
    # 5.异常检测
    # ======================

    anomalies = detect_anomalies(
        df_long
    )


    # ======================
    # 6.有效评分
    # ======================

    valid_rating = get_valid_ratings(
        df_long
    )


    # ======================
    # 7.拆分文本反馈
    # ======================

    rating_df,text_df = split_rating_and_text(
        df_long
    )


    # ======================
    # 8.AI反馈分析
    # ======================

    feedback_results=[]


    for idx,row in text_df.iterrows():

        result = mock_analyze_feedback(
            feedback_id=str(idx),
            feedback_text=str(
                row["response_value"]
            ),
            course_name=course_name,
            session=session
        )

        feedback_results.append(result)


    return {

        "course_name":course_name,

        "session":session,

        "valid_rating":valid_rating,

        "anomalies":anomalies,

        "feedback_results":feedback_results,

        "df_long":df_long

    }