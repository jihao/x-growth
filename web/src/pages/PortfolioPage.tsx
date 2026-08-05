import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { addFavorite, fetchFavorites, removeFavorite, type FavoriteItem } from "../api/favorites";

export function PortfolioPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [codeInput, setCodeInput] = useState("");

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await fetchFavorites());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const onAdd = async () => {
    const code = codeInput.trim();
    if (!code) return;
    try {
      await addFavorite(code.includes(".") ? code : code.startsWith("6") ? `${code}.SH` : `${code}.SZ`);
      setCodeInput("");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  return (
    <section className="module-page portfolio-page" aria-label="组合">
      <div className="module-hero">
        <div>
          <span>PORTFOLIO LAB</span>
          <h1>我的选股组合</h1>
          <p>一期映射收藏列表，点开即可进入个股分析。</p>
        </div>
      </div>
      {error && <div className="api-banner" role="alert">{error}</div>}
      <div className="fav-add-row">
        <input
          value={codeInput}
          onChange={(e) => setCodeInput(e.target.value)}
          placeholder="输入 ts_code，如 600519.SH"
        />
        <button type="button" onClick={() => void onAdd()}>
          添加收藏
        </button>
      </div>
      {loading ? (
        <p>加载中…</p>
      ) : items.length === 0 ? (
        <p>暂无收藏。可在个股页点 ★，或在上方添加。</p>
      ) : (
        <ul className="fav-list">
          {items.map((item) => (
            <li key={item.ts_code}>
              <button type="button" onClick={() => navigate(`/stocks/${item.ts_code}`)}>
                <b>{item.name || item.ts_code}</b>
                <small>{item.ts_code}</small>
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => void removeFavorite(item.ts_code).then(reload)}
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link to="/">返回首页搜股</Link>
      </p>
    </section>
  );
}
