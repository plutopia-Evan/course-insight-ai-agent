"""Make one uncached DeepSeek classification call with non-sensitive sample text."""

from llm.deepseek_feedback_analyzer import deepseek_analyze_feedback


def main() -> int:
    try:
        import deepseek_config as config
    except ValueError as exc:
        print(f"无法开始真实模型验收：{exc}")
        return 2

    if config.DEEPSEEK_API_KEY.startswith("your_"):
        print("无法开始真实模型验收：请先填写真实的 DEEPSEEK_API_KEY")
        return 2

    result = deepseek_analyze_feedback(
        feedback_id="smoke-1",
        feedback_text="老师讲解清晰，但课程节奏太快。",
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        model=config.DEEPSEEK_MODEL,
        max_retries=1,
        timeout=20,
        use_cache=False,
    )
    if result.get("_error") or not result.get("items"):
        print("真实模型验收失败：未得到通过标签和原文证据校验的意见")
        return 1

    labels = [f"{item['subcategory']} ({item['sentiment']})" for item in result["items"]]
    print(f"真实模型验收通过：{len(labels)} 条意见；" + "、".join(labels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
