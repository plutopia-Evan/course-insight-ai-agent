"""
AI 反馈分类模块 (Mock 模式)

功能:
- 读取 config/feedback_taxonomy.yaml 标签体系
- 基于关键词规则的 mock 反馈分析
- 输出验证与 DataFrame 展平
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import yaml
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FeedbackItem:
    """单条意见。"""
    category: str
    subcategory: str
    sentiment: str
    summary: str
    evidence: str


@dataclass
class FeedbackAnalysis:
    """一条反馈的完整分析结果。"""
    feedback_id: str
    course_name: str
    session: str
    respondent_id: str
    items: List[FeedbackItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "course_name": self.course_name,
            "session": self.session,
            "respondent_id": self.respondent_id,
            "items": [
                {
                    "category": item.category,
                    "subcategory": item.subcategory,
                    "sentiment": item.sentiment,
                    "summary": item.summary,
                    "evidence": item.evidence,
                }
                for item in self.items
            ],
        }


def load_taxonomy(taxonomy_path: str = "config/feedback_taxonomy.yaml") -> dict:
    """加载反馈标签体系。

    Args:
        taxonomy_path: YAML 配置文件路径

    Returns:
        包含 version, sentiments, categories 的字典
    """
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)
    logger.info("标签体系加载完成: version=%s, %d 个大类, %d 个情感标签",
                taxonomy.get("version"), len(taxonomy.get("categories", {})),
                len(taxonomy.get("sentiments", [])))
    return taxonomy


def _build_taxonomy_sets(taxonomy: dict) -> Tuple[set, Dict[str, set], set]:
    """从 taxonomy 构建 category 集合、subcategory 映射和 sentiment 集合。"""
    categories_set = set(taxonomy["categories"].keys())
    subcat_map = {cat: set(labels) for cat, labels in taxonomy["categories"].items()}
    sentiments_set = set(taxonomy["sentiments"])
    return categories_set, subcat_map, sentiments_set


def _validate_item(item: FeedbackItem, categories: set, subcat_map: Dict[str, set],
                   sentiments: set) -> List[str]:
    """验证单条意见的标签是否在范围内，返回错误列表。"""
    errors = []
    if item.category not in categories:
        errors.append(f"category '{item.category}' 不在标签体系中")
    else:
        if item.subcategory not in subcat_map.get(item.category, set()):
            errors.append(f"subcategory '{item.subcategory}' 不在 '{item.category}' 下")
    if item.sentiment not in sentiments:
        errors.append(f"sentiment '{item.sentiment}' 不在允许的情感标签中")
    return errors


# Mock 关键词规则: (关键词列表, category, subcategory, sentiment, summary)
MOCK_RULES: List[Tuple[List[str], str, str, str, str]] = [
    (["讲得很好", "讲解清晰"], "讲师表现", "讲解清晰", "positive", "认可讲师讲解"),
    (["节奏太快", "进度太快"], "课程节奏", "节奏过快", "negative", "课程节奏过快"),
    (["增加案例", "更多案例"], "实操与案例", "希望增加完整案例", "suggestion", "建议增加案例"),
    (["练习太少", "增加练习"], "实操与案例", "练习不足", "suggestion", "建议增加练习"),
    (["资料发放晚"], "教材与资料", "资料发放较晚", "negative", "资料发放较晚"),
]


def mock_analyze_feedback(feedback_id: str, feedback_text: str,
                          course_name: str = "", session: str = "",
                          respondent_id: str = "",
                          taxonomy_path: str = "config/feedback_taxonomy.yaml") -> dict:
    """基于关键词规则的 mock 反馈分析。

    Args:
        feedback_id: 反馈编号
        feedback_text: 原始反馈文本
        course_name: 课程名称
        session: 期次
        respondent_id: 学员编号
        taxonomy_path: 标签体系文件路径

    Returns:
        固定结构的 dict
    """
    taxonomy = load_taxonomy(taxonomy_path)
    categories_set, subcat_map, sentiments_set = _build_taxonomy_sets(taxonomy)

    analysis = FeedbackAnalysis(
        feedback_id=feedback_id,
        course_name=course_name,
        session=session,
        respondent_id=respondent_id,
    )

    matched_any = False
    for keywords, category, subcategory, sentiment, summary in MOCK_RULES:
        for kw in keywords:
            if kw in feedback_text:
                item = FeedbackItem(
                    category=category,
                    subcategory=subcategory,
                    sentiment=sentiment,
                    summary=summary,
                    evidence=feedback_text,
                )
                errors = _validate_item(item, categories_set, subcat_map, sentiments_set)
                if errors:
                    logger.warning("验证失败 [%s]: %s", feedback_id, errors)
                else:
                    analysis.items.append(item)
                    matched_any = True
                break

    if not matched_any:
        fallback = FeedbackItem(
            category="其他",
            subcategory="其他问题",
            sentiment="neutral",
            summary="未匹配到具体意见",
            evidence=feedback_text,
        )
        analysis.items.append(fallback)

    result = analysis.to_dict()
    logger.info("反馈 %s: 拆分出 %d 条意见", feedback_id, len(result["items"]))
    return result


def flatten_analysis_results(results: List[dict]) -> pd.DataFrame:
    """将分析结果列表展平为 DataFrame，每条意见一行。

    Args:
        results: analysis dict 列表

    Returns:
        展平后的 DataFrame
    """
    rows = []
    for r in results:
        for item in r.get("items", []):
            rows.append({
                "feedback_id": r["feedback_id"],
                "course_name": r.get("course_name", ""),
                "session": r.get("session", ""),
                "respondent_id": r.get("respondent_id", ""),
                "category": item["category"],
                "subcategory": item["subcategory"],
                "sentiment": item["sentiment"],
                "summary": item["summary"],
                "evidence": item["evidence"],
            })

    if not rows:
        return pd.DataFrame(columns=[
            "feedback_id", "course_name", "session", "respondent_id",
            "category", "subcategory", "sentiment", "summary", "evidence",
        ])

    df = pd.DataFrame(rows)
    logger.info("展平完成: %d 条意见, %d 行", len(results), len(df))
    return df
