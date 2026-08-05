import { useParams } from "react-router-dom";

export function StockPage() {
  const { code } = useParams();
  return (
    <section className="module-page" aria-label="个股分析">
      <div className="module-hero">
        <div>
          <span>STOCK ANALYSIS</span>
          <h1>个股分析</h1>
          <p>代码：{code ?? "—"}</p>
        </div>
      </div>
    </section>
  );
}
