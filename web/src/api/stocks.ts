import { apiGet } from "./client";
import type { DailyResponse, StockItem } from "../types/market";

export function fetchStocks() {
  return apiGet<StockItem[]>("/api/v1/stocks");
}

export function fetchDaily(tsCode: string, start?: string, end?: string) {
  const q = new URLSearchParams();
  if (start) q.set("start", start);
  if (end) q.set("end", end);
  const qs = q.toString();
  return apiGet<DailyResponse>(
    `/api/v1/stocks/${encodeURIComponent(tsCode)}/daily${qs ? `?${qs}` : ""}`,
  );
}
