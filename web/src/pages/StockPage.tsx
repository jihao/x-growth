import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { fetchDaily, fetchStocks } from "../api/stocks";
import type { Bar } from "../types/market";

function normalizeTsCode(code: string): string {
  if (code.includes(".")) return code;
  if (code.startsWith("6") || code.startsWith("9")) return `${code}.SH`;
  return `${code}.SZ`;
}

export function StockPage() {
  const { code: rawCode } = useParams();
  const tsCode = rawCode ? normalizeTsCode(rawCode) : "";
  const [name, setName] = useState("");
  const [bars, setBars] = useState<Bar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tsCode) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [daily, stocks] = await Promise.all([
          fetchDaily(tsCode),
          fetchStocks().catch(() => [] as { ts_code: string; name: string }[]),
        ]);
        if (cancelled) return;
        setBars(daily.bars);
        const hit = stocks.find((s) => s.ts_code === tsCode);
        setName(hit?.name ?? "");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : String(err));
        setBars([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tsCode]);

  const last = bars[bars.length - 1];

  return (
    <section className="module-page" aria-label="个股分析">
      <div className="module-hero">
        <div>
          <span>STOCK ANALYSIS</span>
          <h1>
            {name || "个股分析"}{" "}
            <small>{tsCode}</small>
          </h1>
          <p>
            {loading && "加载中…"}
            {!loading && !error && `共 ${bars.length} 根日线`}
            {!loading && !error && last && ` · 最新收盘 ${last.close}`}
          </p>
        </div>
      </div>
      {error && (
        <div className="api-banner" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
