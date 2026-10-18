from agent.survey_agent import SurveyAgent
from agent.statistics_agent import StatisticsAgent
from agent.feedback_agent import FeedbackAgent
from agent.report_agent import ReportAgent
from core.analysis_summary import build_analysis_summary



class CourseInsightAgent:


    def __init__(self, feedback_analyzer=None):

        # 初始化各个Agent

        self.survey_agent = SurveyAgent()

        self.statistics_agent = StatisticsAgent()

        self.feedback_agent = FeedbackAgent(feedback_analyzer)

        self.report_agent = ReportAgent()



    def run(
        self,
        file_path,
        *,
        max_feedback_count=None,
        max_feedback_chars=None,
    ):


        # ==========================
        # Step 1
        # Survey Agent
        #
        # 作用：
        # Excel读取
        # 数据清洗
        # 宽转长
        # 问题标准化
        # ==========================

        survey_result = self.survey_agent.run(
            file_path
        )



        # ==========================
        # Step 2
        # Statistics Agent
        #
        # 作用：
        # 评分统计
        # 异常检测
        # 指标计算
        # ==========================

        statistics_result = self.statistics_agent.run(
            survey_result
        )



        # ==========================
        # Step 3
        # Feedback Agent
        #
        # 作用：
        # 文本反馈分析
        # 情感分析
        # 问题分类
        # ==========================

        feedback_result = self.feedback_agent.run(
            survey_result,
            max_feedback_count=max_feedback_count,
            max_feedback_chars=max_feedback_chars,
        )



        # ==========================
        # Step 4
        # 合并前三个Agent结果
        #
        # 给ReportAgent使用
        # ==========================

        context = {

            **survey_result,

            **statistics_result,

            **feedback_result

        }

        summary = build_analysis_summary(
            survey_result["df_long"],
            statistics_result["valid_rating"],
            statistics_result["anomalies"],
            feedback_result["feedback_results"],
            feedback_result["feedback_errors"],
            feedback_result["feedback_skipped_count"],
        )
        context["summary"] = summary
        context.update(summary)



        # ==========================
        # Step 5
        # Report Agent
        #
        # 作用：
        # 生成Excel报告
        # ==========================

        report_result = self.report_agent.run(
            context
        )



        # ==========================
        # Step 6
        # 返回最终结果
        # ==========================

        final_result = {

            **context,

            **report_result

        }


        return final_result
