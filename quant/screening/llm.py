"""LLM 深度解读：OpenAI 兼容接口（DeepSeek/Kimi/Qwen 等均可）。

配置（仓库根目录 llm.env，或环境变量）：
    LLM_BASE_URL   默认 https://api.deepseek.com
    LLM_API_KEY    必填，未配置时功能降级为仅规则解读
    LLM_MODEL      默认 deepseek-chat
    LLM_TIMEOUT    请求超时秒数，默认 30
"""
from __future__ import annotations

import json
import os

import requests

from quant import config  # noqa: F401  # 注入 database/mysql 到 sys.path
from mysql_config import load_dotenv

_ENV_PATH = config.ROOT / "llm.env"

_SYSTEM_PROMPT = (
    "你是一位严谨的 A 股量化分析助手。根据用户提供的选股评分与因子数据，"
    "用通俗中文输出三段内容：\n"
    "1) 评分解读：哪些因素支撑、哪些因素拖累；\n"
    "2) 交易建议：明确给出买入/加仓/持有/减仓/抛出之一，"
    "并说明仓位思路与止损参考位；\n"
    "3) 主要风险提示。\n"
    "总计不超过 250 字，不要使用 markdown 标题。"
    "结尾必须单独一行注明：以上仅供参考，不构成投资建议。"
)


def _load_env() -> None:
    load_dotenv(str(_ENV_PATH))


def llm_settings() -> dict | None:
    """读取 LLM 配置；未配置 API Key 时返回 None。"""
    _load_env()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "api_key": api_key,
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "timeout": float(os.environ.get("LLM_TIMEOUT", "30")),
    }


def is_configured() -> bool:
    return llm_settings() is not None


def build_messages(payload: dict) -> list[dict]:
    """payload：{stock, scores, rule_action, rule_reasons, factors}。"""
    user = (
        f"股票：{payload.get('stock', '')}\n"
        f"选股评分：{json.dumps(payload.get('scores', {}), ensure_ascii=False)}\n"
        f"规则引擎给出的建议：{payload.get('rule_action', '')}\n"
        f"规则引擎的判断依据：{json.dumps(payload.get('rule_reasons', []), ensure_ascii=False)}\n"
        f"因子明细：{json.dumps(payload.get('factors', {}), ensure_ascii=False)}\n"
        "请基于以上数据给出解读与交易建议。"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def chat(messages: list[dict]) -> str:
    """调用 OpenAI 兼容 chat completions，返回文本。未配置/失败时抛异常。"""
    st = llm_settings()
    if st is None:
        raise RuntimeError(
            "未配置 LLM_API_KEY，请在仓库根目录创建 llm.env（参考 llm.env.example）。"
        )
    resp = requests.post(
        f"{st['base_url']}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {st['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": st["model"],
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 600,
        },
        timeout=st["timeout"],
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def explain_with_llm(payload: dict) -> str:
    return chat(build_messages(payload))
