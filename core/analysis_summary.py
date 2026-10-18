"""One source of truth for the counts exposed by APIs and reports."""

def build_analysis_summary(
    df_long, valid_ratings, anomalies, feedback_results, feedback_errors, skipped_count
):
    rating_total = int((df_long["question_type"] == "rating").sum())
    feedback_response_count = int((df_long["question_type"] == "text").sum())
    feedback_item_count = sum(len(result.get("items", [])) for result in feedback_results)
    failure_count = len(feedback_errors)

    return {
        "analysis_status": "partial" if failure_count else "complete",
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
