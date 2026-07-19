"""
应用配置模块

从 .env 文件读取 LLM 相关配置，不写死任何密钥。
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """读取必需的环境变量，缺失时抛出明确错误。"""
    value = os.getenv(key)
    if not value:
        raise ValueError(
            f"缺少必需配置: {key}。请在项目根目录创建 .env 文件并设置 {key}。\n"
            f"可参考 .env.example 模板。"
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


LLM_API_KEY = _require("LLM_API_KEY")
LLM_BASE_URL = _require("LLM_BASE_URL")
LLM_MODEL = _require("LLM_MODEL")

LLM_TEMPERATURE = float(_optional("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(_optional("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT = int(_optional("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(_optional("LLM_MAX_RETRIES", "3"))
