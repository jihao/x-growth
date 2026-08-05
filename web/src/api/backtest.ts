import { apiGet, apiSend } from "./client";

export type StrategyInfo = {
  name: string;
  label: string;
  default_params: Record<string, number>;
};

export type BacktestResponse = {
  ts_code: string;
  strategy: string;
  metrics: Record<string, number | null>;
  equity: { date: string; value: number }[];
  benchmark: { date: string; value: number }[];
  trades: {
    entry: string;
    exit: string;
    entry_px: number;
    exit_px: number;
    ret: number;
  }[];
};

export function fetchStrategies() {
  return apiGet<StrategyInfo[]>("/api/v1/strategies");
}

export function runBacktest(
  tsCode: string,
  strategy: string,
  start?: string,
  end?: string,
) {
  return apiSend<BacktestResponse>(
    `/api/v1/stocks/${encodeURIComponent(tsCode)}/backtest`,
    "POST",
    { strategy, start, end },
  );
}
