class SurveyAgent:


    def run(self, file_path):

        from core.survey_processor import (
            read_survey_file,
            load_question_mapping,
            wide_to_long,
            map_questions
        )


        (
            course_name,
            session,
            df,
            question_headers,
            meta_headers

        ) = read_survey_file(
            file_path
        )


        mapping = load_question_mapping(
            "config/question_mapping.xlsx"
        )


        df_long = wide_to_long(
            df,
            question_headers
        )


        df_long = map_questions(
            df_long,
            mapping
        )

        return {

            "course_name":
                course_name,

            "session":
                session,

            "df_long":
                df_long,

            "file_path":
                file_path

        }