"use client";
import { useEffect, useRef, useState } from "react";

function oscillatorValue(type: string, line: number, index: number, height: number) {
  return height / 2 + Math.sin(index / (11 + line * 2) + line * 1.5) * (16 + line * 2) + Math.sin(index / 4.3) * 4 + (type === "DMI" ? line * 4 - 7 : 0);
}

export function OscillatorCanvas({ type, theme, crosshairRatio, onCrosshair, selectable, viewStart, viewEnd }: { type: string; theme: "light" | "dark"; crosshairRatio: number | null; onCrosshair: (ratio: number | null) => void; selectable: boolean; viewStart: number; viewEnd: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const pixelWidth = Math.round(rect.width * dpr);
      const pixelHeight = Math.round(rect.height * dpr);
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = theme === "dark" ? "#111820" : "#fff";
      ctx.fillRect(0, 0, rect.width, rect.height);
      ctx.strokeStyle = theme === "dark" ? "#29323c" : "#e8edf2";
      [24, rect.height / 2, rect.height - 20].forEach((y) => { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(rect.width, y); ctx.stroke(); });
      const colors = type === "DMI" ? ["#d92d20", "#15905f", "#e78419", "#2e74c9"] : type === "KDJ" ? ["#d92d20", "#2e74c9", "#c762b4"] : type === "MACD" ? ["#196f9a", "#e39a21"] : ["#196f9a"];
      colors.forEach((color, line) => {
        ctx.beginPath();
        ctx.strokeStyle = selectedLine === line ? "#1c63d5" : color;
        ctx.lineWidth = selectedLine === line ? 3 : 1.5;
        for (let i = 0; i < 160; i++) {
          const x = (i / 159) * rect.width;
          const dataIndex = viewStart + (i / 159) * Math.max(1, viewEnd - viewStart - 1);
          const y = oscillatorValue(type, line, dataIndex, rect.height);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      });
      if (type === "DMI") {
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.font = "10px Arial";
        [{ y: rect.height - 42, label: "20" }, { y: rect.height - 54, label: "25" }].forEach((ref, i) => {
          ctx.strokeStyle = i ? "#a9b3bd" : "#c6ced6";
          ctx.beginPath(); ctx.moveTo(0, ref.y); ctx.lineTo(rect.width, ref.y); ctx.stroke();
          ctx.fillStyle = "#7f8a96"; ctx.fillText(ref.label, rect.width - 26, ref.y - 3);
        });
        ctx.restore();
      }
      if (crosshairRatio !== null) {
        ctx.save(); ctx.strokeStyle = "#7b8794"; ctx.setLineDash([4, 3]);
        const px = Math.max(0, Math.min(rect.width, crosshairRatio * rect.width));
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, rect.height); ctx.stroke(); ctx.restore();
      }
      if (selectedLine !== null) {
        const names = type === "DMI" ? ["PDI", "MDI", "ADX", "ADXR"] : type === "KDJ" ? ["K", "D", "J"] : type === "MACD" ? ["DIF", "DEA"] : [type];
        const ratio = crosshairRatio ?? .82;
        const index = viewStart + ratio * Math.max(1, viewEnd - viewStart - 1);
        const plottedY = oscillatorValue(type, selectedLine, index, rect.height);
        const displayValue = (100 - (plottedY / rect.height) * 100).toFixed(2);
        const label = `${names[selectedLine] || type} ${displayValue}`;
        ctx.save(); ctx.font = "12px Arial"; const boxW = ctx.measureText(label).width + 18; const px = Math.min(rect.width - boxW - 8, ratio * rect.width + 8);
        ctx.fillStyle = "#1c63d5"; ctx.fillRect(Math.max(4, px), Math.max(5, plottedY - 27), boxW, 22); ctx.fillStyle = "white"; ctx.fillText(label, Math.max(13, px + 9), Math.max(20, plottedY - 12)); ctx.restore();
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    if (canvas.parentElement) observer.observe(canvas.parentElement);
    return () => observer.disconnect();
  }, [crosshairRatio, selectedLine, theme, type, viewEnd, viewStart]);
  return <canvas ref={canvasRef} className="oscillator-canvas" aria-label={`${type}指标图`}
    onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onCrosshair(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))); }}
    onPointerLeave={() => onCrosshair(null)}
    onPointerDown={(event) => {
      if (!selectable) return;
      const rect = event.currentTarget.getBoundingClientRect(); const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)); const index = viewStart + ratio * Math.max(1, viewEnd - viewStart - 1); const y = event.clientY - rect.top;
      const lineCount = type === "DMI" ? 4 : type === "KDJ" ? 3 : type === "MACD" ? 2 : 1;
      let nearest: number | null = null; let distance = 11;
      for (let line = 0; line < lineCount; line++) { const d = Math.abs(y - oscillatorValue(type, line, index, rect.height)); if (d < distance) { distance = d; nearest = line; } }
      setSelectedLine(nearest); onCrosshair(ratio);
    }} />;
}

