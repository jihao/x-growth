import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { fetchConcentration, fetchRegime } from "../api/market";
import {
  fetchScreeningDates,
  fetchScreeningExplain,
  fetchScreeningResults,
} from "../api/screening";
import { fetchTrackingReview } from "../api/tracking";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function MarketPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(todayISO());
  const [regime, setRegime] = useState<Record<string, unknown> | null>(null);
  const [concentration, setConcentration] = useState<Record<string, unknown>[]>([]);
  const [screeningDates, setScreeningDates] = useState<string[]>([]);
  const [screenDate, setScreenDate] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [explain, setExplain] = useState<Record<string, unknown> | null>(null);
  const [review, setReview] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"env" | "screen" | "track">("env");

  useEffect(() => {
    void fetchScreeningDates()
      .then((dates) => {
        setScreeningDates(dates);
        if (dates[0]) setScreenDate(dates[0]);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (tab !== "env") return;
    setError(null);
    void Promise.all([
      fetchRegime(date).catch((err) => {
        throw err;
      }),
      fetchConcentration().catch(() => []),
    ])
      .then(([r, c]) => {
        setRegime(r);
        setConcentration(c.slice(-10).reverse());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [date, tab]);

  useEffect(() => {
    if (tab !== "screen" || !screenDate) return;
    setError(null);
    void fetchScreeningResults(screenDate)
      .then(setResults)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [screenDate, tab]);

  useEffect(() => {
    if (tab !== "track" || !screenDate) return;
    setError(null);
    void fetchTrackingReview(screenDate)
      .then((data) => setReview(data as unknown as Record<string, unknown>))
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [screenDate, tab]);

  return (
    <section className="module-page" aria-label="市场">
      <div className="module-hero">
        <div>
          <span>MARKET PULSE</span>
          <h1>市场环境</h1>
          <p>资金集中度、选股榜与跟踪复盘。</p>
        </div>
      </div>
      <div className="market-tabs">
        {(
          [
            ["env", "环境/集中度"],
            ["screen", "选股榜"],
            ["track", "跟踪复盘"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {error && <div className="api-banner" role="alert">{error}</div>}

      {tab === "env" && (
        <div className="market-block">
          <label>
            交易日
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {regime && (
            <div className="regime-card">
              <h3>{String(regime.summary ?? regime.level ?? "—")}</h3>
              <p>score: {String(regime.score ?? "—")}</p>
            </div>
          )}
          <h3>集中度（最近缓存）</h3>
          {concentration.length === 0 ? (
            <p className="muted">
              集中度缓存为空，请先运行：.venv/bin/python -m quant.concentration.build_cache
              --rebuild
            </p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>HHI</th>
                  <th>CR5</th>
                  <th>CR50</th>
                </tr>
              </thead>
              <tbody>
                {concentration.map((row) => (
                  <tr key={String(row.date)}>
                    <td>{String(row.date)}</td>
                    <td>{Number(row.hhi ?? 0).toFixed(4)}</td>
                    <td>{Number(row.cr5 ?? 0).toFixed(4)}</td>
                    <td>{Number(row.cr50 ?? 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "screen" && (
        <div className="market-block">
          <label>
            选股日
            <select value={screenDate} onChange={(e) => setScreenDate(e.target.value)}>
              {screeningDates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          {results.length === 0 ? (
            <p className="muted">
              暂无选股结果，请先运行：.venv/bin/python -m quant.screening.cli
            </p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>总分</th>
                  <th>解读</th>
                </tr>
              </thead>
              <tbody>
                {results.slice(0, 50).map((row) => (
                  <tr key={String(row.ts_code)}>
                    <td>
                      <button
                        type="button"
                        className="linkish"
                        onClick={() => navigate(`/stocks/${row.ts_code}`)}
                      >
                        {String(row.ts_code)}
                      </button>
                    </td>
                    <td>{String(row.name ?? "")}</td>
                    <td>{Number(row.total_score ?? 0).toFixed(3)}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() =>
                          void fetchScreeningExplain(
                            screenDate,
                            String(row.ts_code),
                          ).then(setExplain)
                        }
                      >
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {explain && (
            <pre className="explain-box">{JSON.stringify(explain, null, 2)}</pre>
          )}
        </div>
      )}

      {tab === "track" && (
        <div className="market-block">
          <label>
            选股日
            <select value={screenDate} onChange={(e) => setScreenDate(e.target.value)}>
              {screeningDates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          {review ? (
            <pre className="explain-box">{JSON.stringify(review, null, 2)}</pre>
          ) : (
            <p className="muted">选择选股日以加载跟踪复盘。</p>
          )}
        </div>
      )}
    </section>
  );
}
