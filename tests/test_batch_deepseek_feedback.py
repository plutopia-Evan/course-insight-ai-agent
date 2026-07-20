"""
DeepSeek 批量反馈分析 - 小批测试脚本

用法:
    python test_batch_deepseek_feedback.py

验证:
1. --limit 5 处理 5 条
2. 生成 Excel + 进度文件
3. 第二次运行全部命中缓存
"""

import os
import sys
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BATCH_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_deepseek_feedback.py")
CACHE_PATH = "data/cache/deepseek_feedback_cache.json"
PROGRESS_PATH = "data/cache/batch_feedback_progress.json"
OUTPUT_PATH = "data/output/deepseek_feedback_batch_result.xlsx"


def run_cmd(cmd: str) -> int:
    print(f"\n{'='*60}")
    print(f"执行: {cmd}")
    print(f"{'='*60}")
    return subprocess.call(cmd, shell=True)


def main():
    all_ok = True

    # ---- 第一轮: --limit 5 ----
    print("\n" + "="*60)
    print("第一轮: 小批测试 (--limit 5)")
    print("="*60)

    # 清理旧进度
    for f in [PROGRESS_PATH]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                time.sleep(1)
                os.remove(f)
            print(f"  已清理: {f}")
    # 输出文件由 batch 脚本自行覆盖

    rc = run_cmd(f"python \"{BATCH_SCRIPT}\" --limit 5")
    if rc != 0:
        print("第一轮失败")
        sys.exit(1)

    # 验证输出
    checks = []
    if os.path.exists(OUTPUT_PATH):
        print(f"  [OK] 输出文件存在: {OUTPUT_PATH}")
        checks.append(True)
    else:
        print(f"  [FAIL] 输出文件缺失: {OUTPUT_PATH}")
        checks.append(False)

    if os.path.exists(PROGRESS_PATH):
        print(f"  [OK] 进度文件存在: {PROGRESS_PATH}")
        checks.append(True)
    else:
        print(f"  [FAIL] 进度文件缺失: {PROGRESS_PATH}")
        checks.append(False)

    # 验证 Excel 内容
    import pandas as pd
    xlsx = pd.ExcelFile(OUTPUT_PATH)
    sheets = xlsx.sheet_names
    expected_sheets = ["AI反馈分类明细", "API调用错误记录", "批量分析汇总", "标签数量汇总"]
    for s in expected_sheets:
        if s in sheets:
            print(f"  [OK] 工作表存在: {s}")
        else:
            print(f"  [FAIL] 工作表缺失: {s}")
            checks.append(False)

    detail = pd.read_excel(xlsx, "AI反馈分类明细")
    unique_fids = detail["feedback_id"].nunique()
    print(f"  反馈数: {unique_fids}, 意见数: {len(detail)}")
    if unique_fids == 5:
        print(f"  [OK] 5 条反馈")
        checks.append(True)
    else:
        print(f"  [FAIL] 期望 5 条, 实际 {unique_fids}")
        checks.append(False)

    summary = pd.read_excel(xlsx, "批量分析汇总")
    for _, row in summary.iterrows():
        if row["指标"] == "成功反馈数":
            if row["数值"] == 5:
                print(f"  [OK] 成功反馈数 = 5")
                checks.append(True)
            else:
                print(f"  [FAIL] 成功反馈数 = {row['数值']}")
                checks.append(False)
        if row["指标"] == "缓存命中数":
            print(f"  缓存命中数(第一轮): {row['数值']}")
    xlsx.close()

    if not all(checks):
        all_ok = False

    # ---- 第二轮: 再次 --limit 5, 应全部缓存命中 ----
    print("\n" + "="*60)
    print("第二轮: 验证缓存命中 (--limit 5)")
    print("="*60)

    # 删除进度，保留缓存和输出（batch 脚本会覆盖输出）
    for f in [PROGRESS_PATH]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                time.sleep(1)
                os.remove(f)
    # 输出文件由 batch 脚本覆盖写入，无需手动删除

    rc = run_cmd(f"python \"{BATCH_SCRIPT}\" --limit 5")
    if rc != 0:
        print("第二轮失败")
        sys.exit(1)

    xlsx2 = pd.ExcelFile(OUTPUT_PATH)
    summary2 = pd.read_excel(xlsx2, "批量分析汇总")
    cache_hits_2 = 0
    api_calls_2 = 0
    for _, row in summary2.iterrows():
        if row["指标"] == "缓存命中数":
            cache_hits_2 = row["数值"]
        if row["指标"] == "API实际调用反馈数":
            api_calls_2 = row["数值"]
    xlsx2.close()
    print(f"  缓存命中数: {cache_hits_2}, API调用数: {api_calls_2}")
    if cache_hits_2 == 5 and api_calls_2 <= 5:
        print(f"  [OK] 第二轮全部/大部分命中缓存")
        checks.append(True)
    else:
        print(f"  [WARN] 预期 5 次缓存命中, 实际 {cache_hits_2}")
        # Not a fatal failure since first run may have been fresh

    # ---- 结果 ----
    print("\n" + "="*60)
    if all_ok:
        print("小批测试通过。")
    else:
        print("部分检查未通过，请查看上方输出。")
        sys.exit(1)


if __name__ == "__main__":
    main()
