"""
课程问卷智能分析工具 - Streamlit 网页界面

功能: 上传问卷文件和题目映射配置，在线分析并下载结果

用法:
    streamlit run app.py
"""

import os
import sys
import logging
import tempfile
import shutil
from datetime import datetime
from io import BytesIO

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from survey_processor import (
    load_question_mapping,
    read_survey_file,
    wide_to_long,
    map_questions,
    detect_anomalies,
    get_valid_ratings,
    split_rating_and_text,
    classify_questions,
    compute_auto_coverage,
    apply_auto_category,
)
from statistics import (
    compute_global_common_stats,
    compute_course_common_stats,
    compute_period_specific_stats,
    compute_session_stats,
    compute_overview_stats,
    compute_feedback_overview,
)
from text_cleaner import (
    clean_text_feedback,
    generate_feedback_summary,
)
from output_writer import (
    write_output_excel,
    build_file_identification,
    build_pending_review,
    build_feedback_frequency,
)
from ai_pipeline import run_ai_pipeline


st.set_page_config(
    page_title="课程问卷智能分析工具",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def setup_temp_logging():
    """配置临时日志捕获，用于在 Streamlit 中显示进度。"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, StreamlitLogHandler) for h in logger.handlers):
        handler = StreamlitLogHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("[%(levelname)-5s] %(message)s"))
        logger.addHandler(handler)
    return logger


class StreamlitLogHandler(logging.Handler):
    """将日志消息发送到 Streamlit 占位符。"""
    def __init__(self):
        super().__init__()
        self.placeholder = None

    def emit(self, record):
        msg = self.format(record)
        if self.placeholder is not None:
            self.placeholder.text(msg)


def run_analysis(survey_files, mapping_file, temp_dir):
    """执行完整的问卷分析流程。

    Args:
        survey_files: 上传的问卷文件列表 [(filename, bytes), ...]
        mapping_file: 上传的题目映射 (filename, bytes)
        temp_dir: 临时目录路径

    Returns:
        dict: 包含所有分析结果的字典
    """
    log_handler = StreamlitLogHandler()
    logger = logging.getLogger()
    logger.addHandler(log_handler)

    progress_container = st.empty()
    log_handler.placeholder = progress_container

    try:
        progress_container.info("正在保存上传文件...")
        saved_survey_paths = []
        for fname, fdata in survey_files:
            save_path = os.path.join(temp_dir, fname)
            with open(save_path, "wb") as f:
                f.write(fdata)
            saved_survey_paths.append(save_path)

        config_path = os.path.join(temp_dir, mapping_file[0])
        with open(config_path, "wb") as f:
            f.write(mapping_file[1])

        progress_container.info("正在加载题目映射配置...")
        mapping_df = load_question_mapping(config_path)

        all_long_tables = []
        all_question_headers = []
        file_course_sessions = []
        all_anomalies = []
        filename_issues = []

        file_count = len(saved_survey_paths)
        for i, filepath in enumerate(saved_survey_paths):
            fname = os.path.basename(filepath)
            progress_container.info(f"正在处理文件 ({i+1}/{file_count}): {fname}")
            try:
                cn, sn, df_raw, qh, mc = read_survey_file(filepath)
                file_course_sessions.append((cn, sn, len(df_raw), len(qh)))
                df_long = wide_to_long(df_raw, qh)
                df_long = map_questions(df_long, mapping_df)
                anomalies = detect_anomalies(df_long)
                if not anomalies.empty:
                    all_anomalies.append(anomalies)
                all_long_tables.append(df_long)
                all_question_headers.extend(qh)
            except Exception as e:
                filename_issues.append({"文件名": fname, "原因": f"处理异常: {e}"})
                progress_container.warning(f"文件 {fname} 处理异常: {e}")
                continue

        if not all_long_tables:
            progress_container.error("没有文件被成功处理")
            return None

        progress_container.info("正在合并数据...")
        df_all_long = pd.concat(all_long_tables, ignore_index=True)
        anomalies_combined = pd.concat(all_anomalies, ignore_index=True) if all_anomalies else pd.DataFrame()

        progress_container.info("正在检测异常评分...")
        valid_ratings = get_valid_ratings(df_all_long)
        all_ratings = df_all_long[df_all_long["question_type"] == "rating"].copy()
        _, text_df = split_rating_and_text(df_all_long)

        progress_container.info("正在分类题目...")
        auto_coverage_df, auto_category_map = compute_auto_coverage(df_all_long, mapping_df)
        df_all_long, valid_ratings = apply_auto_category(df_all_long, valid_ratings, auto_category_map)
        all_ratings["auto_category"] = all_ratings["standard_question"].map(auto_category_map)
        all_ratings["auto_category"] = all_ratings["auto_category"].fillna("unknown")

        all_course_sessions_data = df_all_long[["course_name", "session"]].drop_duplicates()
        total_course_sessions = len(all_course_sessions_data)
        unique_session_labels = df_all_long["session"].nunique()

        question_coverage = classify_questions(mapping_df, all_question_headers)
        file_identification = build_file_identification(saved_survey_paths, file_course_sessions)

        progress_container.info("正在计算统计数据...")
        global_stats = compute_global_common_stats(valid_ratings, all_ratings)
        course_common_stats = compute_course_common_stats(valid_ratings, all_ratings)
        period_specific_stats = compute_period_specific_stats(valid_ratings, all_ratings)
        session_stats = compute_session_stats(valid_ratings, all_ratings)

        progress_container.info("正在清洗文本反馈...")
        cleaned_feedback = clean_text_feedback(text_df)
        feedback_summary = generate_feedback_summary(cleaned_feedback)
        feedback_overview = compute_feedback_overview(text_df, cleaned_feedback)
        feedback_frequency = build_feedback_frequency(cleaned_feedback)

        progress_container.info("正在生成数据总览...")
        overview = compute_overview_stats(
            valid_ratings, df_all_long, text_df, anomalies_combined, saved_survey_paths,
            feedback_overview=feedback_overview,
            total_course_sessions=total_course_sessions,
            unique_session_labels=unique_session_labels,
        )

        progress_container.info("正在构建待确认列表...")
        pending_review = build_pending_review(df_all_long, anomalies_combined, filename_issues,
                                             auto_coverage_df=auto_coverage_df)

        feedback_detail_cols = [
            "course_name", "session", "学员编号",
            "response_value", "feedback_clean", "feedback_label", "duplicate_count",
        ]
        feedback_detail = cleaned_feedback[[c for c in feedback_detail_cols if c in cleaned_feedback.columns]].copy()
        feedback_detail.rename(columns={
            "course_name": "课程名称",
            "session": "期次",
            "response_value": "原始反馈",
            "feedback_clean": "清洗后反馈",
            "feedback_label": "反馈类型",
            "duplicate_count": "重复次数",
        }, inplace=True)
        feedback_detail["是否空白"] = feedback_detail["反馈类型"].apply(lambda x: "是" if x == "纯空白反馈" else "否")
        feedback_detail["是否低信息"] = feedback_detail["反馈类型"].apply(lambda x: "是" if x == "低信息量反馈" else "否")

        normalized_long = df_all_long.copy()
        if "response_value" in normalized_long.columns:
            normalized_long["response_value"] = normalized_long["response_value"].astype(str)
        output_cols = [
            "学员编号", "course_name", "session", "original_question",
            "standard_question", "question_type", "max_score", "category", "response_value",
        ]
        normalized_long_output = normalized_long[[c for c in output_cols if c in normalized_long.columns]]

        mapping_detail = mapping_df.copy()
        if "max_score" in mapping_detail.columns:
            mapping_detail["max_score"] = mapping_detail["max_score"].astype(str)

        output_xlsx_path = os.path.join(temp_dir, "course_survey_analysis.xlsx")
        output_data = {
            "overview": overview,
            "file_identification": file_identification,
            "normalized_long": normalized_long_output,
            "question_mapping_result": mapping_detail,
            "question_coverage": question_coverage,
            "auto_coverage": auto_coverage_df,
            "global_common_stats": global_stats,
            "course_common_stats": course_common_stats,
            "period_specific_stats": period_specific_stats,
            "session_stats": session_stats,
            "feedback_summary": feedback_summary,
            "feedback_frequency": feedback_frequency,
            "feedback_detail": feedback_detail,
            "anomalies": anomalies_combined,
            "pending_review": pending_review,
        }

        progress_container.info("正在生成 Excel 报告...")
        write_output_excel(output_xlsx_path, output_data)

        progress_container.empty()

        return {
            "overview": overview,
            "file_identification": file_identification,
            "question_coverage": question_coverage,
            "auto_coverage": auto_coverage_df,
            "global_common_stats": global_stats,
            "course_common_stats": course_common_stats,
            "period_specific_stats": period_specific_stats,
            "session_stats": session_stats,
            "feedback_summary": feedback_summary,
            "feedback_frequency": feedback_frequency,
            "feedback_overview": feedback_overview,
            "feedback_detail": feedback_detail,
            "anomalies": anomalies_combined,
            "pending_review": pending_review,
            "output_xlsx_path": output_xlsx_path,
            "total_course_sessions": total_course_sessions,
            "unique_session_labels": unique_session_labels,
        }
    finally:
        logger.removeHandler(log_handler)


def main():
    st.title("📊 课程问卷智能分析工具")
    st.markdown("上传课程问卷 Excel 文件，自动完成题目映射、评分统计、文本清洗，一键下载分析报告。")

    st.sidebar.header("📋 使用说明")
    st.sidebar.markdown("""
    1. 上传问卷 Excel 文件（可多选）
    2. 上传题目映射配置文件
    3. 点击"开始分析"
    4. 查看分析结果
    5. 下载完整报告

    ---
    **文件要求：**
    - 问卷文件: `.xlsx` 格式
    - 文件名: `课程名称_第XX期.xlsx`
    - 映射文件: 需含 `original_question`, `standard_question`, `question_type`, `max_score`, `category` 列
    """)

    col1, col2 = st.columns(2)
    with col1:
        uploaded_surveys = st.file_uploader(
            "📁 上传问卷文件",
            type=["xlsx"],
            accept_multiple_files=True,
            help="支持批量上传多个课程期次的问卷文件",
        )
    with col2:
        uploaded_mapping = st.file_uploader(
            "📁 上传题目映射配置",
            type=["xlsx"],
            accept_multiple_files=False,
            help="上传 question_mapping.xlsx",
        )

    if "analysis_done" not in st.session_state:
        st.session_state.analysis_done = False
    if "results" not in st.session_state:
        st.session_state.results = None
    if "xlsx_bytes" not in st.session_state:
        st.session_state.xlsx_bytes = None

    # AI pipeline session state
    if "base_analysis_done" not in st.session_state:
        st.session_state.base_analysis_done = False
    if "base_results" not in st.session_state:
        st.session_state.base_results = None
    if "ai_analysis_done" not in st.session_state:
        st.session_state.ai_analysis_done = False
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
    if "base_xlsx_bytes" not in st.session_state:
        st.session_state.base_xlsx_bytes = None
    if "complete_xlsx_bytes" not in st.session_state:
        st.session_state.complete_xlsx_bytes = None

    # Backward compatibility: mirror legacy analysis_done/results to base_*
    if st.session_state.analysis_done and not st.session_state.base_analysis_done:
        st.session_state.base_analysis_done = True
        st.session_state.base_results = st.session_state.results
        st.session_state.base_xlsx_bytes = st.session_state.xlsx_bytes

    can_analyze = uploaded_surveys and uploaded_mapping

    if st.button("🚀 开始分析", type="primary", disabled=not can_analyze, use_container_width=True):
        if not uploaded_surveys:
            st.error("请先上传问卷文件")
            return
        if not uploaded_mapping:
            st.error("请先上传题目映射配置")
            return

        survey_names = [f.name for f in uploaded_surveys]
        seen = set()
        dupes = [n for n in survey_names if n in seen or seen.add(n)]
        if dupes:
            st.error(f"检测到同名文件: {dupes}，请移除重复文件后重新上传。")
            return

        temp_dir = tempfile.mkdtemp(prefix="survey_analysis_")
        try:
            survey_files = [(f.name, f.read()) for f in uploaded_surveys]
            mapping_file = (uploaded_mapping.name, uploaded_mapping.read())

            with st.spinner("正在分析中，请稍候..."):
                results = run_analysis(survey_files, mapping_file, temp_dir)

            if results is None:
                st.error("分析失败，请检查上传文件格式是否正确")
                return

            with open(results["output_xlsx_path"], "rb") as f:
                st.session_state.xlsx_bytes = f.read()

            st.session_state.results = results
            st.session_state.analysis_done = True
            st.session_state.base_analysis_done = True
            st.session_state.base_results = results
            st.session_state.base_xlsx_bytes = st.session_state.xlsx_bytes
            st.session_state.ai_analysis_done = False
            st.session_state.ai_results = None
            st.session_state.complete_xlsx_bytes = None

        except Exception as e:
            st.error(f"分析过程出错: {e}")
            import traceback
            st.code(traceback.format_exc())
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    if st.session_state.analysis_done and st.session_state.results:
        results = st.session_state.results

        st.divider()
        st.header("📈 分析结果概览")

        overview = results["overview"]
        overview_dict = dict(zip(overview["指标"], overview["数值"]))

        metric_cols = st.columns(5)
        tcs = results.get("total_course_sessions", 0)
        usl = results.get("unique_session_labels", 0)
        metrics = [
            ("分析文件数", overview_dict.get("分析文件数", 0)),
            ("课程数", overview_dict.get("课程数", 0)),
            ("课程期次数", int(tcs) if tcs else 0),
            ("唯一期次标签数", int(usl) if usl else 0),
            ("总学员人次", overview_dict.get("总学员人次", 0)),
        ]
        for i, (label, val) in enumerate(metrics):
            with metric_cols[i]:
                st.metric(label=label, value=int(val) if val is not None else 0)

        metric_cols2 = st.columns(4)
        metrics2 = [
            ("有效评分数", overview_dict.get("有效评分数", 0)),
            ("异常评分数", overview_dict.get("异常评分数", 0)),
            ("开放式反馈 - 有效反馈数", overview_dict.get("开放式反馈 - 有效反馈数", 0)),
            ("标准题目数", overview_dict.get("标准题目数", 0)),
        ]
        for i, (label, val) in enumerate(metrics2):
            with metric_cols2[i]:
                st.metric(label=label, value=int(val) if val is not None else 0)

        if st.session_state.xlsx_bytes:
            st.download_button(
                label="📥 下载完整分析报告 (course_survey_analysis.xlsx)",
                data=st.session_state.xlsx_bytes,
                file_name=f"course_survey_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        # ---- AI 开放式反馈分析 ----
        st.divider()
        st.subheader("🤖 AI开放式反馈分析")

        feedback_detail = results.get("feedback_detail")
        has_feedback = feedback_detail is not None and not feedback_detail.empty

        enable_ai = st.checkbox(
            "启用AI开放式反馈分析",
            value=False,
            help="启用后会调用DeepSeek API，可能产生费用",
            disabled=not has_feedback,
        )

        if not has_feedback:
            st.info("当前数据中无开放式反馈，无法启用AI分析")

        can_run_ai = (
            st.session_state.base_analysis_done
            and enable_ai
            and has_feedback
        )

        if st.button("🤖 开始AI反馈分析", type="primary",
                      disabled=not can_run_ai, use_container_width=True):
            _run_ai_analysis()

        # Show AI download if available
        if st.session_state.complete_xlsx_bytes:
            st.download_button(
                label="📥 下载完整报告（含AI分析）",
                data=st.session_state.complete_xlsx_bytes,
                file_name=f"course_survey_ai_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.divider()

        tabs = st.tabs([
            "文件识别结果",
            "题目覆盖情况",
            "全局公共题统计",
            "课程公共题统计",
            "单期特有题统计",
            "异常数据",
            "反馈频次汇总",
            "开放式反馈明细",
        ])

        with tabs[0]:
            st.subheader("文件识别结果")
            file_id = results["file_identification"]
            display_cols = [c for c in file_id.columns if c != "文件路径"]
            st.dataframe(file_id[display_cols], use_container_width=True, hide_index=True)

        with tabs[1]:
            st.subheader("题目覆盖情况（基于实际上传数据自动判定）")
            auto_cov = results.get("auto_coverage")
            if auto_cov is not None and not auto_cov.empty:
                display_cols = [c for c in auto_cov.columns]
                st.dataframe(auto_cov[display_cols], use_container_width=True, hide_index=True)

                st.divider()
                cat_col1, cat_col2, cat_col3, cat_col4 = st.columns(4)
                cats = auto_cov["自动分类"].value_counts()
                cat_names = {"global_common": "全局公共题", "course_common": "课程公共题",
                             "period_specific": "单期特有题", "feedback": "开放式反馈题"}
                for col, (cat_val, count) in zip([cat_col1, cat_col2, cat_col3, cat_col4], cats.items()):
                    col.metric(label=cat_names.get(cat_val, cat_val), value=count)

                inconsistent = auto_cov[auto_cov["配置与自动是否一致"] == "否"]
                if not inconsistent.empty:
                    st.warning(f"以下 {len(inconsistent)} 个题目的配置分类与自动分类不一致:")
                    st.dataframe(inconsistent[["standard_question", "配置category", "自动分类"]],
                                 use_container_width=True, hide_index=True)
            else:
                st.info("无题目覆盖数据")

        with tabs[2]:
            st.subheader("全局公共题统计")
            gs = results["global_common_stats"]
            if not gs.empty:
                display_cols = [c for c in gs.columns if c != "统计维度"]
                st.dataframe(gs[display_cols], use_container_width=True, hide_index=True)
            else:
                st.info("无全局公共题数据")

        with tabs[3]:
            st.subheader("课程公共题统计")
            cs = results["course_common_stats"]
            if not cs.empty:
                display_cols = [c for c in cs.columns if c != "统计维度"]
                st.dataframe(cs[display_cols], use_container_width=True, hide_index=True)
            else:
                st.info("无课程公共题数据")

        with tabs[4]:
            st.subheader("单期特有题统计")
            ps = results["period_specific_stats"]
            if not ps.empty:
                display_cols = [c for c in ps.columns if c != "统计维度"]
                st.dataframe(ps[display_cols], use_container_width=True, hide_index=True)
            else:
                st.info("无单期特有题数据")

        with tabs[5]:
            st.subheader("异常数据")
            anomalies = results["anomalies"]
            if not anomalies.empty:
                st.warning(f"共检测到 {len(anomalies)} 条异常评分记录")
                st.dataframe(anomalies, use_container_width=True, hide_index=True)
            else:
                st.success("未检测到异常评分记录")

        with tabs[6]:
            st.subheader("反馈频次汇总")
            ff = results["feedback_frequency"]
            if not ff.empty:
                st.dataframe(ff, use_container_width=True, hide_index=True)
            else:
                st.info("无有效反馈数据")

        with tabs[7]:
            st.subheader("开放式反馈明细")
            fd = results.get("feedback_detail")
            if fd is not None and not fd.empty:
                st.dataframe(fd, use_container_width=True, hide_index=True)
            else:
                st.info("无反馈数据")

        st.divider()

        # ---- AI 分析结果标签页 ----
        if st.session_state.ai_analysis_done and st.session_state.ai_results:
            _render_ai_tabs(st.session_state.ai_results)

        st.caption(f"分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def _run_ai_analysis():
    """执行 AI 分析管线（在按钮回调中调用）。"""
    feedback_detail = st.session_state.base_results.get("feedback_detail")
    if feedback_detail is None or feedback_detail.empty:
        st.warning("无可用的开放式反馈数据")
        return

    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    metric_cols = st.columns(5)

    def progress_callback(info):
        stage = info.get("stage", "")
        if stage == "classification":
            current = info.get("current", 0)
            total = info.get("total", 1)
            fraction = min(current / total, 1.0)
            progress_bar.progress(fraction)
            status_placeholder.text(f"正在分类: {current}/{total}")
            metric_cols[0].metric("阶段", "分类")
            metric_cols[1].metric("完成/总数", f"{current}/{total}")
            metric_cols[2].metric("缓存命中", info.get("cache_hits", 0))
            metric_cols[3].metric("API调用", info.get("api_calls", 0))
            metric_cols[4].metric("失败", info.get("failures", 0))
        elif stage == "statistics":
            status_placeholder.text("正在生成统计数据...")
            metric_cols[0].metric("阶段", "统计")
        elif stage == "summary":
            status_placeholder.text("正在生成课程总结...")
            metric_cols[0].metric("阶段", "总结")

    try:
        with st.spinner("AI分析进行中，请稍候..."):
            ai_results = run_ai_pipeline(
                feedback_detail_df=feedback_detail,
                use_cache=True,
                progress_callback=progress_callback,
            )

        st.session_state.ai_results = ai_results
        st.session_state.ai_analysis_done = True

        # Generate combined Excel
        try:
            base_bytes = st.session_state.base_xlsx_bytes
            if base_bytes:
                from io import BytesIO
                combined = BytesIO()
                with pd.ExcelWriter(combined, engine="openpyxl") as writer:
                    # Write base sheets from the base Excel
                    base_xl = pd.ExcelFile(BytesIO(base_bytes))
                    for sheet in base_xl.sheet_names:
                        base_xl.parse(sheet).to_excel(writer, sheet_name=sheet, index=False)
                    # Append AI sheets
                    ai_sheet_map = [
                        ("AI反馈分类明细", "classification_detail"),
                        ("AI标签统计", "label_stats"),
                        ("AI正向评价", "positive_summary"),
                        ("AI负向问题", "negative_summary"),
                        ("AI改进建议", "suggestion_summary"),
                        ("课程期次反馈概览(AI)", "course_overview"),
                        ("课程AI总结", "course_summary"),
                        ("课程AI总结明细", "course_summary_detail"),
                        ("跨期趋势总结", "trend_summary"),
                        ("AI调用汇总", "api_summary"),
                    ]
                    for sheet_name, key in ai_sheet_map:
                        df = ai_results.get(key)
                        if df is not None and not df.empty:
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
                    # Errors
                    err_df = ai_results.get("errors")
                    if err_df is not None and not err_df.empty:
                        err_df.to_excel(writer, sheet_name="AI错误记录", index=False)
                combined.seek(0)
                st.session_state.complete_xlsx_bytes = combined.getvalue()

        except Exception as e:
            st.warning(f"合并Excel时出错: {e}，基础报告仍可下载")

        progress_bar.progress(1.0)
        if ai_results.get("errors") is not None and not ai_results["errors"].empty:
            status_placeholder.text("AI分析结束，存在未完成项目，请查看 AI 错误记录")
        else:
            status_placeholder.text("AI分析完成！")
        progress_placeholder.empty()

    except Exception as e:
        st.warning(f"AI分析过程出错: {e}，基础分析结果不受影响")
        import traceback
        st.code(traceback.format_exc())


def _render_ai_tabs(ai_results):
    """渲染 AI 分析结果标签页。"""
    tabs = st.tabs([
        "AI反馈分类明细",
        "AI标签统计",
        "AI正向评价",
        "AI负向问题",
        "AI改进建议",
        "课程AI总结",
        "跨期趋势分析",
        "AI调用汇总",
        "AI错误记录",
    ])

    with tabs[0]:
        st.subheader("AI反馈分类明细")
        df = ai_results.get("classification_detail")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无分类明细数据")

    with tabs[1]:
        st.subheader("AI标签统计")
        df = ai_results.get("label_stats")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无标签统计数据")

    with tabs[2]:
        st.subheader("AI正向评价")
        df = ai_results.get("positive_summary")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无正向评价数据")

    with tabs[3]:
        st.subheader("AI负向问题")
        df = ai_results.get("negative_summary")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无负向问题数据")

    with tabs[4]:
        st.subheader("AI改进建议")
        df = ai_results.get("suggestion_summary")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无改进建议数据")

    with tabs[5]:
        _render_course_summary_tab(ai_results)

    with tabs[6]:
        _render_trend_tab(ai_results)

    with tabs[7]:
        st.subheader("AI调用汇总")
        df = ai_results.get("api_summary")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无调用汇总数据")

    with tabs[8]:
        st.subheader("AI错误记录")
        df = ai_results.get("errors")
        if df is not None and not df.empty:
            st.warning(f"共 {len(df)} 条错误记录")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("无错误记录")


def _render_course_summary_tab(ai_results):
    """渲染课程AI总结标签页，支持课程和期次选择。"""
    st.subheader("课程AI总结")

    course_summary_df = ai_results.get("course_summary")
    if course_summary_df is None or course_summary_df.empty:
        st.info("无课程总结数据")
        return

    courses = sorted(course_summary_df["课程名称"].dropna().unique())
    if len(courses) == 0:
        st.info("无课程数据")
        return

    selected_course = st.selectbox("选择课程", courses, key="ai_course_select")

    # 过滤该课程的期次
    course_sessions = course_summary_df[course_summary_df["课程名称"] == selected_course]
    sessions = sorted(course_sessions["期次"].dropna().unique())
    selected_session = st.selectbox("选择期次", sessions, key="ai_session_select")

    # 查找对应行
    row = course_sessions[course_sessions["期次"] == selected_session]
    if row.empty:
        st.info("未找到该期次的总结数据")
        return
    row = row.iloc[0]

    st.markdown("### 整体评价")
    st.write(row.get("整体评价", "无"))

    st.markdown("### 主要优点")
    st.write(row.get("主要优点", "无"))

    st.markdown("### 主要问题")
    st.write(row.get("主要问题", "无"))

    st.markdown("### 改进建议")
    st.write(row.get("改进建议", "无"))

    st.markdown("### 管理层摘要")
    st.write(row.get("管理层摘要", "无"))


def _render_trend_tab(ai_results):
    """渲染跨期趋势分析标签页。"""
    st.subheader("跨期趋势分析")

    trend_df = ai_results.get("trend_summary")
    if trend_df is None or trend_df.empty:
        st.info("无跨期趋势数据（需要同一课程至少2个期次）")
        return

    courses = sorted(trend_df["课程名称"].dropna().unique())

    for course in courses:
        course_trend = trend_df[trend_df["课程名称"] == course]
        if course_trend.empty:
            continue
        row = course_trend.iloc[0]

        with st.expander(f"📊 {course}", expanded=(len(courses) == 1)):
            st.markdown("#### 趋势总结")
            st.write(row.get("趋势总结", "无"))

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("#### 持续问题")
                val = row.get("持续问题", "")
                st.write(val if pd.notna(val) and str(val).strip() else "无")
            with col2:
                st.markdown("#### 仅本期观察到的问题")
                val = row.get("仅本期观察到的问题", "")
                st.write(val if pd.notna(val) and str(val).strip() else "无")
            with col3:
                st.markdown("#### 本期未观察到的问题")
                val = row.get("本期未观察到的问题", "")
                st.write(val if pd.notna(val) and str(val).strip() else "无")

            st.markdown("#### 下一期优先事项")
            val = row.get("下一期优先事项", "")
            st.write(val if pd.notna(val) and str(val).strip() else "无")

print("APP FINIISH")
if __name__ == "__main__":
    main()
