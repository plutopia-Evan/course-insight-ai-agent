import pandas as pd


class FeedbackAgent:


    def run(self, survey_result):


        from llm.ai_feedback_analyzer import (
            mock_analyze_feedback
        )


        # =====================
        # 获取长表数据
        # =====================

        if "df_long" in survey_result:

            df_long = survey_result["df_long"]


        elif "normalized_long" in survey_result:

            df_long = pd.DataFrame(
                survey_result["normalized_long"]
            )


        else:

            return {

                "feedback_results": []

            }



        course_name = survey_result.get(
            "course_name",
            ""
        )


        session = survey_result.get(
            "session",
            ""
        )


        # =====================
        # 筛选文本反馈
        # =====================

        text_df = df_long[
            df_long["question_type"]
            ==
            "text"
        ]



        feedback_results = []



        for idx,row in text_df.iterrows():


            result = mock_analyze_feedback(

                feedback_id=str(idx),

                feedback_text=str(
                    row.get(
                        "response_value",
                        ""
                    )
                ),

                course_name=course_name,

                session=session

            )


            feedback_results.append(
                result
            )



        return {


            "feedback_results":
                feedback_results

        }