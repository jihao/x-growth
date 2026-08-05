import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { fetchDaily, fetchStocks, fetchStructure, type StructureResponse } from "../api/stocks";
import { addFavorite, fetchFavorites, removeFavorite } from "../api/favorites";
import { ChartCanvas, type ChartBar } from "../components/charts/ChartCanvas";
import { VolumePanel } from "../components/charts/VolumePanel";
import { OscillatorCanvas } from "../components/charts/OscillatorCanvas";
import { DrawingToolbar, type ToolId } from "../components/charts/DrawingToolbar";
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

const DEFAULT_VARIANTS: Record<string, string> = {
  cursor: "十字光标",
  trend: "线段",
  horizontal: "水平线段",
  shape: "矩形",
  note: "箭头注释",
  measure: "区间测量",
};

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
  const [tool, setTool] = useState<ToolId>("cursor");
  const [toolVariant, setToolVariant] = useState<Record<string, string>>(DEFAULT_VARIANTS);
  const [locked, setLocked] = useState(false);
  const [drawingsVisible, setDrawingsVisible] = useState(true);
  const [hasSelectedDrawing, setHasSelectedDrawing] = useState(false);
  const [deleteSignal, setDeleteSignal] = useState(0);
  const [structure, setStructure] = useState<StructureResponse | null>(null);
  const [starred, setStarred] = useState(false);
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
        const [daily, stocks, struct] = await Promise.all([
          fetchDaily(tsCode),
          fetchStocks().catch(() => [] as { ts_code: string; name: string }[]),
          fetchStructure(tsCode).catch(() => null),
        ]);
        if (cancelled) return;
        setRawBars(daily.bars);
        setStructure(struct);
        const favs = await fetchFavorites().catch(() => []);
        setStarred(favs.some((f) => f.ts_code === tsCode));
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

  const toggleMain = (ind: string) =>
    setMainIndicators((current) =>
      current.includes(ind) ? current.filter((item) => item !== ind) : [...current, ind],
    );

  const structureLines = useMemo(() => {
    if (!structure) return [];
    return [...structure.trendlines.up, ...structure.trendlines.down];
  }, [structure]);

  const canvasTool =
    tool === "shape" && toolVariant.shape === "椭圆" ? "ellipse" : tool;

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
            className="ghost"
            onClick={() => {
              void (async () => {
                try {
                  if (starred) {
                    await removeFavorite(tsCode);
                    setStarred(false);
                  } else {
                    await addFavorite(tsCode);
                    setStarred(true);
                  }
                } catch (err) {
                  setError(err instanceof Error ? err.message : String(err));
                }
              })();
            }}
          >
            {starred ? "★ 取消收藏" : "☆ 收藏"}
          </button>
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
          <DrawingToolbar
            tool={tool}
            toolVariant={toolVariant}
            locked={locked}
            drawingsVisible={drawingsVisible}
            hasSelectedDrawing={hasSelectedDrawing}
            onToolChange={setTool}
            onVariantChange={(id, variant) =>
              setToolVariant((current) => ({ ...current, [id]: variant }))
            }
            onLockedChange={setLocked}
            onVisibleChange={setDrawingsVisible}
            onDelete={() => setDeleteSignal((n) => n + 1)}
          />
          <div className="canvas-wrap">
            {bars.length > 0 ? (
              <>
                <ChartCanvas
                  bars={bars}
                  mainIndicators={mainIndicators}
                  overlays={[]}
                  tool={canvasTool}
                  toolVariant={toolVariant[tool] ?? "十字光标"}
                  locked={locked}
                  drawingsVisible={drawingsVisible}
                  maPeriods={maPeriods}
                  theme={theme}
                  viewStart={viewStart}
                  viewEnd={actualEnd}
                  onPan={panChart}
                  onZoom={zoomChart}
                  onCrosshair={setCrosshairRatio}
                  onDrawingSelectionChange={setHasSelectedDrawing}
                  deleteSignal={deleteSignal}
                  structureLines={structureLines}
                />
                <div className="chart-hint">
                  {locked
                    ? "画线已锁定"
                    : tool === "cursor"
                      ? `${toolVariant.cursor} · 点击画线选中，按 Delete 删除`
                      : `${toolVariant[tool]} · 再次点击图标可切换类型`}
                </div>
              </>
            ) : (
              <div className="chart-empty">{loading ? "加载图表…" : "暂无日线数据"}</div>
            )}
          </div>
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

      {structure && (
        <aside className="structure-panel" aria-label="结构分析">
          <h3>结构分析</h3>
          <p>
            趋势线 上{structure.trendlines.up.length} / 下{structure.trendlines.down.length}
            {structure.wave
              ? ` · 浪型 ${structure.wave.direction} ${structure.wave.verdict} (${structure.wave.ratio.toFixed(2)})`
              : " · 暂无浪型"}
            {` · 背离 ${structure.divergences.length} 条`}
          </p>
        </aside>
      )}
    </section>
  );
}
