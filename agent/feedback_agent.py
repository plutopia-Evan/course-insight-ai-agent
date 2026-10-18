"""Analyze substantive text feedback and retain failures for review."""

import pandas as pd

from core.text_cleaner import is_low_info
from llm.deepseek_feedback_analyzer import deepseek_analyze_feedback


class FeedbackLimitExceeded(ValueError):
    """A survey exceeds the API's per-request model budget."""


class FeedbackAgent:
    def __init__(self, analyze_feedback=None):
        # Tests can explicitly inject a deterministic analyzer; production uses DeepSeek.
        self.analyze_feedback = analyze_feedback or deepseek_analyze_feedback

    def run(self, survey_result, *, max_feedback_count=None, max_feedback_chars=None):
        df_long = survey_result["df_long"]
        text_df = df_long[df_long["question_type"] == "text"]
        course_name = survey_result.get("course_name", "")
        session = survey_result.get("session", "")

        # Reject the entire request before making any billable model calls.
        if max_feedback_count is not None or max_feedback_chars is not None:
            analyzable_count = 0
            for _, row in text_df.iterrows():
                value = row.get("response_value")
                text = "" if pd.isna(value) else str(value).strip()
                if not text or is_low_info(text):
                    continue
                analyzable_count += 1
                if max_feedback_chars is not None and len(text) > max_feedback_chars:
                    raise FeedbackLimitExceeded(
                        f"单条有效反馈不能超过 {max_feedback_chars} 字符"
                    )
                if max_feedback_count is not None and analyzable_count > max_feedback_count:
                    raise FeedbackLimitExceeded(
                        f"单次问卷不能超过 {max_feedback_count} 条有效反馈"
                    )

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
