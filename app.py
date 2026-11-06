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
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from io import BytesIO

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.survey_processor import (
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
from core.statistics import (
    compute_global_common_stats,
    compute_course_common_stats,
    compute_period_specific_stats,
    compute_session_stats,
    compute_overview_stats,
    compute_feedback_overview,
)
from core.text_cleaner import (
    clean_text_feedback,
    generate_feedback_summary,
)
from core.output_writer import (
    write_output_excel,
    build_file_identification,
    build_pending_review,
    build_feedback_frequency,
)
from scripts.ai_pipeline import run_ai_pipeline
from core.batch_service import run_base_analysis, run_batch_analysis, run_feedback_analysis
from core.examples import sample_uploads

load_dotenv()


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
    progress = st.empty()
    try:
        return run_base_analysis(survey_files, mapping_file, temp_dir, progress=progress.info)
    finally:
        progress.empty()


def main():
    st.title("📊 课程问卷智能分析工具")
    st.markdown("上传课程问卷 Excel 文件，自动完成题目映射、评分统计、文本清洗，一键下载分析报告。")

    st.sidebar.header("📋 使用说明")
    st.sidebar.markdown("""
    1. 上传问卷 Excel 文件（可多选）
    2. 使用内置映射或上传自定义映射
    3. 选择是否做 AI，点击“生成课程复盘”
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
            "📁 自定义题目映射（可选）",
            type=["xlsx"],
            accept_multiple_files=False,
            help="上传 question_mapping.xlsx",
        )

    default_mapping = Path("config/question_mapping.xlsx").read_bytes()
    st.download_button("下载题目映射模板", default_mapping, file_name="question_mapping.xlsx")
    if uploaded_mapping is None:
        st.caption("当前使用内置题目映射；新题目会进入人工待确认列表。")
    use_example = st.checkbox("使用合成示例数据体验")
    if use_example:
        uploaded_surveys = sample_uploads()
        st.info("当前为合成演示问卷，不代表真实课程效果或模型准确率。")
    configured_ai = all(os.getenv(key) for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"))
    run_ai_now = st.checkbox("本次同时分析文字反馈", value=False, disabled=not configured_ai,
                             help="勾选后一次完成基础统计与 AI 分析，会调用模型服务。")
    if not configured_ai:
        st.caption("服务尚未配置 AI，仍可生成基础统计报告。")

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

    can_analyze = bool(uploaded_surveys)
    if uploaded_surveys:
        parts = [(file.name, file.getvalue()) for file in uploaded_surveys]
        mapping_bytes = uploaded_mapping.getvalue() if uploaded_mapping else default_mapping
        fingerprint = hashlib.sha256(mapping_bytes + b"".join(name.encode("utf-8") + data for name, data in parts)).hexdigest()
        if st.session_state.get("input_fingerprint") != fingerprint:
            for name in ("analysis_done", "base_analysis_done", "ai_analysis_done"):
                st.session_state[name] = False
            for name in ("results", "base_results", "ai_results", "xlsx_bytes", "base_xlsx_bytes", "complete_xlsx_bytes"):
                st.session_state[name] = None
            st.session_state.input_fingerprint = fingerprint
    elif st.session_state.get("input_fingerprint"):
        for name in ("analysis_done", "base_analysis_done", "ai_analysis_done"):
            st.session_state[name] = False
        for name in ("results", "base_results", "ai_results", "xlsx_bytes", "base_xlsx_bytes", "complete_xlsx_bytes"):
            st.session_state[name] = None
        st.session_state.input_fingerprint = None

    if st.button("🚀 生成课程复盘", type="primary", disabled=not can_analyze, use_container_width=True):
        if not uploaded_surveys:
            st.error("请先上传问卷文件")
            return

        survey_names = [f.name for f in uploaded_surveys]
        seen = set()
        dupes = [n for n in survey_names if n in seen or seen.add(n)]
        if dupes:
            st.error(f"检测到同名文件: {dupes}，请移除重复文件后重新上传。")
            return

        temp_dir = tempfile.mkdtemp(prefix="survey_analysis_")
        try:
            survey_files = [(f.name, f.getvalue()) for f in uploaded_surveys]
            mapping_file = (uploaded_mapping.name, uploaded_mapping.getvalue()) if uploaded_mapping else ("question_mapping.xlsx", default_mapping)

            with st.spinner("正在分析中，请稍候..."):
                results = run_batch_analysis(survey_files, mapping_file, temp_dir, enable_ai=run_ai_now)

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
            st.session_state.ai_analysis_done = run_ai_now
            st.session_state.ai_results = results.get("ai_results")
            st.session_state.complete_xlsx_bytes = results["complete_xlsx_bytes"] if run_ai_now else None

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
        pending = results.get("pending_review")
        if pending is not None and not pending.empty:
            st.warning(f"有 {len(pending)} 项数据需要人工确认，请先查看再使用结论。")
            with st.expander("查看人工待确认项", expanded=True):
                st.dataframe(pending, use_container_width=True)
        st.caption("反馈标签占比以成功分类的去重反馈学员为分母；不等于全班满意度。优先级仍需结合样本量、严重程度和整改成本人工判断。")

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

        enable_ai = configured_ai and not st.session_state.ai_analysis_done

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
    try:
        with st.spinner("正在分析文字反馈并生成报告..."):
            ai, report = run_feedback_analysis(
                st.session_state.base_results["feedback_detail"],
                st.session_state.base_xlsx_bytes,
            )
        st.session_state.ai_results = ai
        st.session_state.complete_xlsx_bytes = report
        st.session_state.ai_analysis_done = True
        st.rerun()
    except Exception as exc:
        st.error(f"AI 分析未完成，基础报告仍可下载：{exc}")


def _render_ai_tabs(ai_results):
    review = ai_results.get("review_plan")
    if review is not None and not review.empty:
        with st.expander("建议人工审核：确认严重程度、整改成本和负责人"):
            st.dataframe(review, use_container_width=True)
            st.caption("可下载报告，在“建议人工审核”工作表中填写决策；频率排序不会自动替代人工决策。")
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
