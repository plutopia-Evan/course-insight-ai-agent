"""
AI 课程总结生成模块

功能:
- 从 ai_feedback_statistics.xlsx 读取结构化统计数据
- 为每(课程,期次)构建输入 JSON
- 调用 DeepSeek API 生成单期总结
- 为同课程多期次生成跨期趋势总结
- Pydantic 校验 + 重试 + SHA256 缓存
- 输出 5 工作表 Excel
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml
from openai import OpenAI
from pydantic import BaseModel, ValidationError, field_validator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def priority_from_ratio(ratio: float) -> str:
    """统一的优先级判断：ratio >= 0.20 → high, >= 0.10 → medium, < 0.10 → low"""
    if ratio >= 0.20:
        return "high"
    elif ratio >= 0.10:
        return "medium"
    return "low"


def _extract_numbers_from_text(text: str) -> List[Dict[str, str]]:
    """提取文本中的所有数字及其单位/上下文。返回 [{raw, context}] 列表。
    优先匹配带单位的数字，纯数字最后匹配，避免从 '0.1667' 中误提取 '1667'。"""
    found = []
    matched_spans = set()

    # 优先：带小数的数字（如 0.1667, 16.67%）
    decimal_pat = re.compile(r'\d+\.\d+')
    for m in decimal_pat.finditer(text):
        raw = m.group().strip()
        start, end = m.start(), m.end()
        # 往后看是否有 % 或 ％
        if end < len(text) and text[end] in ('%', '％'):
            raw = raw + text[end]
            end += 1
        matched_spans.add((start, end))
        ctx_start = max(0, start - 15)
        ctx_end = min(len(text), end + 5)
        found.append({"raw": raw, "context": text[ctx_start:ctx_end]})

    # 带单位的数字
    unit_pat = re.compile(r'\d+\.?\d*\s*[%％人位名天小时分钟周个月年次遍轮]')
    for m in unit_pat.finditer(text):
        start, end = m.start(), m.end()
        if any(s <= start < e or s < end <= e for s, e in matched_spans):
            continue
        matched_spans.add((start, end))
        ctx_start = max(0, start - 15)
        ctx_end = min(len(text), end + 5)
        found.append({"raw": m.group().strip(), "context": text[ctx_start:ctx_end]})

    # 纯数字（>=2位），排除已被覆盖的
    pure_pat = re.compile(r'(?<![0-9.])[1-9]\d{1,}(?![0-9.])(?!\.\d)')
    for m in pure_pat.finditer(text):
        start, end = m.start(), m.end()
        if any(s <= start < e or s < end <= e for s, e in matched_spans):
            continue
        ctx_start = max(0, start - 15)
        ctx_end = min(len(text), end + 5)
        found.append({"raw": m.group().strip(), "context": text[ctx_start:ctx_end]})

    return found


def _is_session_number(num_str: str) -> bool:
    """判断数字是否为课程期次编号（如 01, 02, 第1期等）"""
    n = num_str.strip()
    try:
        val = int(re.sub(r'[.０-９0-9]', lambda c: str(ord(c.group()) - ord('０') + ord('0')) if '０' <= c.group() <= '９' else c.group(), n))
        return 1 <= val <= 99
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------

class StrengthItem(BaseModel):
    title: str
    description: str
    people: int
    ratio: float


class ProblemItem(BaseModel):
    title: str
    description: str
    people: int
    ratio: float
    priority: str

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v):
        if v not in ("high", "medium", "low"):
            raise ValueError(f"priority 必须为 high/medium/low: {v}")
        return v


class RecommendationItem(BaseModel):
    action: str
    reason: str
    source_type: str
    source_label: str
    people: int
    ratio: float
    priority: str

    @field_validator("source_type")
    @classmethod
    def check_source_type(cls, v):
        if v not in ("negative", "suggestion"):
            raise ValueError(f"source_type 必须为 negative 或 suggestion: {v}")
        return v

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v):
        if v not in ("high", "medium", "low"):
            raise ValueError(f"priority 必须为 high/medium/low: {v}")
        return v


class SessionSummary(BaseModel):
    course_name: str
    session: str
    overall_assessment: str
    strengths: List[StrengthItem]
    problems: List[ProblemItem]
    recommendations: List[RecommendationItem]
    management_summary: str

    @field_validator("strengths")
    @classmethod
    def max_strengths(cls, v):
        if len(v) > 3:
            raise ValueError(f"strengths 最多 3 项，实际 {len(v)}")
        return v

    @field_validator("problems")
    @classmethod
    def max_problems(cls, v):
        if len(v) > 3:
            raise ValueError(f"problems 最多 3 项，实际 {len(v)}")
        return v

    @field_validator("recommendations")
    @classmethod
    def max_recommendations(cls, v):
        if len(v) > 3:
            raise ValueError(f"recommendations 最多 3 项，实际 {len(v)}")
        return v


class PersistentProblem(BaseModel):
    label: str
    sessions: List[str]
    trend: str
    evidence: str


class NewProblem(BaseModel):
    label: str
    first_session: str
    current_ratio: float


class ImprovedProblem(BaseModel):
    label: str
    before_ratio: float
    after_ratio: float


class NextPriority(BaseModel):
    priority: int
    action: str
    reason: str


class TrendSummary(BaseModel):
    course_name: str
    trend_summary: str
    next_session_priorities: List[NextPriority]

    @field_validator("next_session_priorities")
    @classmethod
    def max_priorities(cls, v):
        if len(v) > 5:
            raise ValueError(f"next_session_priorities 最多 5 项，实际 {len(v)}")
        return v


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {"课程名称": "course_name", "期次": "session"}
    return df.rename(columns=aliases)


def load_statistics(excel_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overview = pd.read_excel(excel_path, sheet_name="课程期次反馈概览")
    positive = pd.read_excel(excel_path, sheet_name="AI正向反馈汇总")
    negative = pd.read_excel(excel_path, sheet_name="AI负向问题汇总")
    suggestions = pd.read_excel(excel_path, sheet_name="AI改进建议汇总")
    return (
        _normalize_columns(overview),
        _normalize_columns(positive),
        _normalize_columns(negative),
        _normalize_columns(suggestions),
    )


def build_session_input(row, pos_df, neg_df, sug_df) -> dict:
    course = row["course_name"]
    sess = row["session"]

    def _items(sub_df):
        subset = sub_df[(sub_df["course_name"] == course) & (sub_df["session"] == sess)]
        items = []
        for _, r in subset.iterrows():
            items.append({
                "category": r.get("category", ""),
                "subcategory": r.get("subcategory", ""),
                "people": int(r.get("反馈人数", 0)),
                "ratio": float(r.get("人数占比", 0)),
            })
        return items

    return {
        "course_name": course,
        "session": sess,
        "valid_feedback_people": int(row["有效反馈人数"]),
        "total_items": int(row["拆分意见总数"]),
        "positive_count": int(row["positive意见数"]),
        "positive_ratio": float(row["positive占比"]),
        "negative_count": int(row["negative意见数"]),
        "negative_ratio": float(row["negative占比"]),
        "suggestion_count": int(row["suggestion意见数"]),
        "suggestion_ratio": float(row["suggestion占比"]),
        "top_positive": _items(pos_df),
        "top_negative": _items(neg_df),
        "top_suggestions": _items(sug_df),
    }


def build_trend_input(course: str, sessions_data: List[dict]) -> dict:
    return {
        "course_name": course,
        "sessions": sessions_data,
    }


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join("data", "cache")
CACHE_PATH = os.path.join(CACHE_DIR, "ai_summary_cache.json")


def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            broken = os.path.join(CACHE_DIR, f"ai_summary_cache.broken_{timestamp}.json")
            os.rename(CACHE_PATH, broken)
            print(f"  缓存损坏已备份: {broken}")
    return {}


def _save_cache(cache: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _cache_key(model: str, input_json: str) -> str:
    raw = f"{model}|{input_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def load_prompt_template() -> str:
    with open("prompts/course_summary_prompt.md", "r", encoding="utf-8") as f:
        return f.read()


def _call_llm(input_data: dict, system_prompt: str,
              model_type: type, api_key: str, base_url: str, model: str,
              max_retries: int = 3, use_cache: bool = True) -> Tuple[dict, dict]:
    """返回 (result, metadata)，metadata 包含 cache_hit/api_called/retries"""
    input_json = json.dumps(input_data, ensure_ascii=False)
    ck = _cache_key(model, input_json)
    meta = {"_cache_hit": False, "_api_called": 0, "_retries": 0}

    if use_cache:
        cache = _load_cache()
        if ck in cache:
            print("    [缓存命中]")
            meta["_cache_hit"] = True
            return cache[ck], meta

    user_content = input_json
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1 and last_error:
                user_content = f"{input_json}\n\n上一次输出存在以下错误：\n{last_error}\n请修正后重新输出严格JSON。"

            client = OpenAI(api_key=api_key, base_url=base_url)
            meta["_api_called"] += 1

            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=3000,
                timeout=120,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
            data = json.loads(_extract_json(raw))

            # Pydantic 校验
            parsed = model_type(**data)

            # 额外校验: people/ratio 是否存在于输入
            errors = _validate_numbers(parsed, input_data)
            if errors:
                last_error = "; ".join(errors)
                continue

            result = parsed.model_dump()
            if use_cache:
                cache = _load_cache()
                cache[ck] = result
                _save_cache(cache)
            meta["_retries"] = attempt - 1
            return result, meta

        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)
            continue
        except Exception as e:
            last_error = f"API异常: {e}"
            continue

    meta["_retries"] = max_retries
    return {"_error": f"重试{max_retries}次后仍失败: {last_error}"}, meta


def _validate_numbers(parsed, input_data) -> List[str]:
    """严格校验：数据来源隔离 + 优先级阈值 + 文本数字审计"""
    errors = []

    # 构建各数据源的查找列表
    pos_items = [(it.get("subcategory", ""), it.get("people", 0), it.get("ratio", 0))
                 for it in input_data.get("top_positive", [])]
    neg_items = [(it.get("subcategory", ""), it.get("people", 0), it.get("ratio", 0))
                 for it in input_data.get("top_negative", [])]
    sug_items = [(it.get("subcategory", ""), it.get("people", 0), it.get("ratio", 0))
                 for it in input_data.get("top_suggestions", [])]

    # ---- strengths: 仅来自 top_positive ----
    for i, s in enumerate(getattr(parsed, "strengths", [])):
        found = any(t[0] == s.title and t[1] == s.people and abs(t[2] - s.ratio) < 0.001
                    for t in pos_items)
        if not found:
            errors.append(f"strengths[{i}]: title/people/ratio 不在 top_positive 中: "
                          f"{s.title}/{s.people}/{s.ratio}")

    # ---- problems: 仅来自 top_negative ----
    for i, p in enumerate(getattr(parsed, "problems", [])):
        found = any(t[0] == p.title and t[1] == p.people and abs(t[2] - p.ratio) < 0.001
                    for t in neg_items)
        if not found:
            errors.append(f"problems[{i}]: title/people/ratio 不在 top_negative 中: "
                          f"{p.title}/{p.people}/{p.ratio}")
        # 优先级必须符合阈值
        expected_pri = priority_from_ratio(p.ratio)
        if p.priority != expected_pri:
            errors.append(f"problems[{i}]: priority={p.priority} 但 ratio={p.ratio} 期望 {expected_pri}")

    # ---- recommendations: 按 source_type 严格区分来源 ----
    # 收集所有 subcategory 名称用于交叉引用检查
    all_subcategories = set()
    for t in pos_items + neg_items + sug_items:
        if t[0]:
            all_subcategories.add(t[0])

    for i, r in enumerate(getattr(parsed, "recommendations", [])):
        # source_type 决定允许的数据来源
        if r.source_type == "negative":
            allowed = neg_items
            allowed_name = "top_negative"
        else:
            allowed = sug_items
            allowed_name = "top_suggestions"

        found = any(t[0] == r.source_label and t[1] == r.people and abs(t[2] - r.ratio) < 0.001
                    for t in allowed)
        if not found:
            errors.append(f"recommendations[{i}]: source_type={r.source_type} 但 "
                          f"source_label/people/ratio 不在 {allowed_name} 中: "
                          f"{r.source_label}/{r.people}/{r.ratio}")

        # 优先级必须符合阈值
        expected_pri = priority_from_ratio(r.ratio)
        if r.priority != expected_pri:
            errors.append(f"recommendations[{i}]: priority={r.priority} 但 ratio={r.ratio} 期望 {expected_pri}")

        # 交叉引用检查：action 和 reason 不得提到其他 subcategory
        other_labels = all_subcategories - {r.source_label}
        for field_name in [f"recommendations[{i}].action", f"recommendations[{i}].reason"]:
            field_text = r.action if "action" in field_name else r.reason
            for other_label in other_labels:
                if other_label and other_label in field_text:
                    errors.append(
                        f"{field_name}: 提到了其他标签'{other_label}'，"
                        f"但该 recommendation 的 source_label 是'{r.source_label}'，"
                        f"一条 recommendation 只能围绕一个 source_label"
                    )

    # ---- 数字审计: 文本字段中的数字必须有据可查 ----
    text_fields = [
        ("overall_assessment", getattr(parsed, "overall_assessment", "")),
    ]
    for i, s in enumerate(getattr(parsed, "strengths", [])):
        text_fields.append((f"strengths[{i}].description", s.description))
    for i, p in enumerate(getattr(parsed, "problems", [])):
        text_fields.append((f"problems[{i}].description", p.description))
    for i, r in enumerate(getattr(parsed, "recommendations", [])):
        text_fields.append((f"recommendations[{i}].action", r.action))
        text_fields.append((f"recommendations[{i}].reason", r.reason))
    text_fields.append(("management_summary", getattr(parsed, "management_summary", "")))

    # 构建所有合法数字集合
    valid_numbers = set()
    # 来自输入数据的people/ratio
    for _, ppl, rto in pos_items + neg_items + sug_items:
        valid_numbers.add(str(ppl))
        # ratio 的多种精度形式
        for precision in [2, 3, 4]:
            valid_numbers.add(str(round(rto, precision)))
        # 百分比形式 (多种精度)
        for pct_precision in [0, 1, 2]:
            valid_numbers.add(f"{rto:{pct_precision}.{pct_precision}%}")
        # 去掉末尾零的百分比 (如 "16.67%", "33.3%")
        pct_str = f"{rto:.4%}"  # xx.xxxx%
        valid_numbers.add(pct_str)
        pct_str_3 = f"{rto:.3%}"
        valid_numbers.add(pct_str_3)
        pct_str_2 = f"{rto:.2%}"
        valid_numbers.add(pct_str_2)
    # 基础统计数字
    for key in ["valid_feedback_people", "total_items", "positive_count", "negative_count",
                "suggestion_count", "positive_ratio", "negative_ratio", "suggestion_ratio"]:
        v = input_data.get(key)
        if v is not None:
            valid_numbers.add(str(v))
            if isinstance(v, float):
                for precision in [2, 3, 4]:
                    valid_numbers.add(str(round(v, precision)))
                valid_numbers.add(f"{v:.1%}")
                valid_numbers.add(f"{v:.2%}")
    # 期次编号
    session_str = str(input_data.get("session", ""))

    for field_name, text in text_fields:
        nums = _extract_numbers_from_text(text)
        for n in nums:
            raw = n["raw"]
            # 允许期次编号
            if _is_session_number(raw) or raw in session_str or session_str in raw:
                continue
            # 允许纯数字用于排名 (#1, #2)
            if re.match(r'^\d+$', raw) and int(raw) <= 10:
                continue
            # 检查是否在合法集合
            matched = any(vn in raw or raw in vn for vn in valid_numbers)
            if not matched:
                errors.append(f"{field_name}: 数字'{raw}'无法追溯到输入数据 (上下文: {n['context']})")

    return errors


# ---------------------------------------------------------------------------
# Python 跨期趋势计算
# ---------------------------------------------------------------------------

def _compute_cross_session_trends(course: str, sessions_data: List[dict],
                                   session_results: List[dict]) -> dict:
    """纯 Python 计算跨期趋势，不依赖模型。"""
    # 收集所有期次的 negative subcategory 及其 ratio
    # session_results 按 sessions_data 顺序对应
    session_labels = [s["session"] for s in sessions_data]

    neg_by_session: Dict[str, Dict[str, float]] = {}
    for sd in sessions_data:
        sess = sd["session"]
        neg_by_session[sess] = {}
        for it in sd.get("top_negative", []):
            neg_by_session[sess][it["subcategory"]] = it["ratio"]

    all_labels = set()
    for sess_data in neg_by_session.values():
        all_labels.update(sess_data.keys())

    latest_session = session_labels[-1]
    earlier_sessions = session_labels[:-1]

    # persistent: 同一 label 在 >= 2 期次出现
    persistent = []
    for label in all_labels:
        appear = [(s, neg_by_session[s][label])
                  for s in session_labels if label in neg_by_session[s]]
        if len(appear) < 2:
            continue
        before_ratio = appear[-2][1]
        after_ratio = appear[-1][1]
        diff = after_ratio - before_ratio
        if abs(diff) < 0.05:
            trend = "stable"
        elif diff >= 0.05:
            trend = "worsening"
        else:
            trend = "improving"
        persistent.append(PersistentProblem(
            label=label,
            sessions=[a[0] for a in appear],
            trend=trend,
            evidence=f"人数占比从 {before_ratio:.1%} 变为 {after_ratio:.1%}"
        ))

    # new: 仅在最新期次出现
    new = []
    for label in all_labels:
        appear = [s for s in session_labels if label in neg_by_session[s]]
        if latest_session in appear and len(appear) == 1:
            cur_ratio = neg_by_session[latest_session][label]
            new.append(NewProblem(
                label=label,
                first_session=latest_session,
                current_ratio=cur_ratio,
            ))

    # improved: 仅在早期期次出现且后期消失（不在最新期次）
    improved = []
    for label in all_labels:
        appear = [s for s in session_labels if label in neg_by_session[s]]
        if latest_session not in appear and len(appear) >= 1:
            before_ratio = neg_by_session[appear[0]][label]
            improved.append(ImprovedProblem(
                label=label,
                before_ratio=before_ratio,
                after_ratio=0.0,
            ))

    return {
        "persistent_problems": [p.model_dump() for p in persistent],
        "new_problems": [n.model_dump() for n in new],
        "improved_problems": [i.model_dump() for i in improved],
    }


def _build_trend_llm_input(course: str, sessions_data: List[dict],
                            computed_trends: dict) -> dict:
    """构建发给模型做 NL 总结的输入（Python 已算好结构性趋势）。"""
    return {
        "course_name": course,
        "sessions": sessions_data,
        "computed_trends": computed_trends,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def generate_summaries(
    input_path: str = "data/output/ai_feedback_statistics.xlsx",
    output_path: str = "data/output/ai_course_summary.xlsx",
    limit: Optional[int] = None,
    use_cache: bool = True,
):
    start_time = datetime.now()

    import deepseek_config as cfg
    api_key = cfg.DEEPSEEK_API_KEY
    base_url = cfg.DEEPSEEK_BASE_URL
    model = cfg.DEEPSEEK_MODEL

    overview, pos_df, neg_df, sug_df = load_statistics(input_path)
    system_prompt = load_prompt_template()

    # 限制处理
    if limit and limit > 0:
        overview = overview.head(limit)

    # ---- 单期总结 ----
    session_results = []
    session_errors = []
    total_cache_hits = 0
    total_api_calls = 0
    total_retries = 0

    for idx, (_, row) in enumerate(overview.iterrows()):
        course = row["course_name"]
        sess = row["session"]
        print(f"[{idx+1}/{len(overview)}] {course} {sess} ...")

        input_data = build_session_input(row, pos_df, neg_df, sug_df)
        result, meta = _call_llm(
            input_data, system_prompt, SessionSummary,
            api_key, base_url, model, max_retries=3, use_cache=use_cache,
        )
        total_cache_hits += 1 if meta["_cache_hit"] else 0
        total_api_calls += meta["_api_called"]
        total_retries += meta["_retries"]

        if result.get("_error"):
            print(f"  失败: {result['_error']}")
            session_errors.append({"course_name": course, "session": sess, "error": result["_error"]})
        else:
            n_str = len(result.get("strengths", []))
            n_prob = len(result.get("problems", []))
            n_rec = len(result.get("recommendations", []))
            print(f"  成功: {n_str}强项, {n_prob}问题, {n_rec}建议"
                  f"{' [cache]' if meta['_cache_hit'] else ''}")
            result["_course_name"] = course
            result["_session"] = sess
            session_results.append(result)

        time.sleep(0.3)

    # ---- 跨期趋势 ----
    trend_results = []
    trend_errors = []
    courses = overview["course_name"].unique()

    for course in courses:
        course_sessions = overview[overview["course_name"] == course]
        if len(course_sessions) < 2:
            continue

        print(f"跨期趋势: {course} ({len(course_sessions)} 期次)")

        sessions_data = []
        for _, row in course_sessions.iterrows():
            sessions_data.append(build_session_input(row, pos_df, neg_df, sug_df))

        # Python 计算结构性趋势
        computed = _compute_cross_session_trends(course, sessions_data, session_results)
        print(f"  Python计算: {len(computed['persistent_problems'])}持续问题, "
              f"{len(computed['new_problems'])}新问题, "
              f"{len(computed['improved_problems'])}改善")

        # 模型只生成 NL trend_summary + next_session_priorities
        trend_llm_input = _build_trend_llm_input(course, sessions_data, computed)
        result, meta = _call_llm(
            trend_llm_input, system_prompt, TrendSummary,
            api_key, base_url, model, max_retries=3, use_cache=use_cache,
        )
        total_cache_hits += 1 if meta["_cache_hit"] else 0
        total_api_calls += meta["_api_called"]
        total_retries += meta["_retries"]

        if result.get("_error"):
            print(f"  跨期失败: {result['_error']}")
            trend_errors.append({"course_name": course, "error": result["_error"]})
        else:
            # 合并 Python 计算的结构性数据
            result["persistent_problems"] = computed["persistent_problems"]
            result["new_problems"] = computed["new_problems"]
            result["improved_problems"] = computed["improved_problems"]
            print(f"  跨期成功: {len(computed['persistent_problems'])}持续问题, "
                  f"{len(computed['new_problems'])}新问题, "
                  f"{len(computed['improved_problems'])}改善"
                  f"{' [cache]' if meta['_cache_hit'] else ''}")
            trend_results.append(result)

        time.sleep(0.3)

    # ---- 统计 ----
    end_time = datetime.now()
    print(f"\n成功: {len(session_results)} 单期 + {len(trend_results)} 跨期")
    print(f"失败: {len(session_errors)} 单期 + {len(trend_errors)} 跨期")
    print(f"缓存命中: {total_cache_hits}, API调用: {total_api_calls}, 重试: {total_retries}")
    print(f"耗时: {(end_time - start_time).total_seconds():.1f}秒")

    # ---- 写入 Excel ----
    _write_output(
        session_results, session_errors, trend_results, trend_errors,
        output_path, start_time, end_time, model,
        total_cache_hits, total_api_calls, total_retries,
    )

    return output_path


def _write_output(
    session_results, session_errors, trend_results, trend_errors,
    output_path, start_time, end_time, model,
    total_cache_hits=0, total_api_calls=0, total_retries=0,
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. 课程AI总结
    summary_rows = []
    for r in session_results:
        strengths_str = "；".join(f"{s['title']}({s['people']}人)" for s in r.get("strengths", []))
        problems_str = "；".join(f"{p['title']}({p['people']}人,{p['priority']})" for p in r.get("problems", []))
        recs_str = "；".join(f"{r2['action']}({r2['priority']})" for r2 in r.get("recommendations", []))
        summary_rows.append({
            "课程名称": r.get("course_name", ""),
            "期次": r.get("session", ""),
            "整体评价": r.get("overall_assessment", ""),
            "主要优点": strengths_str,
            "主要问题": problems_str,
            "改进建议": recs_str,
            "管理层摘要": r.get("management_summary", ""),
        })
    summary_df = pd.DataFrame(summary_rows)

    # 2. 课程AI总结明细
    detail_rows = []
    for r in session_results:
        for s in r.get("strengths", []):
            detail_rows.append({
                "课程名称": r.get("course_name", ""),
                "期次": r.get("session", ""),
                "类型": "优点",
                "标签": s["title"],
                "描述": s["description"],
                "人数": s["people"],
                "占比": s["ratio"],
                "优先级": "",
            })
        for p in r.get("problems", []):
            detail_rows.append({
                "课程名称": r.get("course_name", ""),
                "期次": r.get("session", ""),
                "类型": "问题",
                "标签": p["title"],
                "描述": p["description"],
                "人数": p["people"],
                "占比": p["ratio"],
                "优先级": p["priority"],
            })
        for rec in r.get("recommendations", []):
            detail_rows.append({
                "课程名称": r.get("course_name", ""),
                "期次": r.get("session", ""),
                "类型": "建议",
                "标签": rec["action"],
                "描述": rec["reason"],
                "来源类型": rec.get("source_type", ""),
                "来源标签": rec.get("source_label", ""),
                "人数": rec.get("people", 0),
                "占比": rec.get("ratio", 0),
                "优先级": rec["priority"],
            })
    detail_df = pd.DataFrame(detail_rows)

    # 3. 跨期趋势总结
    trend_rows = []
    for t in trend_results:
        persistent_str = "；".join(
            f"{p['label']}({p['trend']})" for p in t.get("persistent_problems", [])
        )
        new_str = "；".join(p["label"] for p in t.get("new_problems", []))
        improved_str = "；".join(p["label"] for p in t.get("improved_problems", []))
        priorities_str = "；".join(
            f"#{q['priority']} {q['action']}" for q in t.get("next_session_priorities", [])
        )
        trend_rows.append({
            "课程名称": t.get("course_name", ""),
            "趋势总结": t.get("trend_summary", ""),
            "持续问题": persistent_str,
            "新出现问题": new_str,
            "已改善问题": improved_str,
            "下一期优先事项": priorities_str,
        })
    trend_df = pd.DataFrame(trend_rows)

    # 4. API调用错误记录
    all_errors = session_errors + trend_errors
    err_df = pd.DataFrame(all_errors) if all_errors else pd.DataFrame(
        columns=["course_name", "session", "error"]
    )

    # 5. 生成汇总
    gen_rows = [
        {"指标": "课程期次数", "数值": len(session_results) + len(session_errors)},
        {"指标": "成功数", "数值": len(session_results)},
        {"指标": "失败数", "数值": len(session_errors)},
        {"指标": "跨期课程数", "数值": len(trend_results) + len(trend_errors)},
        {"指标": "缓存命中数", "数值": total_cache_hits},
        {"指标": "API实际调用数", "数值": total_api_calls},
        {"指标": "总重试次数", "数值": total_retries},
        {"指标": "使用模型", "数值": model},
        {"指标": "开始时间", "数值": start_time.strftime('%Y-%m-%d %H:%M:%S')},
        {"指标": "结束时间", "数值": end_time.strftime('%Y-%m-%d %H:%M:%S')},
        {"指标": "总耗时", "数值": f"{(end_time - start_time).total_seconds():.1f}秒"},
    ]
    gen_df = pd.DataFrame(gen_rows)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="课程AI总结", index=False)
        detail_df.to_excel(writer, sheet_name="课程AI总结明细", index=False)
        trend_df.to_excel(writer, sheet_name="跨期趋势总结", index=False)
        err_df.to_excel(writer, sheet_name="API调用错误记录", index=False)
        gen_df.to_excel(writer, sheet_name="生成汇总", index=False)

        for ws in writer.sheets.values():
            ws.freeze_panes = "A2"
            for col_idx in range(1, ws.max_column + 1):
                col_letter = chr(64 + col_idx) if col_idx <= 26 else "A"
                max_len = 8
                for row_idx in range(1, min(ws.max_row + 1, 200)):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    print(f"Excel 已保存: {os.path.abspath(output_path)}")


def main():
    parser = argparse.ArgumentParser(description="课程 AI 总结生成")
    parser.add_argument("--input", default="data/output/ai_feedback_statistics.xlsx")
    parser.add_argument("--output", default="data/output/ai_course_summary.xlsx")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    generate_summaries(
        input_path=args.input,
        output_path=args.output,
        limit=args.limit,
        use_cache=not args.no_cache,
    )


if __name__ == "__main__":
    main()
