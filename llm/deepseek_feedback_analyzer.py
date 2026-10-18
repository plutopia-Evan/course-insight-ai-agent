"""
DeepSeek API 反馈分类模块

功能:
- 通过 OpenAI SDK 调用 DeepSeek 兼容接口
- response_format={"type": "json_object"} 强制 JSON 输出
- Pydantic 结构校验（category/subcategory/sentiment/summary/evidence/feedback_id）
- 自动重试（JSON 解析、标签非法、evidence 不合法、网络异常，最多 3 次）
- SHA256 缓存（模型、标签配置、提示词和反馈文本共同决定缓存键）
- 展平为 DataFrame
"""

import json
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml
import pandas as pd
from openai import OpenAI
from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 日志过滤：不输出 API Key
# ---------------------------------------------------------------------------

class _ApiKeyRedactingFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "api_key" in msg.lower() or "sk-" in msg:
            record.msg = record.msg.replace(record.msg, "[API Key 已屏蔽]")
            record.args = ()
        return True


logger.addFilter(_ApiKeyRedactingFilter())


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------

class DeepSeekFeedbackItem(BaseModel):
    category: str
    subcategory: str
    sentiment: str
    summary: str = ""
    evidence: str = ""


class DeepSeekFeedbackAnalysis(BaseModel):
    feedback_id: str
    items: List[DeepSeekFeedbackItem]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v):
        if len(v) == 0:
            raise ValueError("items 不能为空")
        return v


# ---------------------------------------------------------------------------
# Taxonomy 加载
# ---------------------------------------------------------------------------

def load_taxonomy(taxonomy_path: str = "config/feedback_taxonomy.yaml") -> dict:
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)
    return taxonomy


def _build_taxonomy_sets(taxonomy: dict) -> Tuple[set, Dict[str, set], set]:
    categories_set = set(taxonomy["categories"].keys())
    subcat_map = {cat: set(labels) for cat, labels in taxonomy["categories"].items()}
    sentiments_set = set(taxonomy["sentiments"])
    return categories_set, subcat_map, sentiments_set


def _build_sentiment_rules(taxonomy: dict) -> Dict[str, set]:
    """按子标签定义可接受的情感，拒绝配置中拼写错误或重复的标签。"""
    labels = [label for group in taxonomy["categories"].values() for label in group]
    if len(labels) != len(set(labels)):
        raise ValueError("标签配置中的 subcategory 必须唯一")
    all_labels = set(labels)
    positive = set(taxonomy.get("positive_subcategories", []))
    suggestion = set(taxonomy.get("suggestion_subcategories", []))
    neutral_allowed = set(taxonomy.get("neutral_allowed_subcategories", []))
    if (positive & suggestion) or (positive & neutral_allowed) or (suggestion & neutral_allowed):
        raise ValueError("情感规则中的标签分组不能重叠")
    unknown = (positive | suggestion | neutral_allowed) - all_labels
    if unknown:
        raise ValueError(f"情感规则包含未知标签: {sorted(unknown)}")
    required = {"positive", "negative", "suggestion", "neutral"}
    if not required.issubset(set(taxonomy["sentiments"])):
        raise ValueError("情感标签缺少必要类型")
    rules = {}
    for label in labels:
        if label in positive:
            rules[label] = {"positive"}
        elif label in suggestion:
            rules[label] = {"suggestion"}
        else:
            rules[label] = {"negative", "suggestion"}
            if label in neutral_allowed:
                rules[label].add("neutral")
    return rules


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def load_prompt_template(prompt_path: str = "prompts/feedback_classification_prompt.md") -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def render_classification_prompt(template: str, taxonomy: dict) -> str:
    """从唯一的标签配置生成提示词中的可选项。"""
    sentiment_rules = _build_sentiment_rules(taxonomy)
    sentiments = "\n".join(f"- `{value}`" for value in taxonomy["sentiments"])
    category_lines = []
    for category, labels in taxonomy["categories"].items():
        annotated_labels = [
            f"{label}（{'/'.join(sorted(sentiment_rules[label]))}）" for label in labels
        ]
        category_lines.append(f"- **{category}**：{'、'.join(annotated_labels)}")
    categories = "\n".join(category_lines)
    if "{{taxonomy_sentiments}}" not in template or "{{taxonomy_categories}}" not in template:
        raise ValueError("分类提示词缺少标签配置占位符")
    return (template.replace("{{taxonomy_sentiments}}", sentiments)
                    .replace("{{taxonomy_categories}}", categories))


