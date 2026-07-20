"""
文本反馈清洗模块

功能:
- 删除纯空白反馈
- 标记低信息量反馈（无、没有、暂无、无建议、挺好、很好等）
- 统计完全重复的反馈及其出现次数
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


LOW_INFO_PATTERNS = [
    r"^[\s]*[无沒]$",
    r"^[\s]*没有[\.。\s]*$",
    r"^[\s]*沒有[\.。\s]*$",
    r"^[\s]*暂无[\.。\s]*$",
    r"^[\s]*暫無[\.。\s]*$",
    r"^[\s]*无建议[\.。\s]*$",
    r"^[\s]*無建議[\.。\s]*$",
    r"^[\s]*无意见[\.。\s]*$",
    r"^[\s]*無意見[\.。\s]*$",
    r"^[\s]*暂无建议[\.。\s]*$",
    r"^[\s]*暫無建議[\.。\s]*$",
    r"^[\s]*暂[时時]没有[\.。\s]*$",
    r"^[\s]*暂[时時]沒有[\.。\s]*$",
    r"^[\s]*没什么[\.。\s]*$",
    r"^[\s]*沒什麼[\.。\s]*$",
    r"^[\s]*没啥[\.。\s]*$",
    r"^[\s]*沒啥[\.。\s]*$",
    r"^[\s]*没想法[\.。\s]*$",
    r"^[\s]*沒想法[\.。\s]*$",
    r"^[\s]*不知道[\.。\s]*$",
    r"^[\s]*不清楚[\.。\s]*$",
    r"^[\s]*没有想法[\.。\s]*$",
    r"^[\s]*沒有想法[\.。\s]*$",
    r"^[\s]*没啥意见[\.。\s]*$",
    r"^[\s]*沒啥意見[\.。\s]*$",
    r"^[\s]*没有意见[\.。\s]*$",
    r"^[\s]*沒有意見[\.。\s]*$",
    r"^[\s]*没有什么建议[\.。\s]*$",
    r"^[\s]*沒有什麼建議[\.。\s]*$",
    r"^[\s]*没有建议[\.。\s]*$",
    r"^[\s]*沒有建議[\.。\s]*$",
    r"^[\s]*没问题[\.。\s]*$",
    r"^[\s]*沒問題[\.。\s]*$",
    r"^[\s]*非常好[\.。\s]*$",
    r"^[\s]*很好[\.。\!！\s]*$",
    r"^[\s]*挺好的[\.。\s]*$",
    r"^[\s]*挺好[\.。\!！\s]*$",
    r"^[\s]*不错[\.。\!！\s]*$",
    r"^[\s]*不錯[\.。\!！\s]*$",
    r"^[\s]*满意[\.。\s]*$",
    r"^[\s]*滿意[\.。\s]*$",
    r"^[\s]*还行[\.。\s]*$",
    r"^[\s]*還行[\.。\s]*$",
    r"^[\s]*还好[\.。\s]*$",
    r"^[\s]*還好[\.。\s]*$",
    r"^[\s]*可以[\.。\s]*$",
    r"^[\s]*挺好的呀[\.。\s]*$",
    r"^[\s]*棒[\.。\!！\s]*$",
    r"^[\s]*赞[\.。\!！\s]*$",
    r"^[\s]*讚[\.。\!！\s]*$",
    r"^[\s]*好评[\.。\!！\s]*$",
    r"^[\s]*好評[\.。\!！\s]*$",
    r"^[\s]*还好吧[\.。\s]*$",
    r"^[\s]*還好吧[\.。\s]*$",
    r"^[\s]*一般[\.。\s]*$",
    r"^[\s]*一般般[\.。\s]*$",
    r"^[\s]*没啥建议[\.。\s]*$",
    r"^[\s]*沒啥建議[\.。\s]*$",
    r"^[\s]*继续加油[\.。\!！\s]*$",
    r"^[\s]*繼續加油[\.。\!！\s]*$",
    r"^[\s]*保持[\.。\s]*$",
    r"^[\s]*good[\.。\s]*$",
    r"^[\s]*nice[\.。\s]*$",
    r"^[\s]*ok[\.。\s]*$",
    r"^[\s]*好$",
    r"^[\s]+$",
]

LOW_INFO_LABEL = "低信息量反馈"
WHITESPACE_LABEL = "纯空白反馈"
VALID_FEEDBACK_LABEL = "有效反馈"


def is_low_info(text: str) -> bool:
    """判断单条文本反馈是否为低信息量。

    Args:
        text: 文本反馈内容

    Returns:
        True 如果文本匹配低信息量模式
    """
    if not isinstance(text, str):
        return False
    cleaned = text.strip()
    if cleaned == "":
        return False
    for pattern in LOW_INFO_PATTERNS:
        if re.match(pattern, cleaned):
            return True
    return False


def clean_text_feedback(text_df: pd.DataFrame) -> pd.DataFrame:
    """清洗文本反馈数据。

    处理步骤:
    1. 筛选非空反馈
    2. 标记低信息量反馈
    3. 统计完全重复反馈的出现次数
    4. 生成清洗标记

    Args:
        text_df: 文本反馈 DataFrame，需含 response_value 列

    Returns:
        清洗后的文本反馈 DataFrame，新增列:
        - feedback_clean: 清洗后的文本
        - feedback_label: 标记类型
        - duplicate_count: 重复出现次数（仅在原始记录中保留）
        - is_representative: 是否为重复组的代表行
    """
    if text_df.empty:
        logger.info("文本反馈数据为空，跳过清洗")
        return text_df

    df = text_df.copy()

    df["feedback_clean"] = df["response_value"].apply(
        lambda v: str(v).strip() if isinstance(v, str) else ("" if pd.isna(v) else str(v).strip())
    )

    def _classify(text: str, clean: str) -> str:
        if not isinstance(text, str) and pd.isna(text):
            return WHITESPACE_LABEL
        if clean == "":
            return WHITESPACE_LABEL
        if is_low_info(clean):
            return LOW_INFO_LABEL
        return VALID_FEEDBACK_LABEL

    df["feedback_label"] = df.apply(lambda row: _classify(row["response_value"], row["feedback_clean"]), axis=1)

    valid_feedback = df[df["feedback_label"] == VALID_FEEDBACK_LABEL].copy()
    if len(valid_feedback) > 0:
        dup_counts = valid_feedback.groupby("feedback_clean").size().reset_index(name="duplicate_count")
        dup_counts = dup_counts[dup_counts["duplicate_count"] > 1]
        dup_feedbacks = set(dup_counts["feedback_clean"].tolist())

        dup_map = dict(zip(dup_counts["feedback_clean"], dup_counts["duplicate_count"]))

        def _get_dup_count(clean_text: str, label: str) -> int:
            if label != VALID_FEEDBACK_LABEL:
                return 1
            return dup_map.get(clean_text, 1)

        df["duplicate_count"] = df.apply(
            lambda row: _get_dup_count(row["feedback_clean"], row["feedback_label"]), axis=1
        )

        seen = set()
        is_rep_list = []
        for _, row in df.iterrows():
            if row["feedback_label"] == VALID_FEEDBACK_LABEL and row["feedback_clean"] in dup_feedbacks:
                if row["feedback_clean"] not in seen:
                    seen.add(row["feedback_clean"])
                    is_rep_list.append(True)
                else:
                    is_rep_list.append(False)
            else:
                is_rep_list.append(True)
        df["is_representative"] = is_rep_list
    else:
        df["duplicate_count"] = 1
        df["is_representative"] = True

    blank_count = (df["feedback_label"] == WHITESPACE_LABEL).sum()
    low_info_count = (df["feedback_label"] == LOW_INFO_LABEL).sum()
    valid_count = (df["feedback_label"] == VALID_FEEDBACK_LABEL).sum()
    dup_groups = df[df["duplicate_count"] > 1]["feedback_clean"].nunique()

    logger.info("文本反馈清洗完成: 纯空白 %d, 低信息量 %d, 有效 %d, 重复组 %d",
                blank_count, low_info_count, valid_count, dup_groups)

    return df


def generate_feedback_summary(cleaned_feedback: pd.DataFrame) -> pd.DataFrame:
    """生成文本反馈汇总表。

    包含:
    - 所有非空白反馈
    - 按有效/低信息量分组
    - 重复标记

    Args:
        cleaned_feedback: 清洗后的反馈 DataFrame

    Returns:
        汇总 DataFrame
    """
    if cleaned_feedback.empty:
        return pd.DataFrame()

    df = cleaned_feedback.copy()

    non_blank = df[df["feedback_label"] != WHITESPACE_LABEL].copy()

    cols = ["学员编号", "course_name", "session", "standard_question",
            "feedback_clean", "feedback_label", "duplicate_count"]
    available_cols = [c for c in cols if c in non_blank.columns]
    result = non_blank[available_cols].copy()
    result.rename(columns={"feedback_clean": "反馈内容", "feedback_label": "标记类型"}, inplace=True)

    result = result.sort_values(["course_name", "session", "标记类型"])

    logger.info("反馈汇总生成完成，共 %d 条记录", len(result))
    return result
