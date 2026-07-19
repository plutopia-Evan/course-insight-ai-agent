# Course Insight AI Agent Tools Config


# 1. Project Information


## Project Name

Course Insight AI Agent


## Description

Course Insight AI Agent is an intelligent course operation analysis system.

The system integrates:

- Excel data processing
- Statistical analysis
- LLM-based feedback understanding
- Automated report generation

to transform raw course questionnaire data into actionable operation insights.



---

# 2. Tool Overview


| Tool Name | Function | API |
|---|---|---|
| course_analysis | Course questionnaire analysis | POST /analysis |
| feedback_analysis | Student feedback intelligence analysis | POST /feedback_analysis |
| report_generation | Automated report generation | POST /generate_report |



---


# Tool 1: course_analysis


## Tool Name

course_analysis


## Purpose

Analyze course questionnaire Excel files and extract structured course performance metrics.


## Description

This tool processes uploaded questionnaire Excel files.

It automatically performs:

- Course information extraction
- Session identification
- Questionnaire parsing
- Question mapping
- Score calculation
- Data quality checking
- Abnormal response detection


## When To Use

Call this tool when:

- User uploads a course questionnaire Excel file
- User asks about course performance
- User wants satisfaction statistics
- User needs student participation information
- User wants to identify abnormal questionnaire data


## API Endpoint

```
POST /analysis
```


## Input Schema


```json
{
  "file_path": "data/input/course_questionnaire.xlsx"
}
```


## Input Parameters


| Parameter | Type | Description |
|---|---|---|
| file_path | string | Path of questionnaire Excel file |


## Output Schema


```json
{
  "course_name": "产品经理训练营",
  "session": "第01期",
  "student_count": 32,
  "average_score": 4.56,
  "feedback_count": 32,
  "anomaly_count": 10
}
```


## Output Description


| Field | Description |
|---|---|
| course_name | Course name |
| session | Course session |
| student_count | Number of students |
| average_score | Average satisfaction score |
| feedback_count | Number of text feedback |
| anomaly_count | Number of abnormal records |



---


# Tool 2: feedback_analysis


## Tool Name

feedback_analysis


## Purpose

Analyze open-ended student feedback and extract course improvement insights.


## Description

This tool uses LLM-based analysis to understand student comments.

It performs:

- Sentiment analysis
- Feedback classification
- Problem identification
- Root cause extraction
- Improvement suggestion generation


## When To Use

Call this tool when:

- User wants to understand student opinions
- User asks why students are satisfied or dissatisfied
- User wants course improvement suggestions
- User needs feedback summarization


## API Endpoint

```
POST /feedback_analysis
```


## Input Schema


```json
{
  "course_name": "产品经理训练营",
  "session": "第01期",
  "feedback_texts": [
    "老师讲解非常清晰",
    "希望增加更多项目案例"
  ]
}
```


## Input Parameters


| Parameter | Type | Description |
|---|---|---|
| course_name | string | Course name |
| session | string | Course session |
| feedback_texts | array[string] | List of student comments |


## Output Schema


```json
{
  "course_name": "产品经理训练营",
  "session": "第01期",
  "feedback_count": 2,
  "analysis": [
    {
      "category": "实操与案例",
      "subcategory": "案例不足",
      "sentiment": "negative",
      "summary": "学生希望增加企业案例",
      "evidence": "希望增加更多项目案例"
    }
  ]
}
```


## Output Description


| Field | Description |
|---|---|
| category | Feedback category |
| subcategory | Specific issue |
| sentiment | Positive/Negative/Neutral |
| summary | AI generated summary |
| evidence | Original feedback evidence |



---


# Tool 3: report_generation


## Tool Name

report_generation


## Purpose

Generate complete course analysis reports automatically.


## Description

This tool integrates:

- Questionnaire processing
- Statistical analysis
- Feedback analysis
- Report generation

and outputs a structured Excel analysis report.


## When To Use

Call this tool when:

- User requests a complete course report
- User wants downloadable analysis results
- User needs course review materials
- User wants management presentation data


## API Endpoint

```
POST /generate_report
```


## Input Schema


```json
{
  "file_path": "data/input/course_questionnaire.xlsx"
}
```


## Input Parameters


| Parameter | Type | Description |
|---|---|---|
| file_path | string | Questionnaire Excel path |


## Output Schema


```json
{
  "status": "success",
  "course_name": "产品经理训练营",
  "session": "第01期",
  "file_path": "data/output/report.xlsx"
}
```


## Output Description


| Field | Description |
|---|---|
| status | Generation status |
| course_name | Course name |
| session | Course session |
| file_path | Generated report path |



---


# 3. Agent Tool Calling Strategy


## Scenario 1: User uploads questionnaire file


Example:

"帮我分析这个课程问卷"


Agent Action:


```
Call:

course_analysis
```



---


## Scenario 2: User asks about feedback problems


Example:

"学生为什么觉得课程不好？"


Agent Action:


```
Call:

feedback_analysis
```



---


## Scenario 3: User requests report


Example:

"生成课程分析报告"


Agent Action:


```
Call:

report_generation
```



---


## Scenario 4: Complete Course Analysis


Example:

"分析产品经理训练营第一期，并生成优化报告"


Agent Workflow:


```
Step 1:

course_analysis


        ↓


Step 2:

feedback_analysis


        ↓


Step 3:

report_generation

```



---


# 4. Agent Architecture


```
                    User


                      ↓


          Course Insight AI Agent


                      ↓


          Tool Calling Decision


                      ↓


 ------------------------------------------------

        |                 |                 |

        ↓                 ↓                 ↓


course_analysis   feedback_analysis   report_generation


        |                 |                 |


        ↓                 ↓                 ↓


 Excel Parser       LLM Analysis      Excel Generator


                      ↓


              Course Insight Report

```



---


# 5. Tool Usage Principles


1. Always analyze structured questionnaire data before generating conclusions.


2. Use feedback_analysis when qualitative opinions are required.


3. Use report_generation only after required analysis information is available.


4. Maintain course_name and session context throughout the workflow.


5. Final responses should provide:

- Key findings
- Main problems
- Optimization suggestions
- Report path (if generated)
