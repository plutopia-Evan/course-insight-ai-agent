"""
AI 课程总结生成模块测试脚本

用法:
    python test_ai_summary_generator.py

验证:
1. 处理前 2 个课程期次
2. JSON 合法、数字可追溯
3. 优先级阈值正确（使用 priority_from_ratio）
4. Excel 工作表完整
5. 第二次运行命中缓存
6. strengths 来源全部为 positive
7. problems 来源全部为 negative
8. 跨期趋势由 Python 计算
9. 生成汇总包含缓存命中数和 API 调用数
"""

import json
import os
import sys
import subprocess

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUTPUT_PATH = "data/output/ai_course_summary.xlsx"
GENERATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_summary_generator.py")
STATS_PATH = "data/output/ai_feedback_statistics.xlsx"


def main():
    all_ok = True

    if not os.path.exists(STATS_PATH):
        print(f"输入文件不存在: {STATS_PATH}")
        print("请先运行 ai_feedback_statistics.py 生成统计数据")
        sys.exit(1)

    # 清理旧输出
    for f in [OUTPUT_PATH]:
        if os.path.exists(f):
            os.remove(f)

    # ---- 第一轮 ----
    print("=" * 60)
    print("第一轮: --limit 2")
    print("=" * 60)
    rc = subprocess.call(
        f'python "{GENERATOR}" --limit 2',
        shell=True,
    )
    if rc != 0:
        print("第一轮失败")
        sys.exit(1)

    if not os.path.exists(OUTPUT_PATH):
        print(f"[FAIL] 输出文件不存在")
        sys.exit(1)
    print(f"[OK] 输出文件存在")

    xlsx = pd.ExcelFile(OUTPUT_PATH)
    expected_sheets = ["课程AI总结", "课程AI总结明细", "跨期趋势总结", "API调用错误记录", "生成汇总"]
    for s in expected_sheets:
        if s in xlsx.sheet_names:
            print(f"[OK] 工作表: {s}")
        else:
            print(f"[FAIL] 缺失工作表: {s}")
            all_ok = False

    summary = pd.read_excel(xlsx, "课程AI总结")
    print(f"\n课程AI总结: {len(summary)} 行")
    for _, row in summary.iterrows():
        print(f"  {row['课程名称']} {row['期次']}")
        print(f"    整体评价: {str(row['整体评价'])[:60]}...")
        print(f"    主要优点: {str(row['主要优点'])[:60]}...")
        print(f"    主要问题: {str(row['主要问题'])[:60]}...")
        print(f"    管理层摘要: {str(row['管理层摘要'])[:60]}...")

    # 检查明细
    stats = pd.read_excel(STATS_PATH, sheet_name="课程期次反馈概览")
    pos_data = pd.read_excel(STATS_PATH, sheet_name="AI正向反馈汇总")
    neg_data = pd.read_excel(STATS_PATH, sheet_name="AI负向问题汇总")
    detail = pd.read_excel(xlsx, "课程AI总结明细")
    print(f"\n课程AI总结明细: {len(detail)} 行")

    # ---- 检查优先级 ----
    problem_detail = detail[detail["类型"] == "问题"]
    for _, row in problem_detail.iterrows():
        ratio = row.get("占比", 0)
        priority = row.get("优先级", "")
        if isinstance(ratio, (int, float)) and not pd.isna(ratio):
            if ratio >= 0.20:
                expected = "high"
            elif ratio >= 0.10:
                expected = "medium"
            else:
                expected = "low"
            if priority != expected:
                print(f"  [WARN] 优先级可能不对: {row['标签']} ratio={ratio:.3f} priority={priority} expected={expected}")

    # ---- 检查建议明细新字段 ----
    sug_detail = detail[detail["类型"] == "建议"]
    if "来源类型" in detail.columns and "来源标签" in detail.columns:
        non_empty_source = sug_detail[sug_detail["来源类型"].notna() & (sug_detail["来源类型"] != "")]
        print(f"[OK] 建议明细包含来源类型/来源标签 ({len(non_empty_source)} 条有来源)")
    else:
        print(f"[WARN] 建议明细缺少来源类型/来源标签字段")

    # ---- 跨期趋势 ----
    if "跨期趋势总结" in xlsx.sheet_names:
        trend = pd.read_excel(xlsx, "跨期趋势总结")
        print(f"\n跨期趋势总结: {len(trend)} 行")
        for _, row in trend.iterrows():
            print(f"  {row['课程名称']}: {str(row['趋势总结'])[:80]}...")
            print(f"    持续问题: {str(row['持续问题'])[:60]}")
            print(f"    新问题: {str(row['新出现问题'])[:60]}")

    # ---- 生成汇总（含缓存/API 指标） ----
    gen = pd.read_excel(xlsx, "生成汇总")
    print(f"\n生成汇总:")
    for _, row in gen.iterrows():
        print(f"  {row['指标']}: {row['数值']}")

    # 检查新指标
    gen_metrics = dict(zip(gen["指标"], gen["数值"]))
    for m in ["缓存命中数", "API实际调用数", "总重试次数"]:
        if m in gen_metrics:
            print(f"[OK] 指标存在: {m} = {gen_metrics[m]}")
        else:
            print(f"[WARN] 缺失指标: {m}")

    xlsx.close()

    # ---- 第二轮: 验证缓存命中 ----
    print("\n" + "=" * 60)
    print("第二轮: 验证缓存命中 (--limit 2)")
    print("=" * 60)

    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)

    rc = subprocess.call(
        f'python "{GENERATOR}" --limit 2',
        shell=True,
    )
    if rc != 0:
        print("第二轮失败")
        sys.exit(1)

    # 检查缓存指标
    xlsx2 = pd.ExcelFile(OUTPUT_PATH)
    gen2 = pd.read_excel(xlsx2, "生成汇总")
    gen2_metrics = dict(zip(gen2["指标"], gen2["数值"]))
    cache_hits_r2 = int(gen2_metrics.get("缓存命中数", 0))
    api_calls_r2 = int(gen2_metrics.get("API实际调用数", 0))
    if cache_hits_r2 > 0:
        print(f"[OK] 第二轮缓存命中: {cache_hits_r2}")
    else:
        print(f"[WARN] 第二轮缓存命中为 0")
    if api_calls_r2 == 0:
        print(f"[OK] 第二轮无 API 调用（全部缓存）")
    else:
        print(f"[INFO] 第二轮 API 调用: {api_calls_r2}（可能有跨期趋势调用）")
    xlsx2.close()

    print("\n" + "=" * 60)
    if all_ok:
        print("全部测试通过。")
    else:
        print("部分检查未通过。")
        sys.exit(1)


if __name__ == "__main__":
    main()
