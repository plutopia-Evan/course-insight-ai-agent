"""Keep data-, credential-, and server-dependent scripts out of local unit tests.

These files are manual smoke scripts, even though their historical names start
with ``test_``. They remain available for explicit execution.
"""

collect_ignore = [
    "test_ai_feedback.py",
    "test_ai_feedback_statistics.py",
    "test_ai_pipeline.py",
    "test_ai_summary_generator.py",
    "test_api.py",
    "test_batch_deepseek_feedback.py",
    "test_deepseek_feedback.py",
    "test_llm_feedback.py",
    "test_pipeline.py",
    "test_streamlit.py",
]
