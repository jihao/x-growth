import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, apiSend } from "../api/client";
import { fetchStocks } from "../api/stocks";
import type { StockItem } from "../types/market";

export function HomePage() {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchStocks()
      .then(setStocks)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  const matches = useMemo(() => {
    const q = input.trim();
    if (!q) return [];
    return stocks
      .filter((s) => s.ts_code.includes(q) || s.name.includes(q))
      .slice(0, 8);
  }, [input, stocks]);

  const openStock = (tsCode: string, name?: string) => {
    setMessages((current) => [
      ...current,
      { role: "user", text: input || tsCode },
      {
        role: "assistant",
        text: `已找到${name || tsCode}（${tsCode}），正在打开个股分析页。`,
      },
    ]);
    setInput("");
    navigate(`/stocks/${tsCode}`);
  };

  const submitSearch = () => {
    if (matches[0]) {
      openStock(matches[0].ts_code, matches[0].name);
      return;
    }
    setMessages((current) => [
      ...current,
      { role: "user", text: input },
      { role: "assistant", text: "未匹配到股票，请输入代码或名称关键词。" },
    ]);
  };

  const submitAgent = async () => {
    const value = input.trim();
    if (!value) return;
    setMessages((current) => [...current, { role: "user", text: value }]);
    setInput("");
    try {
      const res = await apiSend<{ reply: string }>("/api/v1/chat", "POST", {
        message: value,
      });
      setMessages((current) => [
        ...current,
        { role: "assistant", text: res.reply },
      ]);
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : String(err);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: detail.includes("未配置")
            ? "LLM 未配置。可先用搜索打开个股页，或配置 llm.env。"
            : detail,
        },
      ]);
    }
  };

  return (
    <section className="home-page" aria-label="量化分析主页面">
      <div className="home-hero">
        <div className="home-eyebrow">
          <i />
          QUANT WORKSPACE
        </div>
        <h1>
          用数据把研判做成<span>连续动作</span>
        </h1>
        <p>从真实行情、技术指标到结构分析，在一个连续工作流里完成个股研究。</p>
        {error && <div className="api-banner" role="alert">{error}</div>}
        <div className="home-command">
          <div className="home-input-wrap">
            <span>⌕</span>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitSearch();
              }}
              placeholder="输入股票代码、名称，或询问市场问题…"
              autoComplete="off"
            />
          </div>
          <button type="button" className="home-search-button" onClick={submitSearch}>
            搜索
          </button>
          <button type="button" className="home-agent-button" onClick={() => void submitAgent()}>
            Agent
          </button>
        </div>
        {matches.length > 0 && (
          <ul className="home-suggest">
            {matches.map((stock) => (
              <li key={stock.ts_code}>
                <button type="button" onClick={() => openStock(stock.ts_code, stock.name)}>
                  {stock.name} <small>{stock.ts_code}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="home-messages">
          {messages.map((msg, index) => (
            <p key={index} className={msg.role}>
              <b>{msg.role === "user" ? "你" : "助手"}：</b>
              {msg.text}
            </p>
          ))}
        </div>
      </div>
    </section>
  );
}
