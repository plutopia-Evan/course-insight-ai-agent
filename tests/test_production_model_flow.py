"""The default survey pipeline reaches the production DeepSeek analyzer."""

import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from agent.orchestrator import CourseInsightAgent
from llm import deepseek_feedback_analyzer as analyzer


def test_default_agent_uses_one_model_response_per_substantive_feedback(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "config"
    prompt_dir = tmp_path / "prompts"
    config_dir.mkdir()
    prompt_dir.mkdir()
    shutil.copyfile(root / "config/question_mapping.xlsx", config_dir / "question_mapping.xlsx")
    shutil.copyfile(root / "config/feedback_taxonomy.yaml", config_dir / "feedback_taxonomy.yaml")
    shutil.copyfile(
        root / "prompts/feedback_classification_prompt.md",
        prompt_dir / "feedback_classification_prompt.md",
    )
    mapping = pd.read_excel(config_dir / "question_mapping.xlsx")
    rating_question = mapping.loc[mapping.question_type == "rating", "original_question"].iloc[0]
    text_question = mapping.loc[mapping.question_type == "text", "original_question"].iloc[0]
    survey_path = tmp_path / "验收课程_第01期.xlsx"
    pd.DataFrame({
        "学员编号": ["S1", "S2", "S3"],
        rating_question: [5, 4, 3],
        text_question: ["老师讲解清晰", "课程节奏太快", "无"],
    }).to_excel(survey_path, index=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    previous_config = sys.modules.pop("deepseek_config", None)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        user_prompt = kwargs["messages"][1]["content"]
        feedback_id = re.search(r"feedback_id: (\d+)", user_prompt).group(1)
        if "讲解清晰" in user_prompt:
            label = ("讲师表现", "讲解清晰", "positive", "讲解清晰")
        else:
            label = ("课程节奏", "节奏过快", "negative", "节奏太快")
        category, subcategory, sentiment, evidence = label
        body = {
            "feedback_id": feedback_id,
            "items": [{
                "category": category,
                "subcategory": subcategory,
                "sentiment": sentiment,
                "summary": "课程反馈",
                "evidence": evidence,
            }],
        }
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(body, ensure_ascii=False))
        )])

    monkeypatch.setattr(
        analyzer,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )),
    )
    try:
        result = CourseInsightAgent().run(str(survey_path))
    finally:
        sys.modules.pop("deepseek_config", None)
        if previous_config is not None:
            sys.modules["deepseek_config"] = previous_config

    assert result["analysis_status"] == "complete"
    assert result["feedback_response_count"] == 3
    assert result["feedback_skipped_count"] == 1
    assert result["feedback_item_count"] == 2
    assert result["feedback_failed_count"] == 0
    assert [item["items"][0]["sentiment"] for item in result["feedback_results"]] == [
        "positive", "negative"
    ]
    assert len(calls) == 2
    assert all(call["model"] == "deepseek-chat" for call in calls)
    assert all(call["response_format"] == {"type": "json_object"} for call in calls)
    assert len(pd.read_excel(result["report_path"], sheet_name="开放式反馈明细")) == 2
