from agent.survey_agent import SurveyAgent
from agent.statistics_agent import StatisticsAgent
from agent.feedback_agent import FeedbackAgent
from agent.report_agent import ReportAgent



class CourseInsightAgent:


    def __init__(self):

        # 初始化各个Agent

        self.survey_agent = SurveyAgent()

        self.statistics_agent = StatisticsAgent()

        self.feedback_agent = FeedbackAgent()

        self.report_agent = ReportAgent()



    def run(
        self,
        file_path
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
            survey_result
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