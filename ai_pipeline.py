"""
AI 模块统一调度管线

功能:
- 从 DataFrame 读取反馈 → 筛选有效反馈
- 调用 DeepSeek 逐条分类
- 生成统计数据（复用 ai_feedback_statistics）
- 生成课程总结（复用 ai_summary_generator）
- 统一的进度回调与错误处理

用法:
    from ai_pipeline import run_ai_pipeline
    results = run_ai_pipeline(feedback_df, use_cache=True, progress_callback=my_callback)
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from batch_deepseek_feedback import filter_valid_feedback, _col
from deepseek_feedback_analyzer import deepseek_analyze_feedback
from ai_feedback_analyzer import flatten_analysis_results
from ai_feedback_statistics import generate_statistics
from ai_summary_generator import generate_summaries


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def run_ai_pipeline(
    feedback_detail_df: pd.DataFrame,
    use_cache: bool = True,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> Dict[str, pd.DataFrame]:
    """统一 AI 分析管线。

    Args:
        feedback_detail_df: 包含反馈数据的 DataFrame。
            可能包含列：课程名称, 期次, 学员编号, 原始反馈, 清洗后反馈, 反馈类型, 是否空白, 是否低信息
        use_cache: 是否使用缓存。
        progress_callback: 进度回调，接收 dict。

    Returns:
        dict 包含:
            classification_detail, label_stats, positive_summary,
            negative_summary, suggestion_summary, course_overview,
            course_summary, course_summary_detail, trend_summary,
            errors, api_summary
    """

    start_time = datetime.now()
    errors: List[dict] = []

    # ---- 阶段 0: 筛选有效反馈 ----
    df_filtered = filter_valid_feedback(feedback_detail_df)
    df_filtered = df_filtered.reset_index(drop=True)

    if len(df_filtered) == 0:
        return _empty_result(start_time, "无有效反馈数据")

    # ---- 阶段 1: 逐条分类 ----
    print(f"[Pipeline] 阶段1 分类: {len(df_filtered)} 条待处理")

    col_course = _col(df_filtered, ["课程名称", "course_name"])
    col_session = _col(df_filtered, ["期次", "session"])
    col_respondent = _col(df_filtered, ["学员编号", "respondent_id"])
    col_raw = _col(df_filtered, ["原始反馈", "response_value", "feedback_text"])
    col_clean = _col(df_filtered, ["清洗后反馈", "feedback_clean"])

    results: List[dict] = []
    cache_hits = 0
    api_calls = 0
    failures = 0
    total = len(df_filtered)

    for idx, row in df_filtered.iterrows():
        fid = f"F{idx + 1:04d}"
        feedback_text = _safe_get(row, df_filtered, [col_clean, col_raw])
        course_name = _safe_get(row, df_filtered, [col_course])
        session = _safe_get(row, df_filtered, [col_session])
        respondent = _safe_get(row, df_filtered, [col_respondent])

        if not feedback_text.strip():
            failures += 1
            errors.append({
                "feedback_id": fid,
                "课程名称": course_name,
                "期次": session,
                "学员编号": respondent,
                "错误详情": "反馈文本为空",
            })
            if progress_callback:
                progress_callback({
                    "stage": "classification",
                    "current": idx + 1,
                    "total": total,
                    "cache_hits": cache_hits,
                    "api_calls": api_calls,
                    "failures": failures,
                })
            continue

        try:
            result = deepseek_analyze_feedback(
                feedback_id=fid,
                feedback_text=feedback_text,
                course_name=course_name,
                session=session,
                respondent_id=respondent,
                use_cache=use_cache,
            )
        except Exception as e:
            failures += 1
            errors.append({
                "feedback_id": fid,
                "课程名称": course_name,
                "期次": session,
                "学员编号": respondent,
                "错误详情": f"调用异常: {e}",
            })
            if progress_callback:
                progress_callback({
                    "stage": "classification",
                    "current": idx + 1,
                    "total": total,
                    "cache_hits": cache_hits,
                    "api_calls": api_calls,
                    "failures": failures,
                })
            continue

        if result.get("_cache_hit"):
            cache_hits += 1
        else:
            api_calls += 1

        if result.get("_error"):
            failures += 1
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
            n_items = len(result.get("items", []))
            print(f"  [{idx+1}/{total}] {fid} 成功: {n_items} 条意见"
                  + (" [缓存]" if result.get("_cache_hit") else ""))

        results.append(result)

        if progress_callback:
            progress_callback({
                "stage": "classification",
                "current": idx + 1,
                "total": total,
                "cache_hits": cache_hits,
                "api_calls": api_calls,
                "failures": failures,
            })

        time.sleep(0.1)

    # 展平分类结果
    classification_detail = flatten_analysis_results(results)
    success_count = total - failures
    print(f"[Pipeline] 阶段1 完成: 分类成功 {success_count}/{total}, "
          f"缓存命中 {cache_hits}, API调用 {api_calls}, 失败 {failures}")

    if len(classification_detail) == 0:
        # 无分类结果，无法继续统计和总结
        errors_df = pd.DataFrame(errors) if errors else pd.DataFrame(columns=["feedback_id", "错误详情"])
        return {
            "classification_detail": classification_detail,
            "label_stats": pd.DataFrame(),
            "positive_summary": pd.DataFrame(),
            "negative_summary": pd.DataFrame(),
            "suggestion_summary": pd.DataFrame(),
            "course_overview": pd.DataFrame(),
            "course_summary": pd.DataFrame(),
            "course_summary_detail": pd.DataFrame(),
            "trend_summary": pd.DataFrame(),
            "errors": errors_df,
            "api_summary": _api_summary_df(start_time, success_count, 0, 0,
                                            cache_hits, api_calls, failures, "无分类结果"),
        }

    # ---- 阶段 2: 统计 ----
    if progress_callback:
        progress_callback({"stage": "statistics"})

    print("[Pipeline] 阶段2 统计...")
    label_stats, positive_summary, negative_summary, suggestion_summary, course_overview = \
        _run_statistics(classification_detail, errors, start_time)

    # ---- 阶段 3: 总结 ----
    if progress_callback:
        progress_callback({"stage": "summary"})

    print("[Pipeline] 阶段3 总结...")
    course_summary, course_summary_detail, trend_summary, summary_errors = \
        _run_summaries(use_cache, errors, start_time)

    # ---- 汇总 ----
    end_time = datetime.now()
    summary_success = len(course_summary) if not course_summary.empty else 0
    summary_failures = len(summary_errors) if summary_errors else 0

    print(f"[Pipeline] 完成: 分类 {success_count}/{total}, "
          f"总结 {summary_success} 单期, "
          f"缓存命中 {cache_hits}, API调用 {api_calls}, 耗时 "
          f"{(end_time - start_time).total_seconds():.1f}秒")

    return {
        "classification_detail": classification_detail,
        "label_stats": label_stats,
        "positive_summary": positive_summary,
        "negative_summary": negative_summary,
        "suggestion_summary": suggestion_summary,
        "course_overview": course_overview,
        "course_summary": course_summary,
        "course_summary_detail": course_summary_detail,
        "trend_summary": trend_summary,
        "errors": pd.DataFrame(errors) if errors else pd.DataFrame(columns=["feedback_id", "错误详情"]),
        "api_summary": _api_summary_df(start_time, success_count, summary_success,
                                        summary_failures, cache_hits, api_calls,
                                        failures, ""),
    }


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _safe_get(row, df: pd.DataFrame, candidates: List[str], default: str = "") -> str:
    col = _col(df, candidates)
    return str(row.get(col, default)) if col else default


def _run_statistics(
    classification_detail: pd.DataFrame,
    errors: List[dict],
    start_time: datetime,
) -> tuple:
    """保存分类结果到临时 Excel，调用 generate_statistics，读取结果。"""
    tmpdir = os.path.join("data", "output")
    os.makedirs(tmpdir, exist_ok=True)
    class_path = os.path.join(tmpdir, "_pipeline_classification.xlsx")
    stats_path = os.path.join(tmpdir, "_pipeline_statistics.xlsx")

    try:
        with pd.ExcelWriter(class_path, engine="openpyxl") as writer:
            classification_detail.to_excel(writer, sheet_name="AI反馈分类明细", index=False)
        generate_statistics(input_path=class_path, output_path=stats_path)
    except Exception as e:
        print(f"  统计阶段失败: {e}")
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    label_stats = _safe_read(stats_path, "AI标签统计")
    positive_summary = _safe_read(stats_path, "AI正向反馈汇总")
    negative_summary = _safe_read(stats_path, "AI负向问题汇总")
    suggestion_summary = _safe_read(stats_path, "AI改进建议汇总")
    course_overview = _safe_read(stats_path, "课程期次反馈概览")

    print(f"  统计完成: 标签统计 {len(label_stats)} 行, 概览 {len(course_overview)} 课程期次")
    return label_stats, positive_summary, negative_summary, suggestion_summary, course_overview


def _run_summaries(
    use_cache: bool,
    errors: List[dict],
    start_time: datetime,
) -> tuple:
    """调用 generate_summaries，读取结果。"""
    tmpdir = os.path.join("data", "output")
    os.makedirs(tmpdir, exist_ok=True)
    stats_path = os.path.join(tmpdir, "_pipeline_statistics.xlsx")
    summary_path = os.path.join(tmpdir, "_pipeline_summary.xlsx")

    if not os.path.exists(stats_path):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

    summary_errors = []
    try:
        generate_summaries(
            input_path=stats_path,
            output_path=summary_path,
            use_cache=use_cache,
        )
    except Exception as e:
        print(f"  总结阶段失败: {e}")
        summary_errors.append({"阶段": "summary", "error": str(e)})
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), summary_errors

    course_summary = _safe_read(summary_path, "课程AI总结")
    course_summary_detail = _safe_read(summary_path, "课程AI总结明细")
    trend_summary = _safe_read(summary_path, "跨期趋势总结")

    # 检查 API 错误记录
    err_df = _safe_read(summary_path, "API调用错误记录")
    if not err_df.empty and err_df.iloc[0, 0] != "暂无数据":
        for _, row in err_df.iterrows():
            summary_errors.append(row.to_dict())

    print(f"  总结完成: 课程总结 {len(course_summary)} 行, 趋势 {len(trend_summary)} 行")
    return course_summary, course_summary_detail, trend_summary, summary_errors


def _safe_read(path: str, sheet_name: str) -> pd.DataFrame:
    """安全读取 Excel 工作表，不存在则返回空 DataFrame。"""
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def _api_summary_df(
    start_time: datetime,
    classify_success: int,
    summary_success: int,
    summary_failures: int,
    cache_hits: int,
    api_calls: int,
    failures: int,
    message: str,
) -> pd.DataFrame:
    end_time = datetime.now()
    rows = [
        {"指标": "分类成功数", "数值": classify_success},
        {"指标": "分类失败数", "数值": failures},
        {"指标": "总结成功数", "数值": summary_success},
        {"指标": "总结失败数", "数值": summary_failures},
        {"指标": "缓存命中数", "数值": cache_hits},
        {"指标": "API实际调用数", "数值": api_calls},
        {"指标": "开始时间", "数值": start_time.strftime("%Y-%m-%d %H:%M:%S")},
        {"指标": "结束时间", "数值": end_time.strftime("%Y-%m-%d %H:%M:%S")},
        {"指标": "总耗时", "数值": f"{(end_time - start_time).total_seconds():.1f}秒"},
    ]
    if message:
        rows.append({"指标": "备注", "数值": message})
    return pd.DataFrame(rows)


def _empty_result(start_time: datetime, message: str) -> Dict[str, pd.DataFrame]:
    empty = pd.DataFrame()
    return {
        "classification_detail": empty,
        "label_stats": empty,
        "positive_summary": empty,
        "negative_summary": empty,
        "suggestion_summary": empty,
        "course_overview": empty,
        "course_summary": empty,
        "course_summary_detail": empty,
        "trend_summary": empty,
        "errors": pd.DataFrame({"错误详情": [message]}),
        "api_summary": _api_summary_df(start_time, 0, 0, 0, 0, 0, 0, message),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI 统一分析管线")
    parser.add_argument("--input", default="data/output/course_survey_analysis.xlsx")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    from batch_deepseek_feedback import load_feedback_data

    df = load_feedback_data(args.input)
    if args.limit and args.limit > 0:
        df = df.head(args.limit)

    def _cb(info):
        stage = info.get("stage", "")
        if stage == "classification":
            print(f"  进度: {info['current']}/{info['total']} "
                  f"缓存命中={info['cache_hits']} API={info['api_calls']} 失败={info['failures']}")
        else:
            print(f"  阶段: {stage}")

    results = run_ai_pipeline(df, use_cache=not args.no_cache, progress_callback=_cb)

    print("\n=== 管线结果 ===")
    for key, val in results.items():
        if isinstance(val, pd.DataFrame):
            print(f"  {key}: {len(val)} 行")
        else:
            print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
