"""
AI 反馈统计模块

功能:
- 从 deepseek_feedback_batch_result.xlsx 读取 AI 反馈分类明细
- 生成 5 个工作表: 标签统计 / 正向汇总 / 负向汇总 / 建议汇总 / 课程期次概览
- 数据校验与异常记录
- Excel 格式化（冻结首行、自动列宽、表头加粗、百分比格式、筛选）
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, numbers
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HEADER_FONT = Font(name="微软雅黑", bold=True, size=11)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT_WHITE = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
ANOMALY_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

VALID_SENTIMENTS = {"positive", "negative", "suggestion", "neutral"}

# ---------------------------------------------------------------------------
# 列名标准化
# ---------------------------------------------------------------------------

COLUMN_ALIASES = {
    "课程名称": "course_name",
    "course_name": "course_name",
    "期次": "session",
    "session": "session",
    "学员编号": "respondent_id",
    "respondent_id": "respondent_id",
}

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=COLUMN_ALIASES)
    return df

def _resolve_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def generate_statistics(
    input_path: str = "data/output/deepseek_feedback_batch_result.xlsx",
    output_path: str = "data/output/ai_feedback_statistics.xlsx",
) -> str:
    df_raw = pd.read_excel(input_path, sheet_name="AI反馈分类明细")
    df = _normalize_columns(df_raw)

    # 必需字段检查
    required = ["course_name", "session", "respondent_id", "category", "subcategory", "sentiment"]
    missing = [r for r in required if r not in df.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    # ---- 数据校验 ----
    normal = []
    anomalies = []

    for idx, row in df.iterrows():
        reasons = []
        if pd.isna(row.get("course_name")) or str(row["course_name"]).strip() == "":
            reasons.append("缺少课程名称")
        if pd.isna(row.get("session")) or str(row["session"]).strip() == "":
            reasons.append("缺少期次")
        if pd.isna(row.get("respondent_id")) or str(row["respondent_id"]).strip() == "":
            reasons.append("缺少学员编号")
        if pd.isna(row.get("category")) or str(row["category"]).strip() == "":
            reasons.append("缺少category")
        if pd.isna(row.get("subcategory")) or str(row["subcategory"]).strip() == "":
            reasons.append("缺少subcategory")
        sent = str(row.get("sentiment", "")).strip()
        if sent not in VALID_SENTIMENTS:
            reasons.append(f"非法sentiment: '{sent}'")

        if reasons:
            rec = row.to_dict()
            rec["异常原因"] = "; ".join(reasons)
            anomalies.append(rec)
        else:
            normal.append(row)

    df_clean = pd.DataFrame(normal)
    df_anomalies = pd.DataFrame(anomalies)

    print(f"数据校验: 正常 {len(df_clean)} 条, 异常 {len(df_anomalies)} 条")

    if len(df_clean) == 0:
        print("错误: 无有效数据")
        sys.exit(1)

    # 全局唯一学员数 per (课程, 期次)
    course_session_people = df_clean.groupby(["course_name", "session"])["respondent_id"].nunique().to_dict()

    # ---- AI标签统计 ----
    label_stats = _compute_label_stats(df_clean, course_session_people)
    print(f"AI标签统计: {len(label_stats)} 行")

    # ---- 正向/负向/建议汇总 ----
    positive_df = _compute_sentiment_summary(df_clean, "positive", course_session_people)
    negative_df = _compute_sentiment_summary(df_clean, "negative", course_session_people)
    suggestion_df = _compute_sentiment_summary(df_clean, "suggestion", course_session_people)

    # ---- 课程期次反馈概览 ----
    overview_df = _compute_course_session_overview(df_clean)

    # ---- 写入 Excel ----
    _write_excel(
        output_path=output_path,
        label_stats=label_stats,
        positive_df=positive_df,
        negative_df=negative_df,
        suggestion_df=suggestion_df,
        overview_df=overview_df,
        anomalies_df=df_anomalies,
    )

    print(f"统计完成: {os.path.abspath(output_path)}")
    return output_path


# ---------------------------------------------------------------------------
# 标签统计
# ---------------------------------------------------------------------------

def _compute_label_stats(df: pd.DataFrame, cs_people: dict) -> pd.DataFrame:
    groups = df.groupby(["course_name", "session", "category", "subcategory", "sentiment"])
    rows = []
    for (course, sess, cat, subcat, sent), grp in groups:
        people = grp["respondent_id"].nunique()
        total_people = cs_people.get((course, sess), 1)
        rows.append({
            "课程名称": course,
            "期次": sess,
            "category": cat,
            "subcategory": subcat,
            "sentiment": sent,
            "反馈次数": len(grp),
            "反馈人数": people,
            "有效反馈总人数": total_people,
            "反馈人数占比": round(people / total_people, 4) if total_people > 0 else 0.0,
        })
    result = pd.DataFrame(rows)
    result = result.sort_values(["课程名称", "期次", "反馈人数"], ascending=[True, True, False])
    return result


# ---------------------------------------------------------------------------
# 正向/负向/建议汇总
# ---------------------------------------------------------------------------

def _compute_sentiment_summary(df: pd.DataFrame, sentiment: str, cs_people: dict) -> pd.DataFrame:
    subset = df[df["sentiment"] == sentiment]
    if subset.empty:
        return pd.DataFrame(columns=[
            "课程名称", "期次", "category", "subcategory", "反馈人数", "反馈次数", "人数占比", "排名"
        ])

    groups = subset.groupby(["course_name", "session", "category", "subcategory"])
    rows = []
    for (course, sess, cat, subcat), grp in groups:
        people = grp["respondent_id"].nunique()
        total_people = cs_people.get((course, sess), 1)
        rows.append({
            "课程名称": course,
            "期次": sess,
            "category": cat,
            "subcategory": subcat,
            "反馈人数": people,
            "反馈次数": len(grp),
            "人数占比": round(people / total_people, 4) if total_people > 0 else 0.0,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result = result.sort_values(["课程名称", "期次", "反馈人数"], ascending=[True, True, False])
    result["排名"] = result.groupby(["课程名称", "期次"]).cumcount() + 1
    return result


# ---------------------------------------------------------------------------
# 课程期次反馈概览
# ---------------------------------------------------------------------------

def _compute_course_session_overview(df: pd.DataFrame) -> pd.DataFrame:
    groups = df.groupby(["course_name", "session"])
    rows = []
    for (course, sess), grp in groups:
        total_people = grp["respondent_id"].nunique()
        total_items = len(grp)
        pos = (grp["sentiment"] == "positive").sum()
        neg = (grp["sentiment"] == "negative").sum()
        sug = (grp["sentiment"] == "suggestion").sum()
        neu = (grp["sentiment"] == "neutral").sum()

        pos_pct = round(pos / total_items, 4) if total_items > 0 else 0.0
        neg_pct = round(neg / total_items, 4) if total_items > 0 else 0.0
        sug_pct = round(sug / total_items, 4) if total_items > 0 else 0.0

        top3_pos = _top3_labels(grp, "positive")
        top3_neg = _top3_labels(grp, "negative")
        top3_sug = _top3_labels(grp, "suggestion")

        rows.append({
            "课程名称": course,
            "期次": sess,
            "有效反馈人数": total_people,
            "拆分意见总数": total_items,
            "positive意见数": pos,
            "negative意见数": neg,
            "suggestion意见数": sug,
            "neutral意见数": neu,
            "positive占比": pos_pct,
            "negative占比": neg_pct,
            "suggestion占比": sug_pct,
            "Top3正向标签": top3_pos,
            "Top3负向标签": top3_neg,
            "Top3建议标签": top3_sug,
        })

    result = pd.DataFrame(rows)
    result = result.sort_values(["课程名称", "期次"])
    return result


def _top3_labels(grp: pd.DataFrame, sentiment: str) -> str:
    subset = grp[grp["sentiment"] == sentiment]
    if subset.empty:
        return ""
    label_people = subset.groupby("subcategory")["respondent_id"].nunique()
    total = grp["respondent_id"].nunique()
    top = label_people.sort_values(ascending=False).head(3)
    parts = []
    for label, count in top.items():
        pct = round(count / total * 100, 1) if total > 0 else 0.0
        parts.append(f"{label}({count}人,{pct}%)")
    return "；".join(parts)


# ---------------------------------------------------------------------------
# Excel 输出
# ---------------------------------------------------------------------------

def _write_excel(
    output_path: str,
    label_stats: pd.DataFrame,
    positive_df: pd.DataFrame,
    negative_df: pd.DataFrame,
    suggestion_df: pd.DataFrame,
    overview_df: pd.DataFrame,
    anomalies_df: pd.DataFrame,
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    sheet_configs: List[Tuple[str, pd.DataFrame, List[str]]] = [
        ("AI标签统计", label_stats, ["反馈人数占比"]),
        ("AI正向反馈汇总", positive_df, ["人数占比"]),
        ("AI负向问题汇总", negative_df, ["人数占比"]),
        ("AI改进建议汇总", suggestion_df, ["人数占比"]),
        ("课程期次反馈概览", overview_df, ["positive占比", "negative占比", "suggestion占比"]),
    ]

    wb = Workbook()
    wb.remove(wb.active)

    for sheet_name, df, pct_cols in sheet_configs:
        ws = wb.create_sheet(title=sheet_name)
        _write_df_to_sheet(ws, df, pct_cols)

    if not anomalies_df.empty:
        ws = wb.create_sheet(title="异常记录")
        _write_df_to_sheet(ws, anomalies_df, [])
        for row_idx in range(2, 2 + len(anomalies_df)):
            for col_idx in range(1, len(anomalies_df.columns) + 1):
                ws.cell(row=row_idx, column=col_idx).fill = ANOMALY_FILL
    else:
        ws = wb.create_sheet(title="异常记录")
        ws.cell(row=1, column=1, value="无异常记录")

    wb.save(output_path)


def _write_df_to_sheet(ws, df: pd.DataFrame, pct_cols: List[str]):
    import numpy as np

    if df is None or df.empty:
        ws.cell(row=1, column=1, value="暂无数据")
        return

    # NaN 替换
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype) in ("Int8", "Int16", "Int32", "Int64", "Float32", "Float64", "boolean"):
            df[col] = df[col].astype(object)
    df = df.replace({pd.NA: "", np.nan: "", pd.NaT: ""})
    df = df.fillna("")

    # 写入表头
    for col_idx, col_name in enumerate(df.columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=str(col_name))
        cell.font = HEADER_FONT_WHITE
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 写入数据
    for row_idx, (_, row) in enumerate(df.iterrows()):
        for col_idx, col_name in enumerate(df.columns, 1):
            val = row[col_name]
            if isinstance(val, float) and np.isnan(val):
                val = ""
            cell = ws.cell(row=row_idx + 2, column=col_idx, value=val)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if col_name in pct_cols and isinstance(val, (int, float)) and val != "":
                cell.number_format = '0.00%'

    # 自动列宽
    for col_idx in range(1, len(df.columns) + 1):
        max_len = 8
        col_letter = get_column_letter(col_idx)
        for row_idx in range(1, min(ws.max_row + 1, 200)):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    # 冻结首行
    ws.freeze_panes = "A2"

    # 开启筛选
    ws.auto_filter.ref = f"A1:{get_column_letter(len(df.columns))}{len(df)+1}"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI 反馈统计")
    parser.add_argument("--input", type=str, default="data/output/deepseek_feedback_batch_result.xlsx")
    parser.add_argument("--output", type=str, default="data/output/ai_feedback_statistics.xlsx")
    args = parser.parse_args()
    generate_statistics(input_path=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
