import { apiGet } from "./client";
import type { DailyResponse, StockItem } from "../types/market";

export type StructureTrendline = {
  side: string;
  score: number;
  touch_count: number;
  start_date: string;
  end_date: string;
  start_price: number | null;
  end_price: number | null;
  status: string | null;
  touch_dates: string[];
};

export type StructureResponse = {
  ts_code: string;
  trendlines: {
    up: StructureTrendline[];
    down: StructureTrendline[];
  };
  wave: {
    direction: string;
    verdict: string;
    ratio: number;
    pivots: { date: string; price: number; kind: string }[];
  } | null;
  divergences: {
    side: string;
    status: string;
    level: string;
    preferred: boolean;
    p1_date: string;
    p1_price: number;
    p2_date: string;
    p2_price: number;
  }[];
};

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

export function fetchStructure(tsCode: string, start?: string, end?: string) {
  const q = new URLSearchParams();
  if (start) q.set("start", start);
  if (end) q.set("end", end);
  const qs = q.toString();
  return apiGet<StructureResponse>(
    `/api/v1/stocks/${encodeURIComponent(tsCode)}/structure${qs ? `?${qs}` : ""}`,
  );
}
