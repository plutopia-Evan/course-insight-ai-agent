class StatisticsAgent:


    def run(self, survey_result):


        from core.survey_processor import (
            detect_anomalies,
            get_valid_ratings,
            split_rating_and_text
        )


        from core.statistics import (
            compute_overview_stats,
            compute_session_stats
        )


        df_long = survey_result["df_long"]


        # 1.异常检测

        anomalies = detect_anomalies(
            df_long
        )


        # 2.有效评分

        valid_ratings = get_valid_ratings(
            df_long
        )


        # 3.拆分评分和文本

        rating_df, text_df = split_rating_and_text(
            df_long
        )


        # 4.总览统计

        overview = compute_overview_stats(
            valid_ratings,
            df_long,
            text_df,
            anomalies,
            [
                survey_result["file_path"]
            ]
        )


        # 5.期次统计

        session_stats = compute_session_stats(
            valid_ratings,
            df_long
        )


        return {


            "anomalies":
                anomalies,


            "valid_rating":
                valid_ratings,


            "overview":
                overview,


            "session_stats":
                session_stats

        }