"""
LLM 反馈分类模块

功能:
- OpenAI 兼容 API 调用
- Pydantic 结构校验（category/subcategory/sentiment/summary/evidence）
- 自动重试（最多 3 次）
- SHA256 缓存（data/cache/ai_feedback_cache.json）
- 展平为 DataFrame
"""

import json
import hashlib
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import yaml
import pandas as pd
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------

class FeedbackItemModel(BaseModel):
    category: str
    subcategory: str
    sentiment: str
    summary: str
    evidence: str


class FeedbackAnalysisModel(BaseModel):
    feedback_id: str
    items: List[FeedbackItemModel]

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


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def load_prompt_template(prompt_path: str = "prompts/feedback_classification_prompt.md") -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_prompt(feedback_id: str, feedback_text: str) -> str:
    return f"feedback_id: {feedback_id}\n反馈内容: {feedback_text}"


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_analysis(
    analysis: FeedbackAnalysisModel,
    feedback_text: str,
    categories: set,
    subcat_map: Dict[str, set],
    sentiments: set,
) -> List[str]:
    """校验分析结果的标签和字段合法性，返回错误列表。"""
    errors = []
    for i, item in enumerate(analysis.items):
        prefix = f"items[{i}]"
        if item.category not in categories:
            errors.append(f"{prefix}: category '{item.category}' 不在标签体系中")
        else:
            if item.subcategory not in subcat_map.get(item.category, set()):
                errors.append(f"{prefix}: subcategory '{item.subcategory}' 不在 '{item.category}' 下")
        if item.sentiment not in sentiments:
            errors.append(f"{prefix}: sentiment '{item.sentiment}' 不合法")
        if len(item.summary) > 20:
            errors.append(f"{prefix}: summary '{item.summary}' 超过20个汉字")
        if item.evidence not in feedback_text:
            errors.append(f"{prefix}: evidence '{item.evidence}' 不是原文子串")
    return errors


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

def _cache_dir() -> str:
    return os.path.join("data", "cache")


def _cache_path() -> str:
    return os.path.join(_cache_dir(), "ai_feedback_cache.json")


def _load_cache() -> dict:
    path = _cache_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    d = _cache_dir()
    os.makedirs(d, exist_ok=True)
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------

def _call_llm(system_prompt: str, user_prompt: str,
              api_key: str, base_url: str, model: str,
              temperature: float = 0.1, max_tokens: int = 2000,
              timeout: int = 60) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return response.choices[0].message.content


def _extract_json(text: str) -> str:
    """从模型返回文本中提取 JSON 字符串，兼容 markdown 代码块包裹。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# 主分析函数
# ---------------------------------------------------------------------------

def llm_analyze_feedback(
    feedback_id: str,
    feedback_text: str,
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
    """调用 LLM 分析单条反馈，含校验、重试、缓存。

    Args:
        feedback_id: 反馈编号
        feedback_text: 原始反馈文本
        taxonomy_path: 标签体系 YAML 路径
        prompt_path: Prompt 模板路径
        api_key: API Key（默认从 config 读取）
        base_url: API Base URL
        model: 模型名称
        temperature: 生成温度
        max_tokens: 最大 token 数
        timeout: 超时秒数
        max_retries: 最大重试次数
        use_cache: 是否使用缓存

    Returns:
        校验后的分析结果 dict，包含 _raw_response 和 _error 字段（如有）
    """
    if api_key is None or base_url is None or model is None:
        try:
            import config as cfg
            api_key = api_key or cfg.LLM_API_KEY
            base_url = base_url or cfg.LLM_BASE_URL
            model = model or cfg.LLM_MODEL
            temperature = cfg.LLM_TEMPERATURE if temperature == 0.1 else temperature
            max_tokens = cfg.LLM_MAX_TOKENS if max_tokens == 2000 else max_tokens
            timeout = cfg.LLM_TIMEOUT if timeout == 60 else timeout
            max_retries = cfg.LLM_MAX_RETRIES if max_retries == 3 else max_retries
        except (ImportError, ValueError) as e:
            return {
                "feedback_id": feedback_id,
                "items": [],
                "_error": str(e),
                "_raw_response": "",
            }

    text_hash = _text_hash(feedback_text)

    if use_cache:
        cache = _load_cache()
        if text_hash in cache:
            logger.info("缓存命中: %s", feedback_id)
            cached = cache[text_hash].copy()
            cached["feedback_id"] = feedback_id
            return cached

    taxonomy = load_taxonomy(taxonomy_path)
    categories, subcat_map, sentiments = _build_taxonomy_sets(taxonomy)
    prompt_template = load_prompt_template(prompt_path)
    system_prompt = prompt_template
    user_prompt = build_user_prompt(feedback_id, feedback_text)

    last_error = None
    raw_response = ""

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("LLM 调用 [%s] 第 %d/%d 次", feedback_id, attempt, max_retries)
            raw_response = _call_llm(
                system_prompt, user_prompt,
                api_key=api_key, base_url=base_url, model=model,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )
            json_str = _extract_json(raw_response)
            data = json.loads(json_str)

            analysis = FeedbackAnalysisModel(**data)

            if analysis.feedback_id != feedback_id:
                analysis.feedback_id = feedback_id

            errors = validate_analysis(analysis, feedback_text, categories, subcat_map, sentiments)
            if errors:
                raise ValueError("校验失败: " + "; ".join(errors))

            result = analysis.model_dump()
            logger.info("LLM 分析成功 [%s]: %d 条意见", feedback_id, len(result["items"]))

            if use_cache:
                cache_entry = {
                    "feedback_id": feedback_id,
                    "items": result["items"],
                    "_raw_response": raw_response,
                    "_text_hash": text_hash,
                }
                cache = _load_cache()
                cache[text_hash] = cache_entry
                _save_cache(cache)

            return result

        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = str(e)
            logger.warning("LLM 调用 [%s] 第 %d 次失败: %s", feedback_id, attempt, last_error)
            if attempt < max_retries:
                continue

    logger.error("LLM 调用 [%s] 全部 %d 次重试均失败: %s", feedback_id, max_retries, last_error)
    return {
        "feedback_id": feedback_id,
        "items": [],
        "_error": f"重试{max_retries}次后仍失败: {last_error}",
        "_raw_response": raw_response,
    }


# ---------------------------------------------------------------------------
# 展平
# ---------------------------------------------------------------------------

def flatten_analysis_results(results: List[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        for item in r.get("items", []):
            rows.append({
                "feedback_id": r["feedback_id"],
                "category": item["category"],
                "subcategory": item["subcategory"],
                "sentiment": item["sentiment"],
                "summary": item["summary"],
                "evidence": item["evidence"],
            })
    if not rows:
        return pd.DataFrame(columns=[
            "feedback_id", "category", "subcategory", "sentiment", "summary", "evidence",
        ])
    df = pd.DataFrame(rows)
    logger.info("展平完成: %d 条反馈, %d 行", len(results), len(df))
    return df
