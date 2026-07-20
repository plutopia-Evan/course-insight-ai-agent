"""
DeepSeek 反馈分类模块测试脚本

用法:
    python test_deepseek_feedback.py

前提: 需在 .env 中配置 DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deepseek_feedback_analyzer import (
    deepseek_analyze_feedback,
    flatten_deepseek_results,
)

TEST_FEEDBACKS = [
    {"feedback_id": "F001", "respondent_id": "U001",
     "feedback_text": "老师讲得很好，但是课程节奏太快，希望增加案例。"},
    {"feedback_id": "F002", "respondent_id": "U002",
     "feedback_text": "代码演示比较清楚，但课堂练习太少。"},
    {"feedback_id": "F003", "respondent_id": "U003",
     "feedback_text": "希望课后资料能够早点发放。"},
    {"feedback_id": "F004", "respondent_id": "U004",
     "feedback_text": "内容比较实用。"},
    {"feedback_id": "F005", "respondent_id": "U005",
     "feedback_text": "整体还可以。"},
]


def main():
    # 检查配置
    try:
        import deepseek_config as cfg
    except ValueError as e:
        print(f"配置错误: {e}")
        sys.exit(1)
    except ImportError:
        print("错误: 无法导入 deepseek_config.py，请确保 python-dotenv 已安装。")
        sys.exit(1)

    print("=" * 60)
    print("DeepSeek 反馈分类测试")
    print(f"Model: {cfg.DEEPSEEK_MODEL}")
    print(f"Base URL: {cfg.DEEPSEEK_BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ---- 缓存损坏测试 ----
    print("\n--- 缓存损坏测试 ---")
    import glob as _glob
    from deepseek_feedback_analyzer import _cache_dir, _cache_path, _load_cache, _save_cache
    from deepseek_feedback_analyzer import deepseek_analyze_feedback as _analyze

    os.makedirs(_cache_dir(), exist_ok=True)
    cache_path = _cache_path()

    # 清理旧损坏备份
    for old_broken in _glob.glob(os.path.join(_cache_dir(), "deepseek_feedback_cache.broken_*.json")):
        os.remove(old_broken)
        print(f"  清理旧备份: {os.path.basename(old_broken)}")

    # 写入非法 JSON
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write("NOT VALID JSON {{{")
    print(f"  已写入非法缓存: {cache_path}")

    # 尝试加载，应自动备份并返回空字典
    loaded = _load_cache()
    assert loaded == {}, f"损坏缓存应返回空字典，实际: {loaded}"
    print(f"  _load_cache 返回空字典: OK")

    # 验证备份文件已创建
    broken_files = _glob.glob(os.path.join(_cache_dir(), "deepseek_feedback_cache.broken_*.json"))
    assert len(broken_files) >= 1, "应生成损坏备份文件"
    print(f"  备份文件已生成: {os.path.basename(broken_files[0])}")

    # 验证旧缓存文件已被移除(或已被重命名)
    assert not os.path.exists(cache_path), "损坏的缓存文件应已被重命名移除"

    # 用正常缓存覆盖，确保后续测试可用
    _save_cache({})
    print(f"  缓存已重置为空")
    print("  缓存损坏测试: 全部通过")
    print("-" * 60)

    results = []
    errors_list = []
    cache_hits = 0
    api_calls = 0
    total_retries = 0

    for fb in TEST_FEEDBACKS:
        result = deepseek_analyze_feedback(
            feedback_id=fb["feedback_id"],
            feedback_text=fb["feedback_text"],
            course_name="测试课程",
            session="第01期",
            respondent_id=fb["respondent_id"],
        )
        results.append(result)

        print(f"\n--- {fb['feedback_id']} ---")
        print(f"原始反馈: {fb['feedback_text']}")

        if result.get("_cache_hit"):
            cache_hits += 1
            print(f"  [缓存命中]")

        if result.get("_error"):
            print(f"  !! 错误: {result['_error']}")
            errors_list.append({
                "feedback_id": fb["feedback_id"],
                "respondent_id": fb["respondent_id"],
                "feedback_text": fb["feedback_text"],
                "错误类型": "API调用失败",
                "错误详情": result["_error"],
                "重试次数": result.get("_retries", 0),
            })
            if not result.get("_cache_hit"):
                api_calls += result.get("_retries", 3)
                total_retries += result.get("_retries", 0)
        else:
            if not result.get("_cache_hit"):
                api_calls += 1
                total_retries += result.get("_retries", 0)
            print(f"  拆分意见数: {len(result['items'])}")
            for i, item in enumerate(result["items"], 1):
                print(f"  意见{i}: [{item['category']}] {item['subcategory']} "
                      f"| {item['sentiment']} | {item['summary']}")

    # 统计
    input_count = len(TEST_FEEDBACKS)
    success_count = sum(1 for r in results if not r.get("_error"))
    fail_count = len(errors_list)
    total_items = sum(len(r.get("items", [])) for r in results)

    print("\n" + "=" * 60)
    print(f"测试汇总: 输入 {input_count} | 成功 {success_count} | 失败 {fail_count}")
    print(f"缓存命中 {cache_hits} | API 调用 {api_calls} | 重试 {total_retries}")
    print(f"拆分意见总数: {total_items}")
    print("=" * 60)

    # 生成 Excel
    print("\n正在生成 Excel ...")
    os.makedirs("data/output", exist_ok=True)
    output_path = "data/output/deepseek_feedback_test_result.xlsx"

    detail_df = flatten_deepseek_results(results)

    summary_rows = [
        {"指标": "输入反馈数", "数值": input_count},
        {"指标": "成功数", "数值": success_count},
        {"指标": "失败数", "数值": fail_count},
        {"指标": "缓存命中数", "数值": cache_hits},
        {"指标": "API实际调用数", "数值": api_calls},
        {"指标": "拆分意见总数", "数值": total_items},
        {"指标": "模型", "数值": cfg.DEEPSEEK_MODEL},
        {"指标": "测试时间", "数值": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
    ]
    summary_df = pd.DataFrame(summary_rows)

    err_df = pd.DataFrame(errors_list) if errors_list else pd.DataFrame(
        columns=["feedback_id", "respondent_id", "feedback_text", "错误类型", "错误详情", "重试次数"]
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name="AI反馈分类明细", index=False)
        err_df.to_excel(writer, sheet_name="API调用错误记录", index=False)
        summary_df.to_excel(writer, sheet_name="测试汇总", index=False)

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
    print(f"  工作表: AI反馈分类明细, API调用错误记录, 测试汇总")

    if fail_count > 0:
        print("\n部分调用失败，详见 Excel 'API调用错误记录' 工作表。")
        sys.exit(1)
    else:
        print("\n全部调用完成。")


if __name__ == "__main__":
    main()
