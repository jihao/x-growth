import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { fetchDaily, fetchStocks } from "../api/stocks";
import { ChartCanvas, type ChartBar } from "../components/charts/ChartCanvas";
import { VolumePanel } from "../components/charts/VolumePanel";
import { OscillatorCanvas } from "../components/charts/OscillatorCanvas";
import { aggregateBars, type Period } from "../utils/bars";
import type { Bar } from "../types/market";

function normalizeTsCode(code: string): string {
  if (code.includes(".")) return code;
  if (code.startsWith("6") || code.startsWith("9")) return `${code}.SH`;
  return `${code}.SZ`;
}

function toChartBars(bars: Bar[]): ChartBar[] {
  return bars.map((bar) => ({
    ...bar,
    date: new Date(`${bar.date}T00:00:00`),
  }));
}

export function StockPage() {
  const { code: rawCode } = useParams();
  const tsCode = rawCode ? normalizeTsCode(rawCode) : "";
  const [name, setName] = useState("");
  const [rawBars, setRawBars] = useState<Bar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("日K");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mainIndicators, setMainIndicators] = useState<string[]>(["MA"]);
  const [subchart, setSubchart] = useState("MACD");
  const [visibleCount, setVisibleCount] = useState(120);
  const [viewEnd, setViewEnd] = useState(0);
  const [crosshairRatio, setCrosshairRatio] = useState<number | null>(null);
  const [maPeriods] = useState([5, 10, 20, 60]);
  const chartCardRef = useRef<HTMLElement>(null);

  const bars = useMemo(
    () => toChartBars(aggregateBars(rawBars, period)),
    [rawBars, period],
  );

  useEffect(() => {
    if (!tsCode) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [daily, stocks] = await Promise.all([
          fetchDaily(tsCode),
          fetchStocks().catch(() => [] as { ts_code: string; name: string }[]),
        ]);
        if (cancelled) return;
        setRawBars(daily.bars);
        const hit = stocks.find((s) => s.ts_code === tsCode);
        setName(hit?.name ?? "");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : String(err));
        setRawBars([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tsCode]);

  useEffect(() => {
    setViewEnd(bars.length);
    setVisibleCount(Math.min(120, Math.max(1, bars.length)));
  }, [bars.length, period]);

  const actualCount = Math.max(1, Math.min(visibleCount, bars.length || 1));
  const actualEnd = Math.max(actualCount, Math.min(viewEnd, bars.length));
  const viewStart = Math.max(0, actualEnd - actualCount);
  const visibleBars = bars.slice(viewStart, actualEnd);

  const panChart = (delta: number) =>
    setViewEnd((current) =>
      Math.max(actualCount, Math.min(bars.length, current + delta)),
    );
  const zoomChart = useCallback(
    (delta: number) =>
      setVisibleCount((current) =>
        Math.max(Math.min(30, bars.length), Math.min(bars.length, current + delta)),
      ),
    [bars.length],
  );

  useEffect(() => {
    const chartCard = chartCardRef.current;
    if (!chartCard) return;
    const handleWheel = (event: WheelEvent) => {
      const target = event.target;
      if (
        !(target instanceof Element) ||
        !target.closest(".main-chart-area,.volume-panel,.subchart-panel")
      ) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      zoomChart(event.deltaY > 0 ? 8 : -8);
    };
    chartCard.addEventListener("wheel", handleWheel, { passive: false });
    return () => chartCard.removeEventListener("wheel", handleWheel);
  }, [zoomChart]);

  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2] || last;
  const change = last && prev ? last.close - prev.close : 0;
  const changePct = last && prev && prev.close ? (change / prev.close) * 100 : 0;

  const toggleMain = (name: string) =>
    setMainIndicators((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );

  return (
    <section className={theme === "dark" ? "theme-dark" : undefined} aria-label="个股分析">
      {error && (
        <div className="api-banner" role="alert">
          {error}
        </div>
      )}
      <header className="quote-header">
        <div className="stock-title">
          <span className="market-badge">{tsCode.endsWith(".SH") ? "沪" : "深"}</span>
          <div>
            <h1>
              {name || "个股"} <small>{tsCode}</small>
            </h1>
            <p>
              {loading ? "加载中…" : `${bars.length} 根 · ${period}`}
              <span className="data-tag">真数据</span>
            </p>
          </div>
        </div>
        <div className={`headline-price ${change >= 0 ? "red" : "green"}`}>
          <strong>{last ? last.close.toFixed(2) : "--"}</strong>
          <span>
            {change >= 0 ? "+" : ""}
            {change.toFixed(2)} ({changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%)
          </span>
        </div>
        <div className="quote-stats">
          <div>
            <label>开</label>
            <b>{last ? last.open.toFixed(2) : "--"}</b>
          </div>
          <div>
            <label>高</label>
            <b>{last ? last.high.toFixed(2) : "--"}</b>
          </div>
          <div>
            <label>低</label>
            <b>{last ? last.low.toFixed(2) : "--"}</b>
          </div>
          <div>
            <label>量</label>
            <b>{last ? (last.volume / 100).toFixed(0) : "--"}</b>
          </div>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            {theme === "light" ? "深色" : "浅色"}
          </button>
        </div>
      </header>

      <div className="chart-commandbar">
        <div className="range-group">
          {(["日K", "周K", "月K"] as Period[]).map((item) => (
            <button
              key={item}
              type="button"
              className={period === item ? "active" : ""}
              onClick={() => setPeriod(item)}
            >
              {item}
            </button>
          ))}
          <span />
          {["MA", "EMA", "BOLL"].map((item) => (
            <button
              key={item}
              type="button"
              className={mainIndicators.includes(item) ? "active-light" : ""}
              onClick={() => toggleMain(item)}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="adjust-group">
          <button type="button" className="zoom-button" onClick={() => zoomChart(8)}>
            −
          </button>
          <button type="button" className="zoom-button" onClick={() => zoomChart(-8)}>
            ＋
          </button>
        </div>
      </div>

      <article className="chart-card" ref={chartCardRef}>
        <div className="main-chart-area">
          {bars.length > 0 ? (
            <ChartCanvas
              bars={bars}
              mainIndicators={mainIndicators}
              overlays={[]}
              tool="cursor"
              toolVariant="普通光标"
              locked={false}
              drawingsVisible={true}
              maPeriods={maPeriods}
              theme={theme}
              viewStart={viewStart}
              viewEnd={actualEnd}
              onPan={panChart}
              onZoom={zoomChart}
              onCrosshair={setCrosshairRatio}
              onDrawingSelectionChange={() => undefined}
              deleteSignal={0}
            />
          ) : (
            <div className="chart-empty">{loading ? "加载图表…" : "暂无日线数据"}</div>
          )}
        </div>
        {visibleBars.length > 0 && (
          <VolumePanel
            bars={visibleBars}
            crosshairRatio={crosshairRatio}
            onCrosshair={setCrosshairRatio}
          />
        )}
        <div className="subchart-panel">
          <div className="subchart-head">
            {["MACD", "KDJ", "RSI"].map((item) => (
              <button
                key={item}
                type="button"
                className={subchart === item ? "active" : ""}
                onClick={() => setSubchart(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <OscillatorCanvas
            type={subchart}
            theme={theme}
            crosshairRatio={crosshairRatio}
            onCrosshair={setCrosshairRatio}
            selectable
            viewStart={viewStart}
            viewEnd={actualEnd}
          />
        </div>
      </article>
    </section>
  );
}
