import pytest
from pathlib import Path

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_operator_can_run_example_without_mapping_or_model(monkeypatch):
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.delenv(key, raising=False)
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not page.exception
    next(box for box in page.checkbox if box.label == "使用合成示例数据体验").check().run()
    next(button for button in page.button if button.label == "🚀 生成课程复盘").click().run()
    assert not page.exception
    assert page.session_state["results"]["total_course_sessions"] == 2
    assert page.session_state["xlsx_bytes"]
    assert not page.session_state["ai_analysis_done"]
    next(box for box in page.checkbox if box.label == "使用合成示例数据体验").uncheck().run()
    assert not page.exception
    assert page.session_state["results"] is None
