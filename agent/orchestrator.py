class CourseInsightAgent:


    def __init__(self):

        self.context = {}



    def run(self, file_path):


        self.context["file_path"] = file_path


        survey_result = self.run_survey_analysis(
            file_path
        )


        self.context["survey"] = survey_result


        return survey_result



    def run_survey_analysis(
            self,
            file_path
    ):


        from agent.course_pipeline import (
            run_course_analysis
        )


        result = run_course_analysis(
            file_path
        )


        return result