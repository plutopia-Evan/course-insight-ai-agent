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
        st.caption(f"分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
