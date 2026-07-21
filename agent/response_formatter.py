def format_agent_response(result):


    return {


        "status":
            "success",


        "course":{

            "name":
                result.get(
                    "course_name",
                    ""
                ),

            "session":
                result.get(
                    "session",
                    ""
                )

        },


        "summary":{

            "students":
                result.get(
                    "student_count",
                    0
                ),

            "ratings":
                result.get(
                    "rating_total",
                    0
                ),

            "valid_ratings":
                result.get(
                    "valid_rating_count",
                    0
                ),

            "feedbacks":
                result.get(
                    "feedback_count",
                    0
                ),

            "anomalies":
                result.get(
                    "anomaly_count",
                    0
                )

        },


        "analysis":{


            "rating_data":
                result.get(
                    "valid_rating",
                    []
                ),


            "feedback_analysis":
                result.get(
                    "feedback_results",
                    []
                ),


            "anomalies":
                result.get(
                    "anomalies",
                    []
                )


        }

    }