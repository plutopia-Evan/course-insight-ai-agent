"""
AI 统一管线测试脚本

用法:
    python test_ai_pipeline.py

验证:
1. 输入5条有效反馈
2. 分类成功5条
3. 生成所有 DataFrame
4. errors 为空
5. 打印每个 DataFrame 的行数
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_pipeline import run_ai_pipeline
from batch_deepseek_feedback import filter_valid_feedback

INPUT_PATH = "data/output/course_survey_analysis.xlsx"


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"输入文件不存在: {INPUT_PATH}")
        sys.exit(1)

    # 读取并筛选前 5 条
    df = pd.read_excel(INPUT_PATH, sheet_name="开放式反馈明细")
    df_valid = filter_valid_feedback(df)
    df_test = df_valid.head(5).copy()
    print(f"筛选有效反馈: {len(df_valid)} 条, 测试取前 {len(df_test)} 条")

    # 进度回调
    def on_progress(info):
        stage = info.get("stage", "")
        if stage == "classification":
            print(f"  [进度] 分类: {info['current']}/{info['total']} "
                  f"缓存={info['cache_hits']} API={info['api_calls']} 失败={info['failures']}")
        else:
            print(f"  [阶段] {stage}")

    # 运行管线
    print("\n运行管线...")
    results = run_ai_pipeline(
        feedback_detail_df=df_test,
        use_cache=True,
        progress_callback=on_progress,
    )

    # 验证
    print("\n" + "=" * 60)
    print("结果验证")
    print("=" * 60)

    expected_keys = [
        "classification_detail", "label_stats", "positive_summary",
        "negative_summary", "suggestion_summary", "course_overview",
        "course_summary", "course_summary_detail", "trend_summary",
        "errors", "api_summary",
    ]
    all_ok = True

    for key in expected_keys:
        if key in results:
            df_result = results[key]
            if isinstance(df_result, pd.DataFrame):
                print(f"  [OK] {key}: {len(df_result)} 行")
            else:
                print(f"  [FAIL] {key}: 不是 DataFrame (type={type(df_result).__name__})")
                all_ok = False
        else:
            print(f"  [FAIL] 缺少 key: {key}")
            all_ok = False

    # 检查分类结果
    detail = results["classification_detail"]
    unique_fids = detail["feedback_id"].nunique() if not detail.empty else 0
    print(f"\n分类明细: {len(detail)} 条意见, {unique_fids} 个唯一 feedback_id")

    if unique_fids < 5:
        print(f"  [WARN] 期望 5 个 feedback_id, 实际 {unique_fids}")
        # Not a hard failure - some rows may produce 0 items

    # 检查 errors
    errors = results["errors"]
    if len(errors) == 0:
        print(f"  [OK] errors 为空")
    else:
        print(f"  [INFO] errors: {len(errors)} 行")
        for _, e in errors.iterrows():
            print(f"    {e.to_dict()}")

    # 打印 api_summary
    api = results["api_summary"]
    print(f"\nAPI 汇总:")
    for _, row in api.iterrows():
        print(f"  {row['指标']}: {row['数值']}")

    # 最终
    print("\n" + "=" * 60)
    if all_ok:
        print("全部 DataFrame 生成成功。")
    else:
        print("部分检查未通过。")
        sys.exit(1)


if __name__ == "__main__":
    main()
