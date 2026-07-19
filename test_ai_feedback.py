"""
AI 反馈分类模块测试脚本 (Mock 模式)

验证 mock_analyze_feedback 的关键词规则和输出格式。
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_feedback_analyzer import mock_analyze_feedback, flatten_analysis_results

TEST_FEEDBACKS = [
    {
        "feedback_id": "F001",
        "course_name": "产品经理训练营",
        "session": "第01期",
        "respondent_id": "S001",
        "feedback_text": "老师讲得很好，但是课程节奏太快，希望增加案例。",
    },
    {
        "feedback_id": "F002",
        "course_name": "产品经理训练营",
        "session": "第01期",
        "respondent_id": "S002",
        "feedback_text": "代码演示比较清楚，但课堂练习太少。",
    },
    {
        "feedback_id": "F003",
        "course_name": "数据分析实战课",
        "session": "第02期",
        "respondent_id": "S003",
        "feedback_text": "希望课后资料能够早点发放。",
    },
    {
        "feedback_id": "F004",
        "course_name": "数据分析实战课",
        "session": "第01期",
        "respondent_id": "S004",
        "feedback_text": "内容比较实用。",
    },
    {
        "feedback_id": "F005",
        "course_name": "产品经理训练营",
        "session": "第02期",
        "respondent_id": "S005",
        "feedback_text": "整体还可以。",
    },
]


def main():
    os.makedirs("data/output", exist_ok=True)

    results = []
    print("=" * 60)
    print("AI 反馈分类 Mock 测试")
    print("=" * 60)

    for fb in TEST_FEEDBACKS:
        result = mock_analyze_feedback(
            feedback_id=fb["feedback_id"],
            feedback_text=fb["feedback_text"],
            course_name=fb["course_name"],
            session=fb["session"],
            respondent_id=fb["respondent_id"],
        )
        results.append(result)

        print(f"\n--- {fb['feedback_id']} ---")
        print(f"原始反馈: {fb['feedback_text']}")
        print(f"拆分意见数: {len(result['items'])}")
        for i, item in enumerate(result["items"], 1):
            print(f"  意见{i}: [{item['category']}] {item['subcategory']} "
                  f"| {item['sentiment']} | {item['summary']}")
        print(f"JSON:\n{json.dumps(result, ensure_ascii=False, indent=2)}")

    df = flatten_analysis_results(results)
    print(f"\n展平 DataFrame: {len(df)} 行 x {len(df.columns)} 列")
    print(df.to_string(index=False))

    output_dir = "data/output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "mock_ai_feedback_result.xlsx")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="AI反馈分类明细", index=False)

        worksheet = writer.sheets["AI反馈分类明细"]
        for col_idx, col_name in enumerate(df.columns, 1):
            max_len = max(df[col_name].astype(str).map(len).max(), len(col_name)) + 4
            worksheet.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else "A"].width = min(max_len, 50)

    print(f"\nExcel 已保存: {os.path.abspath(output_path)}")
    print(f"工作表: AI反馈分类明细")

    expected = {
        "F001": 3,
        "F002": 1,
        "F003": 1,
        "F004": 1,
        "F005": 1,
    }
    print("\n--- 验证 ---")
    all_ok = True
    for r in results:
        fid = r["feedback_id"]
        actual = len(r["items"])
        exp = expected[fid]
        status = "OK" if actual == exp else f"FAIL (expected {exp})"
        if actual != exp:
            all_ok = False
        print(f"  {fid}: {actual} 条意见 -> {status}")

    if all_ok:
        print("\n全部测试通过。")
    else:
        print("\n部分测试未通过，请检查。")
        sys.exit(1)


if __name__ == "__main__":
    main()
