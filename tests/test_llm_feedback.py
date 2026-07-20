"""
LLM 反馈分类模块测试脚本

用法:
    python test_llm_feedback.py

前提: 需在 .env 中配置 LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_feedback_analyzer import llm_analyze_feedback, flatten_analysis_results

TEST_FEEDBACKS = [
    {"feedback_id": "F001", "feedback_text": "老师讲得很好，但是课程节奏太快，希望增加案例。"},
    {"feedback_id": "F002", "feedback_text": "代码演示比较清楚，但课堂练习太少。"},
    {"feedback_id": "F003", "feedback_text": "希望课后资料能够早点发放。"},
    {"feedback_id": "F004", "feedback_text": "内容比较实用。"},
    {"feedback_id": "F005", "feedback_text": "整体还可以。"},
]


def main():
    # 检查 .env 配置
    try:
        import config as cfg
    except ValueError as e:
        print(f"配置错误: {e}")
        sys.exit(1)
    except ImportError:
        print("错误: 无法导入 config.py，请确保 python-dotenv 已安装。")
        sys.exit(1)

    print("=" * 60)
    print("LLM 反馈分类测试")
    print(f"Model: {cfg.LLM_MODEL}")
    print(f"Base URL: {cfg.LLM_BASE_URL}")
    print("=" * 60)

    results = []
    errors_list = []

    for fb in TEST_FEEDBACKS:
        result = llm_analyze_feedback(
            feedback_id=fb["feedback_id"],
            feedback_text=fb["feedback_text"],
        )
        results.append(result)

        print(f"\n--- {fb['feedback_id']} ---")
        print(f"原始反馈: {fb['feedback_text']}")

        if result.get("_error"):
            print(f"  !! 错误: {result['_error']}")
            errors_list.append({
                "feedback_id": fb["feedback_id"],
                "feedback_text": fb["feedback_text"],
                "error": result["_error"],
            })
        else:
            print(f"  拆分意见数: {len(result['items'])}")
            for i, item in enumerate(result["items"], 1):
                print(f"  意见{i}: [{item['category']}] {item['subcategory']} "
                      f"| {item['sentiment']} | {item['summary']}")

    print("\n" + "=" * 60)
    print("正在生成 Excel ...")

    os.makedirs("data/output", exist_ok=True)
    output_path = "data/output/llm_feedback_test_result.xlsx"

    detail_rows = flatten_analysis_results(results)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail_rows.to_excel(writer, sheet_name="AI反馈分类明细", index=False)

        if errors_list:
            err_df = pd.DataFrame(errors_list)
            err_df.to_excel(writer, sheet_name="调用错误记录", index=False)
        else:
            err_df = pd.DataFrame(columns=["feedback_id", "feedback_text", "error"])
            err_df.to_excel(writer, sheet_name="调用错误记录", index=False)

        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_idx in range(1, ws.max_column + 1):
                col_letter = chr(64 + col_idx) if col_idx <= 26 else "A"
                max_len = 8
                for row_idx in range(1, min(ws.max_row + 1, 200)):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    print(f"Excel 已保存: {os.path.abspath(output_path)}")
    print(f"  工作表: {writer.sheets.keys() if hasattr(writer, 'sheets') else ['AI反馈分类明细', '调用错误记录']}")

    success_count = sum(1 for r in results if not r.get("_error"))
    fail_count = len(errors_list)
    print(f"\n成功: {success_count}, 失败: {fail_count}")
    if fail_count > 0:
        print("部分调用失败，详见 Excel '调用错误记录' 工作表。")
    else:
        print("全部调用完成。")


if __name__ == "__main__":
    main()
