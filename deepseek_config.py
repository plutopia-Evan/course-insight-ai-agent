"""
DeepSeek API 配置模块

从 .env 文件读取 DeepSeek 相关配置。
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(
            f"缺少必需配置: {key}。\n"
            f"请在项目根目录 .env 文件中设置 {key}。\n"
            f"可参考 .env.example 模板。"
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


DEEPSEEK_API_KEY = _require("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = _require("DEEPSEEK_BASE_URL")
DEEPSEEK_MODEL = _require("DEEPSEEK_MODEL")

DEEPSEEK_TEMPERATURE = float(_optional("DEEPSEEK_TEMPERATURE", "0.1"))
DEEPSEEK_MAX_TOKENS = int(_optional("DEEPSEEK_MAX_TOKENS", "2000"))
DEEPSEEK_TIMEOUT = int(_optional("DEEPSEEK_TIMEOUT", "60"))
DEEPSEEK_MAX_RETRIES = int(_optional("DEEPSEEK_MAX_RETRIES", "3"))
