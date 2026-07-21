class CourseInsightAgent:


    def __init__(self):

        pass



    def run(self, file_path):

        from agent.course_pipeline import run_course_analysis


        result = run_course_analysis(
            file_path
        )


        return result