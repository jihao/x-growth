export type Bar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
};

export type StockItem = { ts_code: string; name: string };

export type DailyResponse = { ts_code: string; bars: Bar[] };
