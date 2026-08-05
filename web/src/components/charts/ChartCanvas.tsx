"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ema, ma } from "../../utils/bars";

export type ChartBar = {
  date: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number;
};

type Point = { x: number; y: number };
type Drawing = {
  type: "trend" | "horizontal" | "rect" | "ellipse" | "note" | "measure";
  start: Point;
  end: Point;
  text?: string;
  variant?: string;
};

// Adapt ma/ema: convert null -> NaN for canvas drawing
function maN(values: number[], period: number): number[] {
  return ma(values, period).map((v) => (v == null ? Number.NaN : v));
}
function emaN(values: number[], period: number): number[] {
  return ema(values, period);
}

export function ChartCanvas({ bars, mainIndicators, overlays, tool, toolVariant, locked, drawingsVisible, maPeriods, theme, viewStart, viewEnd, onPan, onZoom: _onZoom, onCrosshair, onDrawingSelectionChange, deleteSignal }: {
  bars: ChartBar[];
  mainIndicators: string[];
  overlays: string[];
  tool: string;
  toolVariant: string;
  locked: boolean;
  drawingsVisible: boolean;
  maPeriods: number[];
  theme: "light" | "dark";
  viewStart: number;
  viewEnd: number;
  onPan: (bars: number) => void;
  onZoom: (delta: number) => void;
  onCrosshair: (ratio: number | null) => void;
  onDrawingSelectionChange: (selected: boolean) => void;
  deleteSignal: number;
}) {
  void _onZoom;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [draft, setDraft] = useState<Drawing | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [selectedBar, setSelectedBar] = useState<number | null>(null);
  const [selectedSeries, setSelectedSeries] = useState<{ name: string; index: number; value: number } | null>(null);
  const [crosshair, setCrosshair] = useState<Point | null>(null);
  const [snapTarget, setSnapTarget] = useState<number | null>(null);
  const [noteAnchor, setNoteAnchor] = useState<Point | null>(null);
  const panRef = useRef<{ x: number; sent: number } | null>(null);
  const dragRef = useRef<{ index: number; origin: Point; drawing: Drawing } | null>(null);
  const handledDeleteSignal = useRef(deleteSignal);

  const close = useMemo(() => bars.map((b) => b.close), [bars]);
  const series = useMemo(() => {
    const maLines = maPeriods.map((period) => maN(close, period));
    const ma20 = maN(close, 20);
    const ema8 = emaN(close, 8);
    const ema21 = emaN(close, 21);
    const wma20 = close.map((_, index) => {
      if (index < 19) return Number.NaN;
      let total = 0;
      let weight = 0;
      for (let p = 1; p <= 20; p++) {
        total += close[index - 20 + p] * p;
        weight += p;
      }
      return total / weight;
    });
    const bbi = close.map((_, i) => {
      const values = [maN(close, 3)[i], maN(close, 6)[i], maN(close, 12)[i], maN(close, 24)[i]];
      return values.every(Number.isFinite) ? values.reduce((a, b) => a + b, 0) / 4 : Number.NaN;
    });
    return { maLines, ema8, ema21, wma20, bbi, ma20 };
  }, [close, maPeriods]);
  const selectableSeries = useMemo(() => {
    const output: { name: string; values: number[] }[] = [];
    if (mainIndicators.includes("MA")) series.maLines.forEach((values, index) => output.push({ name: `MA${maPeriods[index]}`, values }));
    if (mainIndicators.includes("EMA")) output.push({ name: "EMA8", values: series.ema8 }, { name: "EMA21", values: series.ema21 });
    if (mainIndicators.includes("BOLL")) {
      const mid = maN(close, 20);
      const upper = mid.map((m, index) => {
        if (!Number.isFinite(m) || index < 19) return Number.NaN;
        const slice = close.slice(index - 19, index + 1);
        const sd = Math.sqrt(slice.reduce((sum, value) => sum + (value - m) ** 2, 0) / 20);
        return m + sd * 2;
      });
      output.push({ name: "BOLL上轨", values: upper }, { name: "BOLL中轨", values: mid }, { name: "BOLL下轨", values: upper.map((value, index) => Number.isFinite(value) ? mid[index] * 2 - value : Number.NaN) });
    }
    if (mainIndicators.includes("MAE")) output.push({ name: "MAE上轨", values: series.ma20.map((v) => v * 1.055) }, { name: "MAE中轨", values: series.ma20 }, { name: "MAE下轨", values: series.ma20.map((v) => v * .945) });
    if (overlays.includes("BBI")) output.push({ name: "BBI", values: series.bbi });
    if (overlays.includes("WMA")) output.push({ name: "WMA20", values: series.wma20 });
    return output;
  }, [close, maPeriods, mainIndicators, overlays, series]);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.round(rect.width * dpr);
    const pixelHeight = Math.round(rect.height * dpr);
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = rect.width;
    const h = rect.height;
    const pad = { left: 18, right: 70, top: 14, bottom: 34 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const visible = bars.slice(viewStart, viewEnd);
    if (!visible.length) return;
    const priceSpan = Math.max(...visible.map((b) => b.high)) - Math.min(...visible.map((b) => b.low));
    const min = Math.min(...visible.map((b) => b.low)) - priceSpan * .06;
    const max = Math.max(...visible.map((b) => b.high)) + priceSpan * .06;
    const x = (index: number) => pad.left + ((index - viewStart) / Math.max(1, viewEnd - viewStart - 1)) * plotW;
    const y = (value: number) => pad.top + ((max - value) / (max - min)) * plotH;
    const screenPoint = (point: Point) => ({ x: x(point.x), y: y(point.y) });

    const dark = theme === "dark";
    ctx.fillStyle = dark ? "#111820" : "#fff";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = dark ? "#29323c" : "#e8edf2";
    ctx.lineWidth = 1;
    ctx.font = "11px Arial";
    for (let i = 0; i <= 6; i++) {
      const py = pad.top + (plotH / 6) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(w - pad.right + 8, py);
      ctx.stroke();
      const price = max - ((max - min) / 6) * i;
      ctx.fillStyle = dark ? "#8d9aa8" : "#7d8793";
      ctx.fillText(price.toFixed(0), w - pad.right + 14, py + 4);
    }
    const dateStep = Math.max(1, Math.round((viewEnd - viewStart) / 8));
    for (let i = viewStart; i < viewEnd; i += dateStep) {
      const px = x(i);
      ctx.beginPath();
      ctx.moveTo(px, pad.top);
      ctx.lineTo(px, h - pad.bottom);
      ctx.stroke();
      ctx.fillStyle = dark ? "#7f8b98" : "#8d98a5";
      ctx.textAlign = "center";
      ctx.fillText(`${bars[i].date.getMonth() + 1}月`, px, h - 12);
    }
    ctx.textAlign = "start";

    const candleWidth = Math.max(3, Math.min(11, (plotW / Math.max(1, viewEnd - viewStart)) * 0.66));
    bars.forEach((bar, index) => {
      if (index < viewStart || index >= viewEnd) return;
      const px = x(index);
      const up = bar.close >= bar.open;
      ctx.strokeStyle = up ? "#d92d20" : "#15905f";
      ctx.fillStyle = up ? "#d92d20" : "#15905f";
      ctx.beginPath();
      ctx.moveTo(px, y(bar.high));
      ctx.lineTo(px, y(bar.low));
      ctx.stroke();
      const top = y(Math.max(bar.open, bar.close));
      const height = Math.max(1, Math.abs(y(bar.open) - y(bar.close)));
      ctx.fillRect(px - candleWidth / 2, top, candleWidth, height);
      if (selectedBar === index) {
        ctx.save(); ctx.strokeStyle = "#1c63d5"; ctx.lineWidth = 2;
        ctx.strokeRect(px - candleWidth / 2 - 3, y(bar.high) - 4, candleWidth + 6, Math.max(8, y(bar.low) - y(bar.high) + 8)); ctx.restore();
      }
    });

    const drawSeries = (values: number[], color: string, width = 1.35, dash: number[] = []) => {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let started = false;
      values.forEach((value, index) => {
        if (index < viewStart || index >= viewEnd) return;
        if (!Number.isFinite(value)) return;
        if (!started) {
          ctx.moveTo(x(index), y(value));
          started = true;
        } else ctx.lineTo(x(index), y(value));
      });
      ctx.stroke();
      ctx.restore();
    };

    if (mainIndicators.includes("MA")) {
      const colors = ["#e24a3b", "#df9d21", "#7b61c7", "#1683a8", "#37a271"];
      series.maLines.forEach((line, index) => drawSeries(line, colors[index % colors.length]));
    }
    if (mainIndicators.includes("EMA")) {
      drawSeries(series.ema8, "#e24a3b");
      drawSeries(series.ema21, "#2569c9");
    }
    if (mainIndicators.includes("BOLL")) {
      const mid = maN(close, 20);
      const upper = mid.map((m, index) => {
        if (!Number.isFinite(m) || index < 19) return Number.NaN;
        const slice = close.slice(index - 19, index + 1);
        const sd = Math.sqrt(slice.reduce((sum, value) => sum + (value - m) ** 2, 0) / 20);
        return m + sd * 2;
      });
      const lower = upper.map((u, index) => Number.isFinite(u) ? mid[index] * 2 - u : Number.NaN);
      drawSeries(upper, "#b962d0");
      drawSeries(mid, "#e39a21");
      drawSeries(lower, "#b962d0");
    }
    if (mainIndicators.includes("SAR")) {
      ctx.fillStyle = "#5967d8";
      bars.forEach((bar, i) => {
        if (i < viewStart || i >= viewEnd) return;
        if (i % 2) return;
        const value = i < 60 || i > 94 ? bar.low - 12 : bar.high + 12;
        ctx.beginPath();
        ctx.arc(x(i), y(value), 2.3, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    if (mainIndicators.includes("MAE")) {
      drawSeries(series.ma20.map((v) => v * 1.055), "#9c65ca");
      drawSeries(series.ma20, "#e39a21");
      drawSeries(series.ma20.map((v) => v * 0.945), "#9c65ca");
    }

    if (overlays.includes("BBI")) drawSeries(series.bbi, "#136f63", 1.8);
    if (overlays.includes("WMA")) drawSeries(series.wma20, "#de6575", 1.7);
    if (overlays.includes("线性回归")) {
      const start = close[82];
      const end = close[close.length - 1];
      const line = close.map((_, i) => i < 82 ? Number.NaN : start + ((end - start) * (i - 82)) / (close.length - 1 - 82));
      drawSeries(line, "#395fb5", 1.5, [6, 4]);
    }
    if (overlays.includes("价格通道")) {
      const top = close.map((_, i) => i < 19 ? Number.NaN : Math.max(...bars.slice(i - 19, i + 1).map((b) => b.high)));
      const bottom = close.map((_, i) => i < 19 ? Number.NaN : Math.min(...bars.slice(i - 19, i + 1).map((b) => b.low)));
      drawSeries(top, "#2a7db2", 1.1, [5, 3]);
      drawSeries(bottom, "#2a7db2", 1.1, [5, 3]);
    }
    if (overlays.includes("TSF")) drawSeries(emaN(close, 14).map((v, i, a) => i ? v + (v - a[i - 1]) * 3 : v), "#7145af", 1.4);

    if (selectedSeries) {
      const selectedValues = selectableSeries.find((item) => item.name === selectedSeries.name)?.values;
      if (selectedValues) {
        drawSeries(selectedValues, "#1c63d5", 3);
        const px = x(selectedSeries.index); const py = y(selectedSeries.value);
        ctx.save(); ctx.fillStyle = "#1c63d5"; ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI * 2); ctx.fill();
        const label = `${selectedSeries.name} ${selectedSeries.value.toFixed(2)}`;
        ctx.font = "12px Arial"; const boxW = ctx.measureText(label).width + 18;
        ctx.fillRect(Math.min(px + 8, w - pad.right - boxW), Math.max(8, py - 29), boxW, 23);
        ctx.fillStyle = "white"; ctx.fillText(label, Math.min(px + 17, w - pad.right - boxW + 9), Math.max(24, py - 13)); ctx.restore();
      }
    }
    if (selectedBar !== null && bars[selectedBar]) {
      const bar = bars[selectedBar]; const px = x(selectedBar); const py = y(bar.high);
      const label = `${bar.date.toISOString().slice(0, 10)}  开${bar.open.toFixed(2)} 高${bar.high.toFixed(2)} 低${bar.low.toFixed(2)} 收${bar.close.toFixed(2)}`;
      ctx.save(); ctx.font = "12px Arial"; const boxW = ctx.measureText(label).width + 18; const left = Math.max(pad.left, Math.min(px + 9, w - pad.right - boxW));
      ctx.fillStyle = "#1c63d5"; ctx.fillRect(left, Math.max(8, py - 32), boxW, 23); ctx.fillStyle = "white"; ctx.fillText(label, left + 9, Math.max(24, py - 16)); ctx.restore();
    }

    const allDrawings = draft ? [...drawings, draft] : drawings;
    if (drawingsVisible) {
      allDrawings.forEach((drawing, index) => {
        const active = index === selected || index === snapTarget;
        const start = screenPoint(drawing.start);
        const end = screenPoint(drawing.end);
        ctx.save();
        const drawingColor = dark ? "#d6dde5" : "#3f4852";
        ctx.strokeStyle = active ? "#1c63d5" : drawingColor;
        ctx.fillStyle = active ? "#1c63d5" : drawingColor;
        ctx.lineWidth = active ? 2 : 1.5;
        if (drawing.type === "horizontal") {
          ctx.beginPath();
          ctx.moveTo(start.x, start.y);
          ctx.lineTo(end.x, start.y);
          ctx.stroke();
        } else if (drawing.type === "rect") {
          ctx.strokeRect(start.x, start.y, end.x - start.x, end.y - start.y);
        } else if (drawing.type === "ellipse") {
          ctx.beginPath();
          ctx.ellipse((start.x + end.x) / 2, (start.y + end.y) / 2, Math.abs(end.x - start.x) / 2, Math.abs(end.y - start.y) / 2, 0, 0, Math.PI * 2);
          ctx.stroke();
        } else if (drawing.type === "note") {
          const tx = end.x;
          const ty = end.y;
          ctx.beginPath(); ctx.moveTo(tx, ty + 16); ctx.lineTo(start.x, start.y); ctx.stroke();
          const angle = Math.atan2(start.y - (ty + 16), start.x - tx);
          ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(start.x - 9 * Math.cos(angle - .45), start.y - 9 * Math.sin(angle - .45)); ctx.moveTo(start.x, start.y); ctx.lineTo(start.x - 9 * Math.cos(angle + .45), start.y - 9 * Math.sin(angle + .45)); ctx.stroke();
          const text = drawing.text || "注释";
          const boxW = Math.max(80, ctx.measureText(text).width + 24);
          ctx.fillStyle = dark ? "rgba(20,29,38,.63)" : "rgba(255,255,255,.63)";
          ctx.strokeStyle = active ? "#1c63d5" : "#9aa7b5";
          ctx.fillRect(tx - 6, ty - 9, boxW, 30);
          ctx.strokeRect(tx - 6, ty - 9, boxW, 30);
          ctx.fillStyle = dark ? "#e6edf4" : "#273849";
          ctx.font = "12px Arial";
          ctx.fillText(text, tx + 6, ty + 10);
        } else {
          let lineEnd = end;
          if (drawing.type === "trend" && drawing.variant === "射线" && Math.abs(end.x - start.x) > 1) {
            const targetX = end.x >= start.x ? w - pad.right + 8 : pad.left;
            const t = (targetX - start.x) / (end.x - start.x);
            lineEnd = { x: targetX, y: start.y + (end.y - start.y) * t };
          }
          ctx.beginPath();
          ctx.moveTo(start.x, start.y);
          ctx.lineTo(lineEnd.x, lineEnd.y);
          ctx.stroke();
          if (drawing.type === "measure") {
            const pct = ((drawing.end.y - drawing.start.y) / drawing.start.y) * 100;
            const days = Math.abs(Math.round(drawing.end.x - drawing.start.x));
            const label = drawing.variant === "价格测量" ? `${drawing.end.y - drawing.start.y >= 0 ? "+" : ""}${(drawing.end.y - drawing.start.y).toFixed(2)}` : drawing.variant === "时间测量" ? `${days}个交易周期` : `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}% · ${days}日`;
            ctx.fillStyle = "rgba(28,99,213,.9)";
            ctx.fillRect(end.x - 2, end.y - 28, 120, 22);
            ctx.fillStyle = "white";
            ctx.font = "11px Arial";
            ctx.fillText(label, end.x + 5, end.y - 13);
          }
        }
        if (active && drawing.type !== "note") {
          [start, end].forEach((p) => {
            ctx.fillStyle = "white";
            ctx.strokeStyle = "#1c63d5";
            ctx.fillRect(p.x - 3, p.y - 3, 6, 6);
            ctx.strokeRect(p.x - 3, p.y - 3, 6, 6);
          });
        }
        ctx.restore();
      });
    }

    if (crosshair) {
      ctx.save();
      ctx.strokeStyle = "#7b8794";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(crosshair.x, pad.top);
      ctx.lineTo(crosshair.x, h - pad.bottom);
      ctx.moveTo(pad.left, crosshair.y);
      ctx.lineTo(w - pad.right + 8, crosshair.y);
      ctx.stroke();
      const price = max - ((crosshair.y - pad.top) / plotH) * (max - min);
      ctx.fillStyle = "#334155";
      ctx.fillRect(w - pad.right + 7, crosshair.y - 10, 62, 20);
      ctx.fillStyle = "white";
      ctx.font = "11px Arial";
      ctx.fillText(price.toFixed(2), w - pad.right + 13, crosshair.y + 4);
      ctx.restore();
    }
  }, [bars, close, crosshair, draft, drawings, drawingsVisible, mainIndicators, overlays, selectableSeries, selected, selectedBar, selectedSeries, series, snapTarget, theme, viewEnd, viewStart]);

  useEffect(() => {
    redraw();
    const observer = new ResizeObserver(redraw);
    if (canvasRef.current?.parentElement) observer.observe(canvasRef.current.parentElement);
    return () => observer.disconnect();
  }, [redraw]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.key === "Delete" || event.key === "Backspace") && selected !== null && !locked) {
        setDrawings((current) => current.filter((_, index) => index !== selected));
        setSelected(null);
        onDrawingSelectionChange(false);
      }
      if (event.key === "Escape") { setDraft(null); setNoteAnchor(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [locked, onDrawingSelectionChange, selected]);

  useEffect(() => {
    if (deleteSignal === handledDeleteSignal.current) return;
    handledDeleteSignal.current = deleteSignal;
    if (selected === null || locked) return;
    setDrawings((current) => current.filter((_, index) => index !== selected));
    setSelected(null);
    onDrawingSelectionChange(false);
  }, [deleteSignal, locked, onDrawingSelectionChange, selected]);

  const pointForEvent = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const geometry = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const pad = { left: 18, right: 70, top: 14, bottom: 34 };
    const visible = bars.slice(viewStart, viewEnd);
    const span = Math.max(...visible.map((b) => b.high)) - Math.min(...visible.map((b) => b.low));
    return { pad, plotW: rect.width - pad.left - pad.right, plotH: rect.height - pad.top - pad.bottom, min: Math.min(...visible.map((b) => b.low)) - span * .06, max: Math.max(...visible.map((b) => b.high)) + span * .06 };
  };
  const toData = (point: Point) => {
    const g = geometry();
    if (!g) return point;
    return { x: viewStart + ((point.x - g.pad.left) / g.plotW) * Math.max(1, viewEnd - viewStart - 1), y: g.max - ((point.y - g.pad.top) / g.plotH) * (g.max - g.min) };
  };
  const toScreen = (point: Point) => {
    const g = geometry();
    if (!g) return point;
    return { x: g.pad.left + ((point.x - viewStart) / Math.max(1, viewEnd - viewStart - 1)) * g.plotW, y: g.pad.top + ((g.max - point.y) / (g.max - g.min)) * g.plotH };
  };
  const nearestOnSegment = (point: Point, start: Point, end: Point) => {
    const dx = end.x - start.x; const dy = end.y - start.y;
    const t = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / Math.max(1, dx * dx + dy * dy)));
    return { point: { x: start.x + dx * t, y: start.y + dy * t }, distance: Math.hypot(point.x - start.x - dx * t, point.y - start.y - dy * t) };
  };
  const drawingHitDistance = (screen: Point, drawing: Drawing) => {
    const start = toScreen(drawing.start); const end = toScreen(drawing.end);
    if (drawing.type === "rect") {
      const left = Math.min(start.x, end.x); const right = Math.max(start.x, end.x); const top = Math.min(start.y, end.y); const bottom = Math.max(start.y, end.y);
      if (screen.x >= left - 5 && screen.x <= right + 5 && screen.y >= top - 5 && screen.y <= bottom + 5) return 0;
    }
    if (drawing.type === "ellipse") {
      const rx = Math.max(4, Math.abs(end.x - start.x) / 2); const ry = Math.max(4, Math.abs(end.y - start.y) / 2);
      const cx = (start.x + end.x) / 2; const cy = (start.y + end.y) / 2;
      if (((screen.x - cx) / rx) ** 2 + ((screen.y - cy) / ry) ** 2 <= 1.18) return 0;
    }
    if (drawing.type === "note") {
      const boxW = Math.max(80, (drawing.text?.length || 2) * 13 + 24);
      if (screen.x >= end.x - 8 && screen.x <= end.x + boxW && screen.y >= end.y - 12 && screen.y <= end.y + 24) return 0;
    }
    const segmentEnd = drawing.type === "horizontal" ? { x: end.x, y: start.y } : end;
    return nearestOnSegment(screen, start, segmentEnd).distance;
  };
  const snap = (screen: Point) => {
    let best = { point: screen, distance: 11, index: null as number | null };
    drawings.forEach((drawing, index) => {
      if (drawing.type !== "trend" && drawing.type !== "horizontal") return;
      const candidate = nearestOnSegment(screen, toScreen(drawing.start), toScreen(drawing.end));
      if (candidate.distance < best.distance) best = { ...candidate, index };
    });
    setSnapTarget(best.index);
    return best.point;
  };

  const pointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (locked) return;
    const screen = pointForEvent(event);
    const point = toData(screen);
    if (tool === "cursor") {
      let nearest: number | null = null;
      let distance = 10;
      drawings.forEach((drawing, index) => {
        const d = drawingHitDistance(screen, drawing);
        if (d < distance) {
          distance = d;
          nearest = index;
        }
      });
      setSelected(nearest);
      onDrawingSelectionChange(nearest !== null);
      setSelectedBar(null); setSelectedSeries(null);
      if (toolVariant === "普通光标" && nearest !== null) {
        dragRef.current = { index: nearest, origin: point, drawing: { ...drawings[nearest], start: { ...drawings[nearest].start }, end: { ...drawings[nearest].end } } };
        event.currentTarget.setPointerCapture(event.pointerId);
        return;
      }
      if (toolVariant === "普通光标" && nearest === null) {
        const index = Math.max(viewStart, Math.min(viewEnd - 1, Math.round(point.x)));
        let nearestSeries: { name: string; index: number; value: number } | null = null;
        let seriesDistance = 9;
        selectableSeries.forEach((item) => {
          const value = item.values[index];
          if (!Number.isFinite(value)) return;
          const distanceToLine = Math.abs(screen.y - toScreen({ x: index, y: value }).y);
          if (distanceToLine < seriesDistance) { seriesDistance = distanceToLine; nearestSeries = { name: item.name, index, value }; }
        });
        if (nearestSeries) { setSelectedSeries(nearestSeries); return; }
        const bar = bars[index];
        if (bar) {
          const highY = toScreen({ x: index, y: bar.high }).y;
          const lowY = toScreen({ x: index, y: bar.low }).y;
          const candleStep = (geometry()?.plotW || 1) / Math.max(1, viewEnd - viewStart);
          if (Math.abs(screen.x - toScreen({ x: index, y: bar.close }).x) <= Math.max(6, candleStep * .45) && screen.y >= highY - 7 && screen.y <= lowY + 7) { setSelectedBar(index); return; }
        }
        panRef.current = { x: screen.x, sent: 0 };
      }
      return;
    }
    if (tool === "note") {
      if (!noteAnchor) { setNoteAnchor(point); setDraft({ type: "note", start: point, end: point, text: "定位注释", variant: toolVariant }); }
      else {
        let text: string | null;
        if (toolVariant === "价格注释") text = noteAnchor.y.toFixed(2);
        else if (toolVariant === "日期注释") {
          const index = Math.max(0, Math.min(bars.length - 1, Math.round(noteAnchor.x)));
          text = bars[index].date.toISOString().slice(0, 10);
        } else text = window.prompt("输入注释内容", "放量突破");
        if (text) setDrawings((current) => [...current, { type: "note", start: noteAnchor, end: point, text, variant: toolVariant }]);
        setNoteAnchor(null); setDraft(null);
      }
      return;
    }
    const startScreen = tool === "trend" || tool === "horizontal" ? snap(screen) : screen;
    const start = toData(startScreen);
    const type = tool === "ellipse" ? "ellipse" : tool === "shape" ? "rect" : tool === "measure" ? "measure" : tool === "horizontal" ? "horizontal" : "trend";
    setDraft({ type, start, end: start, variant: toolVariant });
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const pointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const screen = pointForEvent(event);
    setCrosshair(screen);
    const g = geometry();
    if (g) onCrosshair(Math.max(0, Math.min(1, (screen.x - g.pad.left) / g.plotW)));
    if (dragRef.current) {
      const current = toData(screen); const drag = dragRef.current;
      const dx = current.x - drag.origin.x; const dy = current.y - drag.origin.y;
      setDrawings((items) => items.map((drawing, index) => index === drag.index ? { ...drag.drawing, start: { x: drag.drawing.start.x + dx, y: drag.drawing.start.y + dy }, end: { x: drag.drawing.end.x + dx, y: drag.drawing.end.y + dy } } : drawing));
      return;
    }
    if (!draft && !panRef.current && (tool === "trend" || tool === "horizontal" || (tool === "cursor" && toolVariant === "普通光标"))) snap(screen);
    else if (!draft && !panRef.current) setSnapTarget(null);
    if (panRef.current) {
      const candle = (g?.plotW || 1) / Math.max(1, viewEnd - viewStart);
      const shift = Math.round((panRef.current.x - screen.x) / candle);
      const delta = shift - panRef.current.sent;
      if (delta) { onPan(delta); panRef.current.sent = shift; }
      return;
    }
    if (draft) {
      let endpoint = tool === "trend" || tool === "horizontal" ? snap(screen) : screen;
      if (tool === "horizontal") endpoint = { x: endpoint.x, y: toScreen(draft.start).y };
      if (tool === "trend" && snapTarget === null) {
        const start = toScreen(draft.start); const dx = endpoint.x - start.x; const dy = endpoint.y - start.y;
        const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
        if (Math.abs(Math.atan2(dy, dx) - angle) < .09) { const length = Math.hypot(dx, dy); endpoint = { x: start.x + Math.cos(angle) * length, y: start.y + Math.sin(angle) * length }; setSnapTarget(-1); }
      }
      setDraft({ ...draft, end: toData(endpoint) });
    }
  };

  const pointerUp = () => {
    if (!draft) return;
    if (draft.type === "note") return;
    const a = toScreen(draft.start); const b = toScreen(draft.end);
    if (Math.hypot(b.x - a.x, b.y - a.y) > 5) setDrawings((current) => [...current, draft]);
    setDraft(null);
    setSnapTarget(null);
  };

  return (
    <canvas
      ref={canvasRef}
      className={`price-canvas ${tool === "cursor" && toolVariant === "普通光标" ? "normal-pointer" : ""}`}
      onPointerDown={pointerDown}
      onPointerMove={pointerMove}
      onPointerUp={() => { dragRef.current = null; panRef.current = null; pointerUp(); }}
      onPointerLeave={() => { setCrosshair(null); onCrosshair(null); dragRef.current = null; panRef.current = null; pointerUp(); }}
      aria-label="日K线图"
    />
  );
}