def build_user_prompt(feedback_id: str, feedback_text: str) -> str:
    return f"feedback_id: {feedback_id}\n反馈内容: {feedback_text}"


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_deepseek_analysis(
    analysis: DeepSeekFeedbackAnalysis,
    feedback_text: str,
    categories: set,
    subcat_map: Dict[str, set],
    sentiments: set,
    expected_feedback_id: str,
    sentiment_rules: Optional[Dict[str, set]] = None,
) -> List[str]:
    """校验 DeepSeek 返回的分析结果。"""
    errors = []

    if analysis.feedback_id != expected_feedback_id:
        errors.append(
            f"feedback_id 不一致: 期望 '{expected_feedback_id}', 实际 '{analysis.feedback_id}'"
        )

    for i, item in enumerate(analysis.items):
        prefix = f"items[{i}]"
        if item.category not in categories:
            errors.append(f"{prefix}: category '{item.category}' 不在标签体系中")
        else:
            if item.subcategory not in subcat_map.get(item.category, set()):
                errors.append(
                    f"{prefix}: subcategory '{item.subcategory}' 不在 '{item.category}' 下"
                )
        if item.sentiment not in sentiments:
            errors.append(f"{prefix}: sentiment '{item.sentiment}' 不合法")
        elif sentiment_rules and item.subcategory in sentiment_rules:
            if item.sentiment not in sentiment_rules[item.subcategory]:
                errors.append(
                    f"{prefix}: '{item.subcategory}' 不允许 sentiment '{item.sentiment}'"
                )
        if not item.summary or not item.summary.strip():
            errors.append(f"{prefix}: summary 不能为空")
        elif len(item.summary) > 20:
            errors.append(f"{prefix}: summary '{item.summary}' 超过20个汉字")
        if not item.evidence or not item.evidence.strip():
            errors.append(f"{prefix}: evidence 不能为空")
        elif item.evidence not in feedback_text:
            errors.append(
                f"{prefix}: evidence '{item.evidence}' 不是原文子串"
            )
    return errors


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

def _cache_dir() -> str:
    return os.path.join("data", "cache")


def _cache_path() -> str:
    return os.path.join(_cache_dir(), "deepseek_feedback_cache.json")


def _load_cache() -> dict:
    """加载缓存，损坏时自动备份并返回空字典。"""
    path = _cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning("缓存文件损坏 (%s): %s", type(e).__name__, e)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        broken_path = os.path.join(
            _cache_dir(), f"deepseek_feedback_cache.broken_{timestamp}.json"
        )
        try:
            os.rename(path, broken_path)
            logger.warning("已损坏缓存已备份为: %s", os.path.basename(broken_path))
        except OSError as rename_err:
            logger.error("无法重命名损坏缓存: %s", rename_err)
        return {}


