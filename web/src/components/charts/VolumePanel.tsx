"use client";
import { useState } from "react";
import type { ChartBar } from "./ChartCanvas";

export function VolumePanel({ bars, crosshairRatio, onCrosshair }: { bars: ChartBar[]; crosshairRatio: number | null; onCrosshair: (ratio: number | null) => void }) {
  const [mode, setMode] = useState<"成交量" | "成交额">("成交量");
  const values = bars.map((bar) => mode === "成交量" ? bar.volume : (bar.amount || 0));
  const max = Math.max(...values);
  const last = bars[bars.length - 1];
  const average = (period: number) => values.slice(-period).reduce((sum, value) => sum + value, 0) / Math.min(period, values.length);
  const format = (value: number) => mode === "成交量" ? `${(value / 1_000_000).toFixed(2)}万手` : `${(value / 100_000_000).toFixed(2)}亿元`;
  return (
    <section className="volume-panel" onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onCrosshair(Math.max(0, Math.min(1, (event.clientX - rect.left - 59) / Math.max(1, rect.width - 129)))); }} onPointerLeave={() => onCrosshair(null)}>
      <div className="panel-tabs compact">
        {["成交量", "成交额"].map((item) => <button key={item} className={mode === item ? "active" : ""} onClick={() => setMode(item as typeof mode)}>{item}</button>)}
        <span className="panel-value">{format(mode === "成交量" ? last.volume : (last.amount || 0))}</span>
        <span className="muted">MA5 {format(average(5))}　MA10 {format(average(10))}</span>
      </div>
      <div className="volume-bars" aria-label={mode}>
        {bars.map((bar, index) => {
          const value = mode === "成交量" ? bar.volume : (bar.amount || 0);
          const ratio = max ? value / max : 0;
          return <span key={index} className={bar.close >= bar.open ? "up" : "down"} style={{ height: `${Math.max(5, ratio * 54)}px` }} title={`${mode} ${format(value)}`} />;
        })}
      </div>
      {crosshairRatio !== null && <i className="synced-crosshair" style={{ left: `calc(59px + (100% - 129px) * ${crosshairRatio})` }} />}
    </section>
  );
}
