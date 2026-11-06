import pandas as pd
import pytest

from core.input_validation import SurveyInputError, validate_mapping
from core.survey_processor import detect_question_column_indices, map_questions, read_survey_file


def mapping():
    return pd.DataFrame([
        {"original_question": "课程", "standard_question": "内容", "question_type": "rating", "max_score": 5, "category": "common"},
        {"original_question": "难度", "standard_question": "难度", "question_type": "rating", "max_score": 5, "category": "common"},
    ])


def test_ambiguous_contains_match_is_visible_not_first_row():
    result = map_questions(pd.DataFrame({"original_question": ["课程难度如何", "课程", "新题目"]}), mapping())
    assert result.mapping_status.tolist() == ["ambiguous", "exact", "unmapped"]
    assert result.question_type.tolist() == ["unknown", "rating", "unknown"]
    assert result.iloc[0].mapping_candidates == "内容 | 难度"


def test_time_question_is_not_misidentified_as_submission_time():
    assert detect_question_column_indices(["学员编号", "上课时间合理性", "课程反馈"]) == (0, None, [1, 2])
    with pytest.raises(SurveyInputError, match="唯一"):
        detect_question_column_indices(["课程反馈", "评分"])


@pytest.mark.parametrize("score", [0, -1, 2.5, "bad"])
def test_invalid_scale_is_rejected(score):
    frame = mapping().astype({"max_score": object})
    frame.loc[0, "max_score"] = score
    with pytest.raises(SurveyInputError, match="正整数"):
        validate_mapping(frame)


def test_duplicate_mapping_is_rejected():
    with pytest.raises(SurveyInputError, match="重复"):
        validate_mapping(pd.concat([mapping(), mapping()]))


@pytest.mark.parametrize("ids", [["S1", "S1"], ["S1", None]])
def test_missing_or_duplicate_respondent_needs_confirmation(tmp_path, ids):
    path = tmp_path / "课程_第01期.xlsx"
    pd.DataFrame({"学员编号": ids, "课程反馈": ["a", "b"]}).to_excel(path, index=False)
    with pytest.raises(SurveyInputError):
        read_survey_file(str(path))


def test_textual_ids_keep_leading_zeroes(tmp_path):
    path = tmp_path / "课程_第01期.xlsx"
    pd.DataFrame({"学员编号": ["001", "1"], "课程反馈": ["a", "b"]}).to_excel(path, index=False)
    _, _, frame, _, _ = read_survey_file(str(path))
    assert frame["学员编号"].tolist() == ["001", "1"]
