class ReportAgent:


    def run(self, context):


        from core.output_writer import (
            write_output_excel
        )

        import pandas as pd
        import os



        # =====================
        # 基础信息
        # =====================

        course_name = context.get(
            "course_name",
            ""
        )


        session = context.get(
            "session",
            ""
        )



        # =====================
        # 输出路径
        # =====================

        output_dir = "data/output"


        os.makedirs(
            output_dir,
            exist_ok=True
        )


        output_path = (
            f"{output_dir}/"
            f"{course_name}_{session}_分析报告.xlsx"
        )



        data = {}



        # =====================================================
        # 1. 获取标准化长表
        # =====================================================

        normalized_long = context.get(
            "normalized_long",
            []
        )


        if isinstance(
            normalized_long,
            pd.DataFrame
        ):

            df_long = normalized_long


        elif normalized_long:


            df_long = pd.DataFrame(
                normalized_long
            )


        else:


            df_long = context.get(
                "df_long",
                pd.DataFrame()
            )


            if not isinstance(
                df_long,
                pd.DataFrame
            ):

                df_long = pd.DataFrame()



        data["normalized_long"] = df_long



        # =====================================================
        # 2. 数据总览
        # =====================================================


        # 学员数量

        if (
            not df_long.empty
            and
            "学员编号" in df_long.columns
        ):

            student_count = (
                df_long["学员编号"]
                .nunique()
            )

        else:

            student_count = 0



        # 评分数据

        if (
            not df_long.empty
            and
            "question_type" in df_long.columns
        ):

            rating_df = df_long[
                df_long["question_type"]
                ==
                "rating"
            ]

        else:

            rating_df = pd.DataFrame()



        # 评分总数量

        rating_total = len(
            rating_df
        )



        # 有效评分数量

        if not rating_df.empty:

            valid_rating_count = (
                rating_df[
                    "response_value"
                ]
                .notna()
                .sum()
            )

        else:

            valid_rating_count = 0



        # feedback数量

        feedback_results = context.get(
            "feedback_results",
            []
        )


        feedback_count = sum(
            len(
                item.get(
                    "items",
                    []
                )
            )

            for item in feedback_results
        )



        # anomaly数量

        anomalies = context.get(
            "anomalies",
            []
        )


        if isinstance(
            anomalies,
            pd.DataFrame
        ):

            anomaly_count = len(
                anomalies
            )


        else:

            anomaly_count = len(
                anomalies
            )



        data["overview"] = pd.DataFrame(
            [
                {

                    "课程名称":
                        course_name,


                    "期次":
                        session,


                    "student_count":
                        student_count,


                    "rating_total":
                        rating_total,


                    "valid_rating_count":
                        valid_rating_count,


                    "feedback_count":
                        feedback_count,


                    "anomaly_count":
                        anomaly_count

                }
            ]
        )



        # =====================================================
        # 3. AI反馈明细
        # =====================================================


        feedback_rows = []


        for item in feedback_results:


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



        # =====================================================
        # 4. 异常数据
        # =====================================================


        if isinstance(
            anomalies,
            pd.DataFrame
        ):

            data["anomalies"] = anomalies


        else:

            data["anomalies"] = pd.DataFrame(
                anomalies
            )



        # =====================================================
        # 5. 其他预留Sheet
        # =====================================================


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



        # =====================================================
        # 6. 输出Excel
        # =====================================================


        write_output_excel(
            output_path,
            data
        )



        return {

            "report_path":
                output_path

        }