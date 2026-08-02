from __future__ import annotations

import pytest

from quant.screening import llm


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)
    # 隔离真实 llm.env 文件
    monkeypatch.setattr(llm, "_ENV_PATH", llm.config.ROOT / "__no_such_llm.env__")


def test_settings_none_without_api_key():
    assert llm.llm_settings() is None
    assert llm.is_configured() is False


def test_settings_defaults_with_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    st = llm.llm_settings()
    assert st["base_url"] == "https://api.deepseek.com"
    assert st["model"] == "deepseek-chat"
    assert st["timeout"] == 30.0
    assert llm.is_configured() is True


def test_settings_overrides(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.moonshot.cn/")
    monkeypatch.setenv("LLM_MODEL", "kimi-k2")
    st = llm.llm_settings()
    assert st["base_url"] == "https://api.moonshot.cn"  # 尾部斜杠被去掉
    assert st["model"] == "kimi-k2"


def test_build_messages_contains_key_data():
    payload = {
        "stock": "600519.SH 贵州茅台",
        "scores": {"总分": 0.91},
        "rule_action": "买入参考",
        "rule_reasons": ["支撑因素：底背离已确认"],
        "factors": {"strategy": {"ma_cross": {"signal": 1}}},
    }
    msgs = llm.build_messages(payload)
    assert msgs[0]["role"] == "system"
    assert "不构成投资建议" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "600519.SH 贵州茅台" in user
    assert "买入参考" in user
    assert "底背离已确认" in user


def test_chat_raises_without_config():
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_chat_posts_and_returns_content(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": " 解读文本 "}}]}

    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(llm.requests, "post", _post)
    out = llm.chat([{"role": "user", "content": "hi"}])
    assert out == "解读文本"
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["json"]["temperature"] == 0.3
