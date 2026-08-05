import { apiGet } from "./client";

export function fetchRegime(date: string) {
  return apiGet<Record<string, unknown>>(
    `/api/v1/market/regime?date=${encodeURIComponent(date)}`,
  );
}

export function fetchConcentration(start?: string, end?: string) {
  const q = new URLSearchParams();
  if (start) q.set("start", start);
  if (end) q.set("end", end);
  const qs = q.toString();
  return apiGet<Record<string, unknown>[]>(
    `/api/v1/market/concentration${qs ? `?${qs}` : ""}`,
  );
}
