import { apiGet } from "./client";

export function fetchScreeningDates() {
  return apiGet<string[]>("/api/v1/screening/dates");
}

export function fetchScreeningResults(date: string) {
  return apiGet<Record<string, unknown>[]>(
    `/api/v1/screening/results?date=${encodeURIComponent(date)}`,
  );
}

export function fetchScreeningExplain(date: string, tsCode: string, deep = 0) {
  return apiGet<Record<string, unknown>>(
    `/api/v1/screening/explain?date=${encodeURIComponent(date)}&ts_code=${encodeURIComponent(tsCode)}&deep=${deep}`,
  );
}
