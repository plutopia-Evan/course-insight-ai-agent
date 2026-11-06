"""One source of truth for the counts exposed by APIs and reports."""

def build_analysis_summary(
    df_long, valid_ratings, anomalies, feedback_results, feedback_errors, skipped_count
):
    rating_total = int((df_long["question_type"] == "rating").sum())
    feedback_response_count = int((df_long["question_type"] == "text").sum())
    feedback_item_count = sum(len(result.get("items", [])) for result in feedback_results)
    failure_count = len(feedback_errors)
    unknown_questions = int(df_long.loc[df_long["question_type"] == "unknown", "original_question"].nunique()) if "original_question" in df_long else 0
    eligible = feedback_response_count - skipped_count
    classified_people = len({str(result["respondent_id"]) for result in feedback_results
                             if result.get("items") and not result.get("error") and result.get("respondent_id")})

    return {
        "analysis_status": "partial" if failure_count or unknown_questions else "complete",
        "data_quality_status": "needs_review" if unknown_questions or len(anomalies) else "ok",
        "unknown_question_count": unknown_questions,
        "classified_feedback_people": classified_people,
        "feedback_eligible_count": eligible,
        "feedback_analyzed_rate": (len(feedback_results) - failure_count) / eligible if eligible else None,
        "feedback_skipped_rate": skipped_count / feedback_response_count if feedback_response_count else None,
        "student_count": int(df_long["学员编号"].nunique()),
        "rating_total": rating_total,
        "valid_rating_count": int(len(valid_ratings)),
        "feedback_response_count": feedback_response_count,
        "feedback_item_count": int(feedback_item_count),
        # Keep the existing API field; it counts extracted opinions, not responses.
        "feedback_count": int(feedback_item_count),
        "feedback_analyzed_count": len(feedback_results) - failure_count,
        "feedback_failed_count": failure_count,
        "feedback_skipped_count": skipped_count,
        "anomaly_count": int(len(anomalies)),
    }
