import { apiGet } from "./client";

export function fetchTrackingReview(date: string) {
  return apiGet<{ date: string; rows: Record<string, unknown>[]; stats: Record<string, unknown> }>(
    `/api/v1/tracking/review?date=${encodeURIComponent(date)}`,
  );
}

export function fetchTrackingStock(date: string, tsCode: string) {
  return apiGet<Record<string, unknown>>(
    `/api/v1/tracking/stock?date=${encodeURIComponent(date)}&ts_code=${encodeURIComponent(tsCode)}`,
  );
}
