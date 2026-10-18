"""Analyze substantive text feedback and retain failures for review."""

import pandas as pd

from core.text_cleaner import is_low_info
from llm.deepseek_feedback_analyzer import deepseek_analyze_feedback


class FeedbackAgent:
    def __init__(self, analyze_feedback=None):
        # Tests can explicitly inject a deterministic analyzer; production uses DeepSeek.
        self.analyze_feedback = analyze_feedback or deepseek_analyze_feedback

    def run(self, survey_result):
        df_long = survey_result["df_long"]
        text_df = df_long[df_long["question_type"] == "text"]
        course_name = survey_result.get("course_name", "")
        session = survey_result.get("session", "")

        results = []
        errors = []
        skipped = 0
        for idx, row in text_df.iterrows():
            value = row.get("response_value")
            text = "" if pd.isna(value) else str(value).strip()
            if not text or is_low_info(text):
                skipped += 1
                continue

            feedback_id = str(idx)
            respondent_id = str(row.get("学员编号", ""))
            try:
                result = self.analyze_feedback(
                    feedback_id=feedback_id,
                    feedback_text=text,
                    course_name=course_name,
                    session=session,
                    respondent_id=respondent_id,
                )
            except Exception as exc:
                result = {"items": [], "_error": str(exc)}

            normalized = {
                "feedback_id": feedback_id,
                "course_name": course_name,
                "session": session,
                "respondent_id": respondent_id,
                "items": result.get("items", []),
            }
            error = result.get("_error") or ("分类结果为空" if not normalized["items"] else None)
            if error:
                normalized["error"] = error
                errors.append({
                    "feedback_id": feedback_id,
                    "respondent_id": respondent_id,
                    "feedback_text": text,
                    "error": error,
                })
            results.append(normalized)

        return {
            "feedback_results": results,
            "feedback_errors": errors,
            "feedback_skipped_count": skipped,
        }
