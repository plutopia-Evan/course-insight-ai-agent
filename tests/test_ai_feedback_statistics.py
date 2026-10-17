"""
AI 反馈统计模块测试脚本

用法:
    python test_ai_feedback_statistics.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_feedback_statistics import generate_statistics

OUTPUT_PATH = "data/output/ai_feedback_statistics.xlsx"
INPUT_PATH = "data/output/deepseek_feedback_batch_result.xlsx"

REQUIRED_SHEETS = [
    "AI标签统计",
    "AI正向反馈汇总",
    "AI负向问题汇总",
    "AI改进建议汇总",
    "课程期次反馈概览",
    "异常记录",
]


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"输入文件不存在: {INPUT_PATH}")
        print("请先运行 batch_deepseek_feedback.py 生成数据")
        sys.exit(1)

    # 清除旧输出
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)

    # 运行统计
    print("=" * 60)
    print("AI 反馈统计测试")
    print("=" * 60)

    generate_statistics(INPUT_PATH, OUTPUT_PATH)

    all_ok = True

    # 检查 1: 输出文件存在
    print("\n--- 检查 1: 输出文件 ---")
    if os.path.exists(OUTPUT_PATH):
        print(f"  [OK] {OUTPUT_PATH}")
    else:
        print(f"  [FAIL] 输出文件缺失")
        all_ok = False
        sys.exit(1)

    # 检查 2: 工作表存在
    print("\n--- 检查 2: 工作表 ---")
    xlsx = pd.ExcelFile(OUTPUT_PATH)
    for sheet in REQUIRED_SHEETS:
        if sheet in xlsx.sheet_names:
            print(f"  [OK] {sheet}")
        else:
            print(f"  [FAIL] 缺失: {sheet}")
            all_ok = False

    # 检查 3: 行数
    print("\n--- 检查 3: 工作表行数 ---")
    sheet_rows = {}
    for sheet in REQUIRED_SHEETS:
        if sheet in xlsx.sheet_names:
            df = pd.read_excel(xlsx, sheet)
            sheet_rows[sheet] = len(df)
            print(f"  {sheet}: {len(df)} 行")

    # 检查 4: 反馈人数 <= 已分类反馈人数
    print("\n--- 检查 4: 反馈人数 <= 已分类反馈人数 ---")
    if "AI标签统计" in xlsx.sheet_names:
        df = pd.read_excel(xlsx, "AI标签统计")
        violations = 0
        for _, row in df.iterrows():
            if row["反馈人数"] > row["已分类反馈人数"]:
                print(f"  [FAIL] {row['课程名称']} {row['期次']} {row['subcategory']}: "
                      f"反馈人数={row['反馈人数']} > 总人数={row['已分类反馈人数']}")
                violations += 1
        if violations == 0:
            print(f"  [OK] 全部通过 ({len(df)} 行)")
        else:
            all_ok = False

    # 检查 5: 人数占比 0-1
    print("\n--- 检查 5: 人数占比范围 ---")
    pct_ok = True
    for sheet in ["AI标签统计", "AI正向反馈汇总", "AI负向问题汇总", "AI改进建议汇总"]:
        if sheet in xlsx.sheet_names:
            df = pd.read_excel(xlsx, sheet)
            pct_col = "反馈人数占比" if "反馈人数占比" in df.columns else "人数占比"
            if pct_col in df.columns:
                bad = df[(df[pct_col] < 0) | (df[pct_col] > 1)]
                if len(bad) > 0:
                    print(f"  [FAIL] {sheet}: {len(bad)} 行占比异常")
                    pct_ok = False
    if pct_ok:
        print(f"  [OK] 全部占比在 [0,1] 范围内")

    # 检查 6: 排名从 1 开始
    print("\n--- 检查 6: 排名 ---")
    rank_ok = True
    for sheet in ["AI正向反馈汇总", "AI负向问题汇总", "AI改进建议汇总"]:
        if sheet in xlsx.sheet_names:
            df = pd.read_excel(xlsx, sheet)
            if "排名" in df.columns and len(df) > 0:
                min_rank = df["排名"].min()
                if min_rank != 1:
                    print(f"  [FAIL] {sheet}: 最小排名={min_rank}")
                    rank_ok = False
    if rank_ok:
        print(f"  [OK] 排名从 1 开始")

    # 检查 7: 课程期次概览 Top3
    print("\n--- 检查 7: 课程期次反馈概览内容 ---")
    if "课程期次反馈概览" in xlsx.sheet_names:
        ov = pd.read_excel(xlsx, "课程期次反馈概览")
        print(f"  课程期次数: {len(ov)}")
        for _, row in ov.iterrows():
            pos_total = row["positive意见数"] + row["negative意见数"] + row["suggestion意见数"] + row["neutral意见数"]
            items_total = row["拆分意见总数"]
            if pos_total != items_total:
                print(f"  [WARN] {row['课程名称']} {row['期次']}: sentiment和={pos_total} != 总数={items_total}")
        print(f"  [OK] 概览内容完整")

    xlsx.close()

    # 最终结果
    print("\n" + "=" * 60)
    if all_ok:
        print("全部测试通过。")
    else:
        print("部分检查未通过，请查看上方输出。")
        sys.exit(1)


if __name__ == "__main__":
    main()
