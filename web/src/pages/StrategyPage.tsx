import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import {
  fetchStrategies,
  runBacktest,
  type BacktestResponse,
  type StrategyInfo,
} from "../api/backtest";

type RecordItem = BacktestResponse & { id: number; ranAt: string };

export function StrategyPage() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [strategy, setStrategy] = useState("ma_cross");
  const [tsCode, setTsCode] = useState("600519.SH");
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("");
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void fetchStrategies()
      .then((list) => {
        setStrategies(list);
        if (list[0]) setStrategy(list[0].name);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  const onRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await runBacktest(tsCode, strategy, start || undefined, end || undefined);
      setRecords((current) => [
        {
          ...result,
          id: Date.now(),
          ranAt: new Date().toLocaleString(),
        },
        ...current,
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="module-page strategy-page" aria-label="策略">
      <div className="module-hero">
        <div>
          <span>STRATEGY STUDIO</span>
          <h1>经典策略回测</h1>
          <p>多因子滑条权重落库为二期；当前接入 `quant.backtest` 经典策略。</p>
        </div>
      </div>
      {error && <div className="api-banner" role="alert">{error}</div>}
      <div className="strategy-form">
        <label>
          策略
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            {strategies.map((s) => (
              <option key={s.name} value={s.name}>
                {s.label} ({s.name})
              </option>
            ))}
          </select>
        </label>
        <label>
          股票
          <input value={tsCode} onChange={(e) => setTsCode(e.target.value)} />
        </label>
        <label>
          开始
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          结束
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <button type="button" disabled={running} onClick={() => void onRun()}>
          {running ? "回测中…" : "提交回测"}
        </button>
      </div>
      <div className="backtest-table">
        <div>
          <b>时间</b>
          <b>策略</b>
          <b>标的</b>
          <b>累计收益</b>
          <b>年化</b>
          <b>最大回撤</b>
          <b>夏普</b>
          <b>交易次数</b>
        </div>
        {records.map((record) => (
          <div key={record.id}>
            <span>{record.ranAt}</span>
            <strong>{record.strategy}</strong>
            <span>{record.ts_code}</span>
            <b className="red">
              {((record.metrics.total_return ?? 0) * 100).toFixed(2)}%
            </b>
            <b className="red">
              {((record.metrics.ann_return ?? 0) * 100).toFixed(2)}%
            </b>
            <b className="green">
              {((record.metrics.max_drawdown ?? 0) * 100).toFixed(2)}%
            </b>
            <b>{(record.metrics.sharpe ?? 0).toFixed(2)}</b>
            <b>{record.metrics.num_trades ?? 0}</b>
          </div>
        ))}
      </div>
    </section>
  );
}
