"""
Excel 输出模块

功能:
- 生成 course_survey_analysis.xlsx
- 包含12个工作表：数据总览、文件识别结果、标准化长表、题目映射结果、
  题目覆盖情况、全局公共题统计、课程公共题统计、单期特有题统计、
  期次评分统计、开放式反馈、异常数据、人工待确认
"""

import logging
import os
from typing import Dict, List

import pandas as pd
from openpyxl import Workbook

from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


HEADER_FONT = Font(name="微软雅黑", bold=True, size=11)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT_WHITE = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
TITLE_FONT = Font(name="微软雅黑", bold=True, size=14)
TITLE_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
WARNING_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
ANOMALY_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
LOW_INFO_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")


def _auto_width(ws, min_width: int = 8, max_width: int = 50):
    """自动调整列宽。"""
    for col_idx in range(1, ws.max_column + 1):
        max_len = min_width
        col_letter = get_column_letter(col_idx)
        for row_idx in range(1, min(ws.max_row + 1, 200)):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is not None:
                cell_len = len(str(cell.value))
                if cell_len > max_len:
                    max_len = cell_len
        ws.column_dimensions[col_letter].width = min(max_len + 4, max_width)


def _style_header_row(ws, row_num: int, col_count: int):
    """设置表头行样式。"""
    for col_idx in range(1, col_count + 1):
        cell = ws.cell(row=row_num, column=col_idx)
        cell.font = HEADER_FONT_WHITE
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _style_data_rows(ws, start_row: int, end_row: int, col_count: int):
    """设置数据行样式。"""
    for row_idx in range(start_row, end_row + 1):
        for col_idx in range(1, col_count + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def _write_df_to_sheet(ws, df: pd.DataFrame, start_row: int = 1, apply_style: bool = True):
    """将 DataFrame 写入工作表，并设置样式。"""
    if df is None or df.empty:
        ws.cell(row=start_row, column=1, value="暂无数据")
        return

    import numpy as np

    df = df.copy()
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        if dtype_str in ("Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
                          "Float32", "Float64", "boolean"):
            df[col] = df[col].astype(object)
    df = df.replace({pd.NA: "", np.nan: "", pd.NaT: ""})
    df = df.fillna("")

    for row_idx, row_data in enumerate(dataframe_to_rows(df, index=False, header=True), start=start_row):
        for col_idx, value in enumerate(row_data, 1):
            if value is None:
                value = ""
            elif isinstance(value, float) and np.isnan(value):
                value = ""
            ws.cell(row=row_idx, column=col_idx, value=value)

    if apply_style:
        _style_header_row(ws, start_row, len(df.columns))
        _style_data_rows(ws, start_row + 1, start_row + len(df), len(df.columns))
        _auto_width(ws)


def write_output_excel(output_path: str, data: Dict, include_empty_sheets: bool = True):
    """生成最终的 course_survey_analysis.xlsx 文件。

    Args:
        output_path: 输出文件路径
        data: 包含所有数据的字典，键名如下:
            - overview: 数据总览 DataFrame
            - file_identification: 文件识别结果 DataFrame
            - normalized_long: 标准化长表 DataFrame
            - question_mapping_result: 题目映射结果 DataFrame
            - question_coverage: 题目覆盖情况 DataFrame
            - global_common_stats: 全局公共题统计 DataFrame
            - course_common_stats: 课程公共题统计 DataFrame
            - period_specific_stats: 单期特有题统计 DataFrame
            - session_stats: 期次评分统计 DataFrame
            - feedback_summary: 开放式反馈汇总 DataFrame
            - anomalies: 异常数据 DataFrame
            - pending_review: 人工待确认 DataFrame
    """
    logger.info("开始生成输出文件: %s", output_path)

    wb = Workbook()
    wb.remove(wb.active)

    sheet_configs = [
        ("数据总览", "overview"),
        ("文件识别结果", "file_identification"),
        ("标准化长表", "normalized_long"),
        ("题目映射结果", "question_mapping_result"),
        ("原始题目映射明细", "question_coverage"),
        ("题目覆盖情况（自动）", "auto_coverage"),
        ("全局公共题统计", "global_common_stats"),
        ("课程公共题统计", "course_common_stats"),
        ("单期特有题统计", "period_specific_stats"),
        ("期次评分统计", "session_stats"),
        ("开放式反馈", "feedback_summary"),
        ("反馈频次汇总", "feedback_frequency"),
        ("开放式反馈明细", "feedback_detail"),
        ("AI分析错误", "feedback_errors"),
        ("异常数据", "anomalies"),
        ("人工待确认", "pending_review"),
    ]

    for sheet_name, data_key in sheet_configs:
        if not include_empty_sheets and data_key not in data:
            continue
        logger.debug("写入工作表: %s", sheet_name)
        ws = wb.create_sheet(title=sheet_name)
        df = data.get(data_key)
        _write_df_to_sheet(ws, df, start_row=1)

        if sheet_name == "异常数据" and df is not None and not df.empty:
            for row_idx in range(2, 2 + len(df)):
                for col_idx in range(1, len(df.columns) + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = ANOMALY_FILL

        if sheet_name == "开放式反馈" and df is not None and not df.empty:
            label_col = None
            for col_idx in range(1, len(df.columns) + 1):
                if ws.cell(row=1, column=col_idx).value == "标记类型":
                    label_col = col_idx
                    break
            if label_col:
                for row_idx in range(2, 2 + len(df)):
                    cell = ws.cell(row=row_idx, column=label_col)
                    if cell.value == "低信息量反馈":
                        cell.fill = LOW_INFO_FILL

    wb.save(output_path)
    logger.info("输出文件已保存: %s", output_path)


def build_file_identification(file_list: List[str], course_sessions: List[tuple]) -> pd.DataFrame:
    """生成文件识别结果表。

    Args:
        file_list: 输入文件路径列表
        course_sessions: 每个文件解析出的 (course_name, session, row_count, question_count) 列表

    Returns:
        文件识别结果 DataFrame
    """
    records = []
    for fpath, (course_name, session, row_count, q_count) in zip(file_list, course_sessions):
        records.append({
            "文件名": os.path.basename(fpath),
            "课程名称": course_name,
            "期次": session,
            "数据行数": row_count,
            "题目列数": q_count,
            "文件路径": fpath,
        })
    result = pd.DataFrame(records)
    logger.info("文件识别结果: %d 个文件", len(result))
    return result


def build_pending_review(df_all_long: pd.DataFrame,
                         anomalies: pd.DataFrame,
                         filename_issues: List[dict] = None,
                         auto_coverage_df: pd.DataFrame = None) -> pd.DataFrame:
    """生成人工待确认列表。

    包含:
    - 未映射题目（question_type == "unknown"）
    - 文件名解析失败
    - 未知题目类型
    - 配置与自动分类不一致的题目
    - 需要人工判断的异常记录（来自 anomalies，排除缺失）

    Args:
        df_all_long: 全部长表数据
        anomalies: 异常数据 DataFrame
        filename_issues: 文件名解析问题列表 [{"文件名": ..., "原因": ...}]
        auto_coverage_df: 自动覆盖分析 DataFrame（含配置与自动是否一致列）

    Returns:
        人工待确认 DataFrame
    """
    review_records = []

    unknown_mask = df_all_long["question_type"] == "unknown"
    if unknown_mask.any():
        unknown_df = df_all_long[unknown_mask][["学员编号", "course_name", "session", "original_question", "response_value"]].drop_duplicates()
        for _, row in unknown_df.iterrows():
            review_records.append({
                "来源": "未映射题目",
                "课程名称": row.get("course_name", ""),
                "期次": row.get("session", ""),
                "学员编号": row.get("学员编号", ""),
                "原始题目": row.get("original_question", ""),
                "待确认原因": f"题目 '{row.get('original_question', '')}' 未在 question_mapping.xlsx 中找到映射",
            })

    if anomalies is not None and not anomalies.empty:
        for _, row in anomalies.iterrows():
            reason = row.get("anomaly_reason", "")
            if "缺失" in str(reason):
                continue
            review_records.append({
                "来源": "异常数据",
                "课程名称": row.get("course_name", ""),
                "期次": row.get("session", ""),
                "学员编号": row.get("学员编号", ""),
                "原始题目": row.get("original_question", ""),
                "待确认原因": f"异常评分: {reason}，原值={row.get('response_value', '')}",
            })

    if filename_issues:
        for issue in filename_issues:
            review_records.append({
                "来源": "文件解析",
                "课程名称": "",
                "期次": "",
                "学员编号": "",
                "原始题目": "",
                "待确认原因": f"文件 '{issue['文件名']}': {issue['原因']}",
            })

    if auto_coverage_df is not None and not auto_coverage_df.empty:
        inconsistent = auto_coverage_df[auto_coverage_df["配置与自动是否一致"] == "否"]
        for _, row in inconsistent.iterrows():
            review_records.append({
                "来源": "分类不一致",
                "课程名称": "",
                "期次": "",
                "学员编号": "",
                "原始题目": row.get("standard_question", ""),
                "待确认原因": f"题目 '{row.get('standard_question', '')}' 配置category={row.get('配置category', '')}，自动分类={row.get('自动分类', '')}",
            })

    if len(review_records) == 0:
        logger.info("无人工待确认项")
        return pd.DataFrame(columns=["来源", "课程名称", "期次", "学员编号", "原始题目", "待确认原因"])

    result = pd.DataFrame(review_records)
    logger.info("人工待确认: %d 条", len(result))
    return result


def build_feedback_frequency(cleaned_feedback: pd.DataFrame) -> pd.DataFrame:
    """生成反馈频次汇总表。

    按课程、期次、清洗后反馈文本统计出现次数。
    仅统计有效反馈（排除空白和低信息量）。

    Args:
        cleaned_feedback: 清洗后的反馈 DataFrame

    Returns:
        反馈频次汇总 DataFrame
    """
    if cleaned_feedback.empty:
        return pd.DataFrame(columns=["课程名称", "期次", "反馈内容", "出现次数"])

    df = cleaned_feedback.copy()

    valid = df[df["feedback_label"] == "有效反馈"]
    if valid.empty:
        logger.info("无有效反馈，反馈频次为空")
        return pd.DataFrame(columns=["课程名称", "期次", "反馈内容", "出现次数"])

    freq = valid.groupby(["course_name", "session", "feedback_clean"]).size().reset_index(name="出现次数")
    freq = freq.sort_values(["course_name", "session", "出现次数"], ascending=[True, True, False])

    freq.rename(columns={
        "course_name": "课程名称",
        "session": "期次",
        "feedback_clean": "反馈内容",
    }, inplace=True)

    logger.info("反馈频次汇总: %d 条唯一反馈", len(freq))
    return freq
