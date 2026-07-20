from agent.course_pipeline import run_course_analysis


result = run_course_analysis(
    "data/input/产品经理训练营_第01期.xlsx"
)


print(result.keys())

print(
    result["course_name"]
)

print(
    len(result["feedback_results"])
)
