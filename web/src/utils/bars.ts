import type { Bar } from "../types/market";

export type Period = "日K" | "周K" | "月K";

function parseDate(date: string): Date {
  return new Date(`${date}T00:00:00`);
}

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function aggregateBars(bars: Bar[], period: Period): Bar[] {
  if (period === "日K") return bars;
  const groups = new Map<string, Bar[]>();
  bars.forEach((bar) => {
    const date = parseDate(bar.date);
    let key: string;
    if (period === "月K") {
      key = `${date.getFullYear()}-${date.getMonth()}`;
    } else {
      const monday = new Date(date);
      const day = monday.getDay() || 7;
      monday.setDate(monday.getDate() - day + 1);
      key = formatDate(monday);
    }
    const group = groups.get(key) || [];
    group.push(bar);
    groups.set(key, group);
  });
  return Array.from(groups.values()).map((group) => ({
    date: group[group.length - 1].date,
    open: group[0].open,
    high: Math.max(...group.map((b) => b.high)),
    low: Math.min(...group.map((b) => b.low)),
    close: group[group.length - 1].close,
    volume: group.reduce((sum, b) => sum + b.volume, 0),
    amount: group.reduce((sum, b) => sum + (b.amount || 0), 0),
  }));
}

export function ma(values: number[], period: number): (number | null)[] {
  return values.map((_, index) => {
    if (index < period - 1) return null;
    let sum = 0;
    for (let i = index - period + 1; i <= index; i++) sum += values[i];
    return sum / period;
  });
}

export function ema(values: number[], period: number): number[] {
  const alpha = 2 / (period + 1);
  const output: number[] = [];
  values.forEach((value, index) => {
    output[index] =
      index === 0 ? value : value * alpha + output[index - 1] * (1 - alpha);
  });
  return output;
}
