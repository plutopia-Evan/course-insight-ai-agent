from types import SimpleNamespace
import pytest
from llm.usage import capture_usage, observed_completion


def client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_usage_is_local_and_missing_price_is_not_zero(monkeypatch):
    monkeypatch.delenv("MODEL_INPUT_USD_PER_MILLION", raising=False)
    call = client(lambda **_: SimpleNamespace(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3)))
    with capture_usage() as first:
        observed_completion(call, stage="classification", model="test", messages=["private text"])
        with capture_usage() as second:
            observed_completion(call, stage="summary", model="test")
    assert len(first) == len(second) == 1
    assert first[0]["input_tokens"] == 12
    assert first[0]["estimated_usd"] is None
    assert "private text" not in str(first)


def test_usage_records_failed_attempt_without_error_details():
    def fail(**_):
        raise RuntimeError("private model response")
    with capture_usage() as events:
        with pytest.raises(RuntimeError):
            observed_completion(client(fail), stage="classification", model="test")
    assert events[0]["success"] is False
    assert events[0]["error_type"] == "RuntimeError"
    assert "private model response" not in str(events)
