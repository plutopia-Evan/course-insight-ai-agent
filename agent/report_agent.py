"""Create the Excel report from the same data returned by the API."""

import pandas as pd

from core.output_writer import write_output_excel
from core.report_storage import new_report_path


FEEDBACK_COLUMNS = [
    "feedback_id", "course_name", "session", "respondent_id",
    "category", "subcategory", "sentiment", "summary", "evidence",
]


class ReportAgent:
    def run(self, context):
        output_path = new_report_path(context["course_name"], context["session"])

        overview = {
            "课程名称": context["course_name"],
            "期次": context["session"],
            **context["summary"],
        }
        feedback_rows = []
        for result in context["feedback_results"]:
            for item in result.get("items", []):
                feedback_rows.append({
                    "feedback_id": result.get("feedback_id", ""),
                    "course_name": result.get("course_name", context["course_name"]),
                    "session": result.get("session", context["session"]),
                    "respondent_id": result.get("respondent_id", ""),
                    **{key: item.get(key, "") for key in (
                        "category", "subcategory", "sentiment", "summary", "evidence"
                    )},
                })

        data = {
            "overview": pd.DataFrame([overview]),
            "normalized_long": context["df_long"],
            "session_stats": context["session_stats"],
            "feedback_detail": pd.DataFrame(feedback_rows, columns=FEEDBACK_COLUMNS),
            "anomalies": context["anomalies"],
        }
        if context["feedback_errors"]:
            data["feedback_errors"] = pd.DataFrame(context["feedback_errors"])
        write_output_excel(str(output_path), data, include_empty_sheets=False)
        return {"report_path": str(output_path)}