def _save_cache(cache: dict):
    d = _cache_dir()
    os.makedirs(d, exist_ok=True)
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _make_cache_key(model: str, taxonomy: dict, system_prompt: str, feedback_text: str) -> str:
    """配置或提示词内容变化后，旧分类结果不再命中。"""
    raw = json.dumps({
        "model": model,
        "taxonomy": taxonomy,
        "system_prompt": system_prompt,
        "feedback_text": feedback_text,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JSON 提取
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """从模型返回文本中提取 JSON，兼容 markdown 代码块。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# 主分析函数
# ---------------------------------------------------------------------------

def deepseek_analyze_feedback(
    feedback_id: str,
    feedback_text: str,
    course_name: str = "",
    session: str = "",
    respondent_id: str = "",
    taxonomy_path: str = "config/feedback_taxonomy.yaml",
    prompt_path: str = "prompts/feedback_classification_prompt.md",
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    timeout: int = 60,
    max_retries: int = 3,
    use_cache: bool = True,
) -> dict:
    """调用 DeepSeek API 分析单条反馈。

    Returns:
        dict 包含 feedback_id, course_name, session, respondent_id, items
        以及内部字段 _cache_hit, _error, _raw_response
    """
    # 加载配置
    if api_key is None or base_url is None or model is None:
        try:
            import deepseek_config as cfg
            api_key = api_key or cfg.DEEPSEEK_API_KEY
            base_url = base_url or cfg.DEEPSEEK_BASE_URL
            model = model or cfg.DEEPSEEK_MODEL
            temperature = cfg.DEEPSEEK_TEMPERATURE
            max_tokens = cfg.DEEPSEEK_MAX_TOKENS
            timeout = cfg.DEEPSEEK_TIMEOUT
            max_retries = cfg.DEEPSEEK_MAX_RETRIES
        except (ImportError, ValueError) as e:
            return {
                "feedback_id": feedback_id,
                "course_name": course_name,
                "session": session,
                "respondent_id": respondent_id,
                "items": [],
                "_error": str(e),
                "_raw_response": "",
                "_cache_hit": False,
                "_retries": 0,
            }

    # 缓存检查
    taxonomy = load_taxonomy(taxonomy_path)
    taxonomy_version = taxonomy.get("version", "1.0")
    prompt_template = load_prompt_template(prompt_path)
    system_prompt = render_classification_prompt(prompt_template, taxonomy)
    categories, subcat_map, sentiments = _build_taxonomy_sets(taxonomy)
    sentiment_rules = _build_sentiment_rules(taxonomy)
    cache_key = _make_cache_key(model, taxonomy, system_prompt, feedback_text)

    if use_cache:
        cache = _load_cache()
        if cache_key in cache:
            cached = cache[cache_key]
            items = cached.get("validated_result", {}).get("items", cached.get("items", []))
            try:
                analysis = DeepSeekFeedbackAnalysis(feedback_id=feedback_id, items=items)
                errors = validate_deepseek_analysis(
                    analysis, feedback_text, categories, subcat_map, sentiments, feedback_id,
                    sentiment_rules,
                )
            except ValidationError as exc:
                errors = [str(exc)]
            if not errors:
                logger.info("缓存命中: %s", feedback_id)
                return {
                    "feedback_id": feedback_id,
                    "course_name": course_name,
                    "session": session,
                    "respondent_id": respondent_id,
                    "items": [item.model_dump() for item in analysis.items],
                    "_cache_hit": True,
                    "_retries": 0,
                }
            logger.warning("忽略未通过校验的反馈缓存: %s", feedback_id)
    base_user_prompt = build_user_prompt(feedback_id, feedback_text)

    last_error = None
    raw_response = ""
    total_retries = 0

    # ---- 重试循环 ----
    for attempt in range(1, max_retries + 1):
        total_retries = attempt
        try:
            logger.info("DeepSeek 调用 [%s] 第 %d/%d 次", feedback_id, attempt, max_retries)

            if attempt == 1:
                current_user_prompt = base_user_prompt
            else:
                current_user_prompt = (
                    f"{base_user_prompt}\n\n"
                    f"上一次输出存在以下错误：\n"
                    f"{last_error}\n"
                    f"请修正这些问题，并重新输出严格JSON。"
                )

            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": current_user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
            raw_response = response.choices[0].message.content

            # JSON 解析
            json_str = _extract_json(raw_response)
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                last_error = f"JSON 解析失败: {e}"
                logger.warning("DeepSeek [%s] 第 %d 次 JSON 解析失败", feedback_id, attempt)
                continue

            # Pydantic 校验
            try:
                analysis = DeepSeekFeedbackAnalysis(**data)
            except ValidationError as e:
                last_error = f"Pydantic 校验失败: {e}"
                logger.warning("DeepSeek [%s] 第 %d 次结构校验失败", feedback_id, attempt)
                continue

            # 标签校验
            errors = validate_deepseek_analysis(
                analysis, feedback_text, categories, subcat_map, sentiments, feedback_id,
                sentiment_rules,
            )
            if errors:
                last_error = "校验失败: " + "; ".join(errors)
                logger.warning("DeepSeek [%s] 第 %d 次标签校验失败: %s",
                               feedback_id, attempt, "; ".join(errors))
                continue

            # ---- 成功 ----
            result = {
                "feedback_id": feedback_id,
                "course_name": course_name,
                "session": session,
                "respondent_id": respondent_id,
                "items": [item.model_dump() for item in analysis.items],
            }
            logger.info("DeepSeek 分析成功 [%s]: %d 条意见, 重试 %d 次",
                        feedback_id, len(result["items"]), attempt - 1)

            if use_cache:
                cache_entry = {
                    "feedback_text": feedback_text,
                    "model": model,
                    "taxonomy_version": taxonomy_version,
                    "raw_response": raw_response,
                    "validated_result": {
                        "items": result["items"],
                    },
                    "created_at": datetime.now().isoformat(),
                    "feedback_id": feedback_id,
                    "course_name": course_name,
                    "session": session,
                    "respondent_id": respondent_id,
                }
                cache = _load_cache()
                cache[cache_key] = cache_entry
                _save_cache(cache)

            result["_cache_hit"] = False
            result["_retries"] = attempt - 1
            return result

        except Exception as e:
            last_error = f"网络/API 异常: {e}"
            logger.warning("DeepSeek [%s] 第 %d 次异常: %s", feedback_id, attempt, e)
            if attempt < max_retries:
                continue

    # ---- 全部重试失败 ----
    logger.error("DeepSeek [%s] 全部 %d 次重试均失败: %s",
                 feedback_id, max_retries, last_error)
    return {
        "feedback_id": feedback_id,
        "course_name": course_name,
        "session": session,
        "respondent_id": respondent_id,
        "items": [],
        "_error": f"重试{max_retries}次后仍失败: {last_error}",
        "_raw_response": raw_response,
        "_cache_hit": False,
        "_retries": total_retries,
    }


# ---------------------------------------------------------------------------
# 展平
# ---------------------------------------------------------------------------

def flatten_deepseek_results(results: List[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        for item in r.get("items", []):
            rows.append({
                "feedback_id": r.get("feedback_id", ""),
                "course_name": r.get("course_name", ""),
                "session": r.get("session", ""),
                "respondent_id": r.get("respondent_id", ""),
                "category": item.get("category", ""),
                "subcategory": item.get("subcategory", ""),
                "sentiment": item.get("sentiment", ""),
                "summary": item.get("summary", ""),
                "evidence": item.get("evidence", ""),
            })
    if not rows:
        return pd.DataFrame(columns=[
            "feedback_id", "course_name", "session", "respondent_id",
            "category", "subcategory", "sentiment", "summary", "evidence",
        ])
    df = pd.DataFrame(rows)
    logger.info("展平完成: %d 条反馈, %d 行", len(results), len(df))
    return df
