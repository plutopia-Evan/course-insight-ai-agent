"""
DeepSeek 批量反馈分析脚本

用法:
    python batch_deepseek_feedback.py
    python batch_deepseek_feedback.py --input "D:\\xxx\\course_survey_analysis.xlsx"
    python batch_deepseek_feedback.py --limit 5
    python batch_deepseek_feedback.py --no-cache --retry-errors

功能:
- 从 course_survey_analysis.xlsx 的"开放式反馈明细"工作表读取有效反馈
- 逐条调用 deepseek_analyze_feedback()
- 中断恢复、进度保存、缓存命中、4 工作表输出
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deepseek_feedback_analyzer import deepseek_analyze_feedback


# ---------------------------------------------------------------------------
# 输入读取
# ---------------------------------------------------------------------------

def load_feedback_data(excel_path: str) -> pd.DataFrame:
    """从 Excel 的'开放式反馈明细'工作表读取反馈数据。"""
    df = pd.read_excel(excel_path, sheet_name="开放式反馈明细")
    logger_print(f"读取反馈数据: {len(df)} 行, 列: {list(df.columns)}")
    return df


def filter_valid_feedback(df: pd.DataFrame) -> pd.DataFrame:
    """筛选有效反馈。

    规则:
    1. 反馈类型 == "有效反馈"（优先级最高）
    2. 清洗后反馈非空
    3. 是否空白 != "是"
    4. 是否低信息 != "是"
    """
    total = len(df)
    filtered = df.copy()

    # 列名兼容：中文或拼音
    type_col = None
    for candidate in ["反馈类型", "feedback_label"]:
        if candidate in filtered.columns:
            type_col = candidate
            break

    clean_col = None
    for candidate in ["清洗后反馈", "feedback_clean"]:
        if candidate in filtered.columns:
            clean_col = candidate
            break

    if type_col is not None:
        filtered = filtered[filtered[type_col] == "有效反馈"]
        logger_print(f"  按反馈类型筛选: {len(filtered)} 行 (总{total})")

    if clean_col is not None:
        filtered = filtered[filtered[clean_col].notna()]
        filtered = filtered[filtered[clean_col].astype(str).str.strip() != ""]
        logger_print(f"  按清洗后反馈非空筛选: {len(filtered)} 行")

    for col, label in [("是否空白", "是"), ("是否低信息", "是")]:
        if col in filtered.columns:
            filtered = filtered[filtered[col] != label]
            logger_print(f"  排除{col}={label}: {len(filtered)} 行")

    logger_print(f"筛选完成: {total} -> {len(filtered)} 条有效反馈")
    return filtered


# ---------------------------------------------------------------------------
# 列名映射
# ---------------------------------------------------------------------------

def _col(df: pd.DataFrame, candidates: List[str]) -> str:
    """返回第一个存在于 DataFrame 中的列名，否则返回空字符串。"""
    for c in candidates:
        if c in df.columns:
            return c
    return ""


def safe_get(row, df: pd.DataFrame, candidates: List[str], default: str = ""):
    """安全读取行中某个候选列的值。"""
    col = _col(df, candidates)
    return str(row.get(col, default)) if col else default


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def logger_print(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ---------------------------------------------------------------------------
# 进度文件
# ---------------------------------------------------------------------------

PROGRESS_DIR = os.path.join("data", "cache")
PROGRESS_PATH = os.path.join(PROGRESS_DIR, "batch_feedback_progress.json")


def _file_hash(filepath: str) -> str:
    """计算文件的 SHA256。"""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_progress() -> Optional[dict]:
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_progress(progress: dict):
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 批量处理
# ---------------------------------------------------------------------------

def run_batch(
    input_path: str,
    output_path: str = "data/output/deepseek_feedback_batch_result.xlsx",
    limit: Optional[int] = None,
    use_cache: bool = True,
    retry_errors: bool = False,
):
    start_time = datetime.now()
    logger_print(f"开始批量分析: {input_path}")
    logger_print(f"limit={limit}, use_cache={use_cache}, retry_errors={retry_errors}")

    if not os.path.exists(input_path):
        logger_print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)

    # 读取并筛选
    df_raw = load_feedback_data(input_path)
    df = filter_valid_feedback(df_raw)

    if limit is not None and limit > 0:
        df = df.head(limit)
        logger_print(f"限制处理前 {limit} 条")

    if len(df) == 0:
        logger_print("没有需要处理的反馈数据")
        return

    # 列名映射
    col_course = _col(df, ["课程名称", "course_name"])
    col_session = _col(df, ["期次", "session"])
    col_respondent = _col(df, ["学员编号", "respondent_id"])
    col_raw = _col(df, ["原始反馈", "response_value", "feedback_text"])
    col_clean = _col(df, ["清洗后反馈", "feedback_clean"])

    # 生成稳定的 feedback_id
    df = df.reset_index(drop=True)
    feedback_ids = [f"F{i+1:04d}" for i in range(len(df))]
    df["_feedback_id"] = feedback_ids

    # 中断恢复
    input_hash = _file_hash(input_path)
    processed_ids = set()
    results: List[dict] = []
    errors: List[dict] = []

    prev = load_progress()
    if prev and prev.get("input_file_hash") == input_hash:
        logger_print(f"发现历史进度: {len(prev.get('processed_feedback_ids', []))} 条已处理")
        processed_ids = set(prev.get("processed_feedback_ids", []))
        results = prev.get("results", [])
        errors = prev.get("errors", [])
    elif prev and prev.get("input_file_hash") != input_hash:
        logger_print("输入文件已变化，将创建新批次")

    cache_hits = 0
    api_calls = 0

    for idx, row in df.iterrows():
        fid = row["_feedback_id"]

        if not retry_errors and fid in processed_ids:
            cache_hits += 1
            continue

        # 反馈文本：优先使用清洗后反馈
        feedback_text = safe_get(row, df, [col_clean, col_raw])
        course_name = safe_get(row, df, [col_course])
        session = safe_get(row, df, [col_session])
        respondent = safe_get(row, df, [col_respondent])
        raw_text = safe_get(row, df, [col_raw])

        if not feedback_text.strip():
            logger_print(f"[{idx+1}/{len(df)}] {fid} 跳过: 反馈文本为空")
            processed_ids.add(fid)
            continue

        # 调用
        result = deepseek_analyze_feedback(
            feedback_id=fid,
            feedback_text=feedback_text,
            course_name=course_name,
            session=session,
            respondent_id=respondent,
            use_cache=use_cache,
        )

        if result.get("_cache_hit"):
            cache_hits += 1
        else:
            api_calls += 1

        if result.get("_error"):
            logger_print(f"[{idx+1}/{len(df)}] {fid} 失败: {result['_error']}")
            errors.append({
                "feedback_id": fid,
                "课程名称": course_name,
                "期次": session,
                "学员编号": respondent,
                "清洗后反馈": feedback_text,
                "错误详情": result["_error"],
                "重试次数": result.get("_retries", 0),
            })
        else:
            n = len(result.get("items", []))
            logger_print(f"[{idx+1}/{len(df)}] {fid} 成功, 拆分 {n} 条意见"
                         + (" [缓存]" if result.get("_cache_hit") else ""))

        # 完整保存
        result["_idx"] = idx
        result["_feedback_text"] = feedback_text
        result["_raw_text"] = raw_text
        result["_course_name"] = course_name
        result["_session"] = session
        result["_respondent_id"] = respondent
        results.append(result)
        processed_ids.add(fid)

        # 每 10 条保存一次进度
        if (idx + 1) % 10 == 0:
            progress = {
                "input_file": os.path.abspath(input_path),
                "input_file_hash": input_hash,
                "processed_feedback_ids": sorted(processed_ids),
                "results": results,
                "errors": errors,
            }
            save_progress(progress)
            logger_print(f"  进度已保存 ({idx+1}/{len(df)})")

    # 最终保存进度
    progress = {
        "input_file": os.path.abspath(input_path),
        "input_file_hash": input_hash,
        "processed_feedback_ids": sorted(processed_ids),
        "results": results,
        "errors": errors,
    }
    save_progress(progress)

    # 生成输出
    end_time = datetime.now()
    _write_output(
        results=results,
        errors=errors,
        output_path=output_path,
        start_time=start_time,
        end_time=end_time,
        cache_hits=cache_hits,
        api_calls=api_calls,
        df=df,
    )

    success = sum(1 for r in results if not r.get("_error"))
    fail = len(errors)
    total_items = sum(len(r.get("items", [])) for r in results)
    logger_print(f"批量分析完成: 成功 {success}, 失败 {fail}, 缓存命中 {cache_hits}, API 调用 {api_calls}")
    logger_print(f"输出文件: {os.path.abspath(output_path)}")


# ---------------------------------------------------------------------------
# 输出 Excel
# ---------------------------------------------------------------------------

def _write_output(
    results: List[dict],
    errors: List[dict],
    output_path: str,
    start_time: datetime,
    end_time: datetime,
    cache_hits: int,
    api_calls: int,
    df: pd.DataFrame,
):
    import deepseek_config as cfg

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. AI反馈分类明细
    detail_rows = []
    for r in results:
        if r.get("_error"):
            continue
        for item in r.get("items", []):
            detail_rows.append({
                "feedback_id": r["feedback_id"],
                "课程名称": r.get("_course_name", ""),
                "期次": r.get("_session", ""),
                "学员编号": r.get("_respondent_id", ""),
                "原始反馈": r.get("_raw_text", ""),
                "清洗后反馈": r.get("_feedback_text", ""),
                "category": item.get("category", ""),
                "subcategory": item.get("subcategory", ""),
                "sentiment": item.get("sentiment", ""),
                "summary": item.get("summary", ""),
                "evidence": item.get("evidence", ""),
                "是否缓存命中": "是" if r.get("_cache_hit") else "否",
                "重试次数": r.get("_retries", 0),
            })
    detail_df = pd.DataFrame(detail_rows)

    # 2. API调用错误记录
    err_df = pd.DataFrame(errors) if errors else pd.DataFrame(
        columns=["feedback_id", "课程名称", "期次", "学员编号", "清洗后反馈", "错误详情", "重试次数"]
    )

    # 3. 批量分析汇总
    success_count = sum(1 for r in results if not r.get("_error"))
    fail_count = len(errors)
    total = success_count + fail_count
    total_items = sum(len(r.get("items", [])) for r in results)
    positive = sum(1 for r in results for it in r.get("items", []) if it.get("sentiment") == "positive")
    negative = sum(1 for r in results for it in r.get("items", []) if it.get("sentiment") == "negative")
    suggestion = sum(1 for r in results for it in r.get("items", []) if it.get("sentiment") == "suggestion")
    neutral = sum(1 for r in results for it in r.get("items", []) if it.get("sentiment") == "neutral")
    elapsed = (end_time - start_time).total_seconds()

    summary_rows = [
        {"指标": "输入总反馈数", "数值": len(df)},
        {"指标": "筛选后有效反馈数", "数值": len(df)},
        {"指标": "成功反馈数", "数值": success_count},
        {"指标": "失败反馈数", "数值": fail_count},
        {"指标": "成功率", "数值": f"{success_count/total*100:.1f}%" if total > 0 else "N/A"},
        {"指标": "缓存命中数", "数值": cache_hits},
        {"指标": "API实际调用反馈数", "数值": api_calls},
        {"指标": "拆分意见总数", "数值": total_items},
        {"指标": "平均每条反馈意见数", "数值": f"{total_items/total:.2f}" if total > 0 else "N/A"},
        {"指标": "positive意见数", "数值": positive},
        {"指标": "negative意见数", "数值": negative},
        {"指标": "suggestion意见数", "数值": suggestion},
        {"指标": "neutral意见数", "数值": neutral},
        {"指标": "开始时间", "数值": start_time.strftime('%Y-%m-%d %H:%M:%S')},
        {"指标": "结束时间", "数值": end_time.strftime('%Y-%m-%d %H:%M:%S')},
        {"指标": "总耗时", "数值": f"{elapsed:.1f}秒"},
        {"指标": "使用模型", "数值": cfg.DEEPSEEK_MODEL},
    ]
    summary_df = pd.DataFrame(summary_rows)

    # 4. 标签数量汇总（去重反馈人数）
    label_rows = []
    if detail_df is not None and not detail_df.empty:
        groups = detail_df.groupby(
            ["课程名称", "期次", "category", "subcategory", "sentiment"]
        )
        for (course, sess, cat, subcat, sent), grp in groups:
            feedback_count = len(grp)
            unique_people = grp[["学员编号"]].drop_duplicates().shape[0]
            label_rows.append({
                "课程名称": course,
                "期次": sess,
                "category": cat,
                "subcategory": subcat,
                "sentiment": sent,
                "反馈次数": feedback_count,
                "去重反馈人数": unique_people,
            })
    label_df = pd.DataFrame(label_rows)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name="AI反馈分类明细", index=False)
        err_df.to_excel(writer, sheet_name="API调用错误记录", index=False)
        summary_df.to_excel(writer, sheet_name="批量分析汇总", index=False)
        if not label_df.empty:
            label_df.to_excel(writer, sheet_name="标签数量汇总", index=False)

        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_idx in range(1, ws.max_column + 1):
                col_letter = chr(64 + col_idx) if col_idx <= 26 else "A"
                max_len = 8
                for row_idx in range(1, min(ws.max_row + 1, 200)):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    logger_print(f"Excel 已保存: {os.path.abspath(output_path)}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DeepSeek 批量反馈分析")
    parser.add_argument(
        "--input", type=str, default="data/output/course_survey_analysis.xlsx",
        help="输入 Excel 路径"
    )
    parser.add_argument(
        "--output", type=str, default="data/output/deepseek_feedback_batch_result.xlsx",
        help="输出 Excel 路径"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="限制处理条数（测试用）"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="禁用缓存"
    )
    parser.add_argument(
        "--retry-errors", action="store_true",
        help="重新尝试已失败的数据"
    )
    args = parser.parse_args()

    run_batch(
        input_path=args.input,
        output_path=args.output,
        limit=args.limit,
        use_cache=not args.no_cache,
        retry_errors=args.retry_errors,
    )


if __name__ == "__main__":
    main()
