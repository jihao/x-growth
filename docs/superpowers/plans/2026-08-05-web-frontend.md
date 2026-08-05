# Web 前端（Vite + FastAPI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 `docs/kline-prototype` 为 UI/图表基座，新建 `web/`（Vite + React）与 `api/`（FastAPI），接上现有 `quant/` 真数据，一期对齐 Streamlit 能力；Streamlit 并行保留。

**Architecture:** FastAPI 薄封装 `quant/` 输出 JSON；React SPA 移植原型 Canvas 与导航壳；OHLCV 叠加指标可前端算，结构/回测/选股/集中度/跟踪必须走后端。

**Tech Stack:** Python 3.13、FastAPI、uvicorn、现有 `.venv` + `quant/`；Node.js 20+、Vite、React 19、TypeScript、Tailwind 4、React Router、Vitest。

## Global Constraints

- Spec：`docs/superpowers/specs/2026-08-05-web-frontend-design.md`（全文约束均适用）。
- 算法只在 `quant/`；`api/` 不做业务重写；不把 Plotly 当 Web 渲染源。
- API base：`/api/v1`；日期对外 `YYYY-MM-DD`，进 `quant` 前转 `YYYYMMDD`；股票统一 `ts_code`。
- 不引入 vinext / Cloudflare D1 / ChatGPT Sites；`docs/kline-prototype/` 只读参考。
- Streamlit（`app/main.py`）P0–P4 期间不删、不改为主入口。
- 单测：API 用 pytest + mock，不强制连 MySQL；`web/` 纯函数用 Vitest。
- `.venv/bin/python -m pytest`；每 Task 结束提交一次。
- 一期组合页 = 收藏；多因子权重落库 / 真组合收益 / Streamlit 下线属 P5，不在本 plan。

## File Structure

| 文件 | 职责 |
|---|---|
| `api/__init__.py` | 包标记 |
| `api/main.py` | FastAPI app、CORS、挂载 router |
| `api/deps.py` | 可选共享依赖 |
| `api/schemas/common.py` | 日期/股票通用 schema |
| `api/schemas/stocks.py` | Stock / Bar / DailyResponse |
| `api/routes/stocks.py` | `/stocks`、`/stocks/{ts_code}/daily` |
| `api/routes/structure.py` | `/stocks/{ts_code}/structure` |
| `api/routes/backtest.py` | `POST /stocks/{ts_code}/backtest` |
| `api/routes/favorites.py` | favorites CRUD |
| `api/routes/market.py` | regime、concentration |
| `api/routes/screening.py` | dates、results、explain |
| `api/routes/tracking.py` | review、stock |
| `api/serializers.py` | DataFrame/dataclass → JSON 辅助 |
| `tests/test_api_stocks.py` | stocks 路由契约（TestClient + mock） |
| `tests/test_api_structure.py` | structure 序列化 |
| `tests/test_api_backtest.py` | backtest 契约 |
| `tests/test_api_favorites.py` | favorites 契约 |
| `tests/test_api_market.py` | market 契约 |
| `tests/test_api_screening.py` | screening 契约 |
| `tests/test_api_tracking.py` | tracking 契约 |
| `requirements.txt` | 追加 fastapi、uvicorn |
| `web/package.json` | Vite React 工程 |
| `web/vite.config.ts` | Vite + 代理 `/api` → `:8000` |
| `web/src/main.tsx` | 入口 |
| `web/src/App.tsx` | 路由 + global-nav |
| `web/src/styles/globals.css` | 从原型移植主题 |
| `web/src/types/market.ts` | Bar、StockMeta 等 |
| `web/src/api/client.ts` | fetch 封装 |
| `web/src/api/stocks.ts` | stocks / daily / structure / backtest |
| `web/src/api/favorites.ts` | favorites |
| `web/src/api/market.ts` | regime / concentration |
| `web/src/api/screening.ts` | screening / explain |
| `web/src/api/tracking.ts` | tracking |
| `web/src/lib/bars.ts` | aggregateBars、adjust 占位、ma/ema |
| `web/src/lib/bars.test.ts` | Vitest |
| `web/src/components/charts/ChartCanvas.tsx` | 主图 Canvas（移植原型） |
| `web/src/components/charts/VolumePanel.tsx` | 成交量 |
| `web/src/components/charts/OscillatorCanvas.tsx` | 副图 |
| `web/src/components/layout/GlobalNav.tsx` | 顶栏导航 |
| `web/src/pages/HomePage.tsx` | 首页搜股/问答 |
| `web/src/pages/StockPage.tsx` | 个股分析 |
| `web/src/pages/PortfolioPage.tsx` | 组合=收藏 |
| `web/src/pages/StrategyPage.tsx` | 策略回测 |
| `web/src/pages/MarketPage.tsx` | 市场（regime/集中度/选股/跟踪） |
| `README.md` | 追加双进程启动说明 |

---

### Task 1: FastAPI 脚手架 + `/stocks` + `/daily`

**Files:**
- Modify: `requirements.txt`
- Create: `api/__init__.py`, `api/main.py`, `api/deps.py`
- Create: `api/serializers.py`
- Create: `api/schemas/common.py`, `api/schemas/stocks.py`
- Create: `api/routes/__init__.py`, `api/routes/stocks.py`
- Create: `tests/test_api_stocks.py`

**Interfaces:**
- Consumes: `quant.data.loader.list_stocks`, `quant.data.loader.load_daily`, `quant.config.fmt_date`
- Produces:
  - `GET /api/v1/stocks` → `list[{ts_code: str, name: str}]`
  - `GET /api/v1/stocks/{ts_code}/daily?start=&end=` → `{ts_code, bars: [{date, open, high, low, close, volume, amount}]}`
  - `api.serializers.bars_from_daily(df) -> list[dict]`
  - `api.serializers.parse_date_param(s: str | None) -> str | None`

- [ ] **Step 1: 追加依赖**

在 `requirements.txt` 末尾追加：

```
fastapi==0.128.0
uvicorn==0.40.0
httpx==0.28.1
```

（`httpx` 供 TestClient；版本若解析冲突可放宽下界，以 `.venv/bin/pip install` 能装为准。）

- [ ] **Step 2: 安装依赖**

Run: `.venv/bin/pip install fastapi uvicorn httpx`
Expected: 安装成功。

- [ ] **Step 3: 写失败测试**

创建 `tests/test_api_stocks.py`：

```python
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_list_stocks_ok():
    df = pd.DataFrame([{"ts_code": "600519.SH", "name": "贵州茅台"}])
    with patch("api.routes.stocks.loader.list_stocks", return_value=df):
        r = client.get("/api/v1/stocks")
    assert r.status_code == 200
    assert r.json() == [{"ts_code": "600519.SH", "name": "贵州茅台"}]


def test_daily_bars_ok():
    idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1100],
            "amount": [1e8, 1.1e8],
        },
        index=idx,
    )
    df.index.name = "trade_date"
    with patch("api.routes.stocks.loader.load_daily", return_value=df) as m:
        r = client.get(
            "/api/v1/stocks/600519.SH/daily",
            params={"start": "2026-01-01", "end": "2026-01-31"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ts_code"] == "600519.SH"
    assert len(body["bars"]) == 2
    assert body["bars"][0]["date"] == "2026-01-02"
    assert body["bars"][0]["close"] == 101.0
    m.assert_called_once()
    args = m.call_args[0]
    assert args[0] == "600519.SH"
    assert args[1] == "20260101"
    assert args[2] == "20260131"


def test_daily_empty():
    empty = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "amount"]
    )
    empty.index = pd.DatetimeIndex([], name="trade_date")
    with patch("api.routes.stocks.loader.load_daily", return_value=empty):
        r = client.get("/api/v1/stocks/600519.SH/daily")
    assert r.status_code == 200
    assert r.json()["bars"] == []
```

- [ ] **Step 4: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_api_stocks.py -v`
Expected: FAIL（`api.main` 或模块不存在）。

- [ ] **Step 5: 实现序列化与路由**

Create `api/__init__.py`（空）。

Create `api/serializers.py`：

```python
"""DataFrame / 日期 → API JSON。"""
from __future__ import annotations

from typing import Any

import pandas as pd

from quant import config


def parse_date_param(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return config.fmt_date(value)


def bars_from_daily(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append(
            {
                "date": date,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "amount": float(row["amount"]),
            }
        )
    return out
```

Create `api/schemas/common.py`：

```python
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    detail: str
```

Create `api/schemas/stocks.py`：

```python
from pydantic import BaseModel, Field


class StockItem(BaseModel):
    ts_code: str
    name: str


class Bar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


class DailyResponse(BaseModel):
    ts_code: str
    bars: list[Bar] = Field(default_factory=list)
```

Create `api/routes/__init__.py`（空）。

Create `api/routes/stocks.py`：

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from quant.data import loader

from api.schemas.stocks import DailyResponse, StockItem
from api.serializers import bars_from_daily, parse_date_param

router = APIRouter(tags=["stocks"])


@router.get("/stocks", response_model=list[StockItem])
def list_stocks():
    try:
        df = loader.list_stocks()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取股票列表失败：{exc}") from exc
    if df is None or df.empty:
        return []
    return [
        StockItem(ts_code=str(r.ts_code), name=str(r.name))
        for r in df.itertuples(index=False)
    ]


@router.get("/stocks/{ts_code}/daily", response_model=DailyResponse)
def get_daily(
    ts_code: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    try:
        s = parse_date_param(start)
        e = parse_date_param(end)
        df = loader.load_daily(ts_code, s, e)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取日线失败：{exc}") from exc
    return DailyResponse(ts_code=ts_code, bars=bars_from_daily(df))
```

Create `api/deps.py`：

```python
"""共享依赖占位（一期无鉴权）。"""
```

Create `api/main.py`：

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import stocks

app = FastAPI(title="x-growth API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(stocks.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"ok": True}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_api_stocks.py -v`
Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add requirements.txt api tests/test_api_stocks.py
git commit -m "feat(api): add FastAPI scaffold with stocks and daily endpoints"
```

---

### Task 2: `web/` Vite 脚手架 + 导航壳 + 主题

**Files:**
- Create: `web/` 全套 Vite React TS 工程（见步骤）
- Create: `web/src/styles/globals.css`（从原型复制并收敛）
- Create: `web/src/components/layout/GlobalNav.tsx`
- Create: `web/src/pages/*.tsx` 占位页
- Create: `web/src/App.tsx`, `web/src/main.tsx`
- Modify: `README.md`（追加启动说明草稿，Task 16 再补全也可在此写最小版）

**Interfaces:**
- Consumes: 无后端依赖（本 Task 可 mock 静态）
- Produces: 可 `npm run dev` 打开；路由 `/` `/stocks/:code` `/portfolios` `/strategies` `/market`；顶栏四栏对齐原型

- [ ] **Step 1: 脚手架**

在仓库根目录执行：

```bash
npm create vite@latest web -- --template react-ts
cd web && npm install && npm install react-router-dom && npm install -D tailwindcss @tailwindcss/vite
```

`web/vite.config.ts` 改为（示意，保留既有 react 插件并加 tailwind + proxy）：

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

- [ ] **Step 2: 移植 CSS**

将 `docs/kline-prototype/app/globals.css` 复制为 `web/src/styles/globals.css`，文件头保留 `@import "tailwindcss";`。删除仅 vinext/ChatGPT 相关无用规则（若有）；保留 `.app-shell`、`.global-nav`、`.quote-header`、`.chart-card`、`.theme-dark` 等。

- [ ] **Step 3: 导航与路由**

Create `web/src/components/layout/GlobalNav.tsx`：

```tsx
import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/", label: "个股", end: true },
  { to: "/portfolios", label: "组合" },
  { to: "/strategies", label: "策略" },
  { to: "/market", label: "市场" },
] as const;

export function GlobalNav() {
  return (
    <header className="global-nav">
      <div className="home-brand">
        <span>知</span>
        <b>知研</b>
        <em>QUANT</em>
      </div>
      <nav aria-label="主菜单">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "active" : undefined)}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
```

Create 占位页 `HomePage.tsx` / `StockPage.tsx` / `PortfolioPage.tsx` / `StrategyPage.tsx` / `MarketPage.tsx`，各返回带 `module-page` 或 `home-page` class 的简单标题（文案对齐原型模块名）。

`App.tsx`：

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GlobalNav } from "./components/layout/GlobalNav";
import { HomePage } from "./pages/HomePage";
import { StockPage } from "./pages/StockPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { StrategyPage } from "./pages/StrategyPage";
import { MarketPage } from "./pages/MarketPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <GlobalNav />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/stocks/:code" element={<StockPage />} />
          <Route path="/portfolios" element={<PortfolioPage />} />
          <Route path="/strategies" element={<StrategyPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
```

`main.tsx` 引入 `./styles/globals.css`。

- [ ] **Step 4: 验证构建**

Run: `cd web && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): scaffold Vite React app with nav shell and theme"
```

---

### Task 3: 前端 API client + 个股页拉真日线

**Files:**
- Create: `web/src/types/market.ts`
- Create: `web/src/api/client.ts`, `web/src/api/stocks.ts`
- Modify: `web/src/pages/StockPage.tsx`, `web/src/pages/HomePage.tsx`（搜股跳转可先简）

**Interfaces:**
- Consumes: `GET /api/v1/stocks`, `GET /api/v1/stocks/{ts_code}/daily`
- Produces: `fetchStocks()`, `fetchDaily(tsCode, start?, end?)`；StockPage 展示 bars 条数与最新收盘（图表下 Task）

- [ ] **Step 1: types + client**

```ts
// web/src/types/market.ts
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
```

```ts
// web/src/api/client.ts
export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

export async function apiSend<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<T> {
  return apiGet<T>(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}
```

```ts
// web/src/api/stocks.ts
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
```

- [ ] **Step 2: StockPage 拉数**

`StockPage` 从 `useParams().code` 取代码（支持 `600519` 或 `600519.SH`；若无后缀，按沪深规则补：`6/9`→`.SH`，其余→`.SZ`，或要求完整 `ts_code`——**固定：路由使用完整 `ts_code`，Home 跳转时带后缀**）。

页面状态：`loading` / `error` / `bars`；错误横幅显示 `ApiError.message`；成功时显示名称（可先只显示 code）与 `bars.length`、最新 `close`。

- [ ] **Step 3: 手动联调**

终端 1：`.venv/bin/uvicorn api.main:app --reload --port 8000`  
终端 2：`cd web && npm run dev`  
浏览器打开 `/stocks/600519.SH`（需本机 MySQL 有数据）。  
Expected: 看到非空 bars 计数与最新价；断 API 时应有错误横幅。

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): wire stock page to daily API"
```

---

### Task 4: 前端 bars 工具函数 + Vitest

**Files:**
- Create: `web/src/lib/bars.ts`, `web/src/lib/bars.test.ts`
- Modify: `web/package.json`（确保 `vitest` 脚本）

**Interfaces:**
- Produces:
  - `aggregateBars(bars: Bar[], period: "日K" | "周K" | "月K"): Bar[]`
  - `ma(values: number[], period: number): (number | null)[]`
  - `ema(values: number[], period: number): (number | null)[]`

- [ ] **Step 1: 安装 vitest**

```bash
cd web && npm install -D vitest
```

`package.json` scripts 增加：`"test": "vitest run"`。

- [ ] **Step 2: 写失败测试**

逻辑对齐 `docs/kline-prototype/app/page.tsx` 中 `aggregateBars` / `ma`（周 K 用周一为 key；月 K 用年-月；MA 不足 period 返回 `null`）。

```ts
import { describe, expect, it } from "vitest";
import { aggregateBars, ma } from "./bars";
import type { Bar } from "../types/market";

const sample: Bar[] = [
  { date: "2026-01-05", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, amount: 100 },
  { date: "2026-01-06", open: 1.5, high: 2.5, low: 1, close: 2, volume: 20, amount: 200 },
  { date: "2026-01-12", open: 2, high: 3, low: 1.5, close: 2.5, volume: 30, amount: 300 },
];

describe("aggregateBars", () => {
  it("returns daily unchanged", () => {
    expect(aggregateBars(sample, "日K")).toHaveLength(3);
  });
  it("aggregates week", () => {
    const w = aggregateBars(sample, "周K");
    expect(w.length).toBeLessThan(3);
    expect(w[0].volume).toBe(30); // 前两根同周
  });
});

describe("ma", () => {
  it("pads nulls then averages", () => {
    expect(ma([1, 2, 3, 4], 3)).toEqual([null, null, 2, 3]);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd web && npm test`
Expected: FAIL（模块不存在或未实现）。

- [ ] **Step 4: 实现 `bars.ts`**

从原型 `aggregateBars` / `ma` / `ema` 移植（日期用 `Bar.date` 字符串构造 `Date`；注意时区：统一 `T00:00:00` 本地或 UTC，测试与实现保持一致）。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd web && npm test`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add web/src/lib web/package.json web/package-lock.json
git commit -m "feat(web): add bar aggregation and MA helpers with tests"
```

---

### Task 5: 移植 ChartCanvas + 成交量/副图骨架

**Files:**
- Create: `web/src/components/charts/ChartCanvas.tsx`
- Create: `web/src/components/charts/VolumePanel.tsx`
- Create: `web/src/components/charts/OscillatorCanvas.tsx`
- Modify: `web/src/pages/StockPage.tsx`

**Interfaces:**
- Consumes: `Bar[]`、`viewStart`/`viewEnd`、主图指标名、theme
- Produces: 可缩放/平移的主图 + 量能；副图至少支持 MACD 或成交量旁路空态

- [ ] **Step 1: 从原型拆分组件**

参考 `docs/kline-prototype/app/page.tsx`：

- `ChartCanvas`（约含 price canvas 绘制、十字光标、拖拽平移）→ `ChartCanvas.tsx`
- volume panel → `VolumePanel.tsx`
- oscillator → `OscillatorCanvas.tsx`

改造要点：

1. 去掉对页面级 mock `moutaiData` 的依赖，props 只收 `bars: Bar[]`。
2. `Bar.date` 为 `string`，绘制前 `new Date(bar.date)`。
3. 主题用 `theme: "light" | "dark"` prop，class 挂在外层。
4. 导出明确 props 类型（`bars`, `mainIndicators`, `overlays`, `maPeriods`, `viewStart`, `viewEnd`, `onPan`, `onZoom`, `tool`, `locked` 等，与原型一致的可先保留默认）。

- [ ] **Step 2: StockPage 集成**

布局对齐原型个股区：`quote-header` + `chart-commandbar`（日K/周K/月K、缩放）+ `chart-card` 内嵌 ChartCanvas + VolumePanel。

状态：`period`、`visibleCount`、`viewEnd`、`mainIndicators`（默认 `["MA"]`）、`theme`。

用 `aggregateBars` 得到展示序列。

- [ ] **Step 3: 人工对照**

并排打开原型 `localhost:3000` 个股区与 `localhost:5173/stocks/600519.SH`：蜡烛颜色、网格、MA、滚轮缩放、拖拽应对齐观感（允许数据区间不同）。

- [ ] **Step 4: Commit**

```bash
git add web/src/components/charts web/src/pages/StockPage.tsx
git commit -m "feat(web): port canvas kline chart onto stock page"
```

---

### Task 6: 画线工具与指标切换

**Files:**
- Modify: `web/src/components/charts/ChartCanvas.tsx`
- Modify: `web/src/pages/StockPage.tsx`
- Create: `web/src/components/charts/DrawingToolbar.tsx`（若原型内联则拆出）

**Interfaces:**
- Produces: 工具条 cursor/trend/horizontal/shape/note/measure；主图 MA/EMA/BOLL 切换；副图 MACD/KDJ/RSI 至少一个可用

- [ ] **Step 1: 移植 TOOLBAR 与 drawings 状态**

从原型复制 `TOOLBAR`、`Drawing` 类型与绘制逻辑到 ChartCanvas；StockPage 持有 `tool` / `toolVariant` / `locked` / `drawingsVisible`。

- [ ] **Step 2: 主图/副图指标**

主图 tabs：`MA` `EMA` `BOLL`（SAR/MAE 可先灰掉或简单实现）。  
副图：至少 `MACD`（前端用 close 算 DIF/DEA/HIST，公式与 `quant/indicators/ta.py` 一致或注明简化）；KDJ/RSI 可跟进。

- [ ] **Step 3: 对照验收**

画趋势线/水平线可落笔；切换 MA 周期可读出；副图随十字光标联动（若原型有）。

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): add drawing tools and indicator toggles"
```

---

### Task 7: Structure API + 前端叠加

**Files:**
- Create: `api/routes/structure.py`, `api/schemas/structure.py`
- Modify: `api/main.py`（include router）
- Create: `tests/test_api_structure.py`
- Create: `web/src/api/stocks.ts` 增加 `fetchStructure`
- Modify: `ChartCanvas` / `StockPage` 绘制趋势线、浪型、背离

**Interfaces:**
- Consumes: `find_trendlines`, `evaluate_breakout`, `analyze_wave_speed`, `analyze_divergence`
- Produces: `GET /api/v1/stocks/{ts_code}/structure?start=&end=` JSON：

```json
{
  "ts_code": "600519.SH",
  "trendlines": {
    "up": [{"start_date":"…","end_date":"…","start_price":0,"end_price":0,"side":"up","score":0}],
    "down": []
  },
  "wave": {"direction":"up","verdict":"extend","pivots":[{"date":"…","price":0,"kind":"H"}]},
  "divergences": [{"side":"top","status":"confirmed","p1_date":"…","p1_price":0,"p2_date":"…","p2_price":0,"level":"medium"}]
}
```

日期一律 `YYYY-MM-DD`；价格 float。默认参数与 Streamlit 一致（window=5, tol=0.015, top_k=3, min_bars=10 等）。

- [ ] **Step 1: 写失败测试**

`tests/test_api_structure.py`：mock `load_daily` 返回短序列 fixture，patch `find_trendlines` / `analyze_wave_speed` / `analyze_divergence` 返回可控对象，断言 JSON 字段与日期格式。

- [ ] **Step 2: 跑测失败 → 实现路由与序列化 → 跑通**

实现 `serialize_trendline(tl, df)`：用 `tl.start_date`/`end_date` 与 `tl.price_at(index位置)` 或 touch 点生成 `start_price`/`end_price`（与 `plots.overlay_trendlines` 一致的取价方式）。

- [ ] **Step 3: 前端叠加**

StockPage 拉取 structure；ChartCanvas 增加 props `structure`；在主图绘制线段（颜色区分升降）与背离标记。右侧可放简表（可选）。

- [ ] **Step 4: Commit**

```bash
git add api tests/test_api_structure.py web/src
git commit -m "feat: expose structure analysis API and overlay on chart"
```

---

### Task 8: Backtest API + 个股回测面板

**Files:**
- Create: `api/routes/backtest.py`, `api/schemas/backtest.py`
- Create: `tests/test_api_backtest.py`
- Modify: `api/main.py`
- Modify: `web/src/pages/StockPage.tsx`（或侧栏 BacktestPanel）
- Modify: `web/src/api/stocks.ts`

**Interfaces:**
- Consumes: `quant.backtest.strategies.get`, `engine.run`, `metrics.performance`
- Produces: `POST /api/v1/stocks/{ts_code}/backtest`  
  body: `{ "strategy": "ma_cross", "start": "2024-01-01", "end": "2026-08-01" }`  
  response: `{ metrics: {total_return, ann_return, max_drawdown, sharpe, win_rate, ...}, equity: [{date, value}], benchmark: [{date, value}], trades: [...] }`

策略名使用 REGISTRY keys：`ma_cross` / `macd` / `bollinger` / `rsi` / `donchian`。

- [ ] **Step 1: 确认策略名（烟测）**

Run: `.venv/bin/python -c "from quant.backtest.strategies import REGISTRY; print(sorted(REGISTRY))"`  
Expected: `['bollinger', 'donchian', 'ma_cross', 'macd', 'rsi']`。

- [ ] **Step 2: TDD 实现 API**

Mock `load_daily` + 真实 `engine.run` 于小 DataFrame，或全 mock `get`/`run`/`performance`。未知策略 → 400。

- [ ] **Step 3: 前端面板**

策略下拉 + 运行按钮 + 展示 metrics；可选简易权益折线（canvas/svg）。

- [ ] **Step 4: Commit**

```bash
git add api tests/test_api_backtest.py web/src
git commit -m "feat: add backtest API and stock page backtest panel"
```

---

### Task 9: Favorites API + 组合页

**Files:**
- Create: `api/routes/favorites.py`
- Create: `tests/test_api_favorites.py`
- Create: `web/src/api/favorites.ts`
- Modify: `web/src/pages/PortfolioPage.tsx`, `StockPage.tsx`（★ 收藏）
- Modify: `api/main.py`

**Interfaces:**
- `GET /api/v1/favorites` → `[{ts_code, name, created_at}]`
- `POST /api/v1/favorites` body `{ts_code}` → 204/200
- `DELETE /api/v1/favorites/{ts_code}` → 204/200
- 底层：`quant.favorites.store`

- [ ] **Step 1: TDD API（mock store）**

- [ ] **Step 2: PortfolioPage = 收藏列表，点击 `navigate(/stocks/{ts_code})`**

- [ ] **Step 3: StockPage 收藏按钮调用 POST/DELETE**

- [ ] **Step 4: Commit**

```bash
git add api tests/test_api_favorites.py web/src
git commit -m "feat: add favorites API and portfolio page as watchlist"
```

---

### Task 10: Market API（regime + concentration）

**Files:**
- Create: `api/routes/market.py`
- Create: `tests/test_api_market.py`
- Create: `web/src/api/market.ts`
- Modify: `web/src/pages/MarketPage.tsx`（先接这两块 UI）
- Modify: `api/main.py`

**Interfaces:**
- `GET /api/v1/market/regime?date=` → `market_regime()` 原样可 JSON 化的 dict（确保 numpy 类型转 float）
- `GET /api/v1/market/concentration?start=&end=` → 序列表（调用 `concentration.cache.read_series(start, end)`）

- [ ] **Step 1: 确认 `read_series` 返回列**

Run: `.venv/bin/python -c "import inspect; from quant.concentration import cache; print(inspect.getsource(cache.read_series)[:500])"`  
Expected: 可见 `read_series` 读 `market_concentration` 表。

- [ ] **Step 2: TDD + 实现（mock `read_series` / `market_regime`）**

- [ ] **Step 3: MarketPage 展示 regime 摘要 + 集中度表/简图（可用简单 SVG 或表格）**

空缓存时提示：`.venv/bin/python -m quant.concentration.build_cache --rebuild`

- [ ] **Step 4: Commit**

```bash
git add api tests/test_api_market.py web/src
git commit -m "feat: add market regime and concentration API pages"
```

---

### Task 11: Screening + explain API 与市场页榜单

**Files:**
- Create: `api/routes/screening.py`
- Create: `tests/test_api_screening.py`
- Create: `web/src/api/screening.ts`
- Modify: `MarketPage.tsx`
- Modify: `api/main.py`

**Interfaces:**
- `GET /api/v1/screening/dates`
- `GET /api/v1/screening/results?date=`
- `GET /api/v1/screening/explain?date=&ts_code=&deep=0|1`  
  - `deep=0` → `explain.explain_row`  
  - `deep=1` → 若 `llm.is_configured()` 则 `explain_with_llm`，否则 400/`{"detail":"LLM 未配置"}`

空结果提示 CLI：`python -m quant.screening.cli`

- [ ] **Step 1: TDD（mock store/explain/llm）**

- [ ] **Step 2: MarketPage 选日期、表格、解读面板；行点击跳转个股**

- [ ] **Step 3: Commit**

```bash
git add api tests/test_api_screening.py web/src
git commit -m "feat: add screening results and explain endpoints to market page"
```

---

### Task 12: Tracking API 与市场页复盘

**Files:**
- Create: `api/routes/tracking.py`
- Create: `tests/test_api_tracking.py`
- Create: `web/src/api/tracking.ts`
- Modify: `MarketPage.tsx`
- Modify: `api/main.py`

**Interfaces:**
- `GET /api/v1/tracking/review?date=` → `tracking.review_date` 的 DataFrame/dict 序列化
- `GET /api/v1/tracking/stock?date=&ts_code=` → `tracking.track_pick`

注意：`review_date` 可能较慢；一期同步即可，前端 loading 态。

- [ ] **Step 1: TDD mock tracking 函数**

- [ ] **Step 2: UI「整体复盘 / 个股跟踪」两块（对齐 Streamlit tabs）**

- [ ] **Step 3: Commit**

```bash
git add api tests/test_api_tracking.py web/src
git commit -m "feat: add tracking review APIs to market page"
```

---

### Task 13: 策略页接经典回测

**Files:**
- Modify: `web/src/pages/StrategyPage.tsx`
- 复用 Task 8 backtest API；可增加 `GET /api/v1/strategies` 列出 REGISTRY（可选，小改 `api/routes/backtest.py`）

**Interfaces:**
- 策略库 UI：列出 REGISTRY 策略；选择标的 `ts_code` + 区间 → 提交回测 → 展示记录列表（前端 state，一期不落库）
- 原型「多因子滑条」保留为禁用/说明「二期」，避免假装已接真

- [ ] **Step 1: （可选）`GET /api/v1/strategies` → `[{name, ...}]`**

- [ ] **Step 2: StrategyPage 真回测表单 + 历史列表（session 内）**

- [ ] **Step 3: Commit**

```bash
git add api web/src
git commit -m "feat(web): wire strategy page to classic backtest API"
```

---

### Task 14: 首页搜股 + 简易问答

**Files:**
- Modify: `web/src/pages/HomePage.tsx`
- Create: `api/routes/chat.py`（可选）或复用 screening llm

**Interfaces:**
- 输入匹配 `fetchStocks()` 的 code/name → `navigate(/stocks/{ts_code})`
- 「Agent」按钮：若配置 LLM，`POST /api/v1/chat` body `{message}` 调 `screening.llm.chat`；未配置则前端提示

- [ ] **Step 1: 搜股跳转（必须）**

- [ ] **Step 2: 可选 chat 端点 + UI；未配置时明确文案**

- [ ] **Step 3: Commit**

```bash
git add api web/src
git commit -m "feat(web): home search navigates to stocks with optional LLM chat"
```

---

### Task 15: README 双进程说明 + 烟测清单

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 追加章节**

```markdown
## Web UI（开发中）

```bash
# 终端 1 — API
.venv/bin/uvicorn api.main:app --reload --port 8000

# 终端 2 — Web
cd web && npm install && npm run dev
```

打开 http://127.0.0.1:5173/  
Streamlit 仍可用：`.venv/bin/streamlit run app/main.py`
```

- [ ] **Step 2: 手工烟测清单（写入 README 或本 plan 验收）**

1. `/` 搜 `茅台` → 进个股  
2. K 线缩放/画线/MA  
3. 结构叠加有数据  
4. 回测出 metrics  
5. 组合页收藏增删  
6. 市场页集中度/选股/跟踪（有缓存/跑批时）  
7. Streamlit 仍能启动  

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add web+api local development instructions"
```

---

## Spec Coverage（自检）

| Spec 要求 | Task |
|---|---|
| `web/` Vite React + 原型主题/Canvas | 2, 5, 6 |
| `api/` FastAPI 薄封装 | 1, 7–12 |
| 个股真日线 + 图表细节 | 3–6 |
| 结构 / 回测 | 7, 8 |
| 收藏=组合一期 | 9 |
| regime / 集中度 / 选股 / 跟踪 | 10–12 |
| 策略页经典回测 | 13 |
| 首页搜股 + 可选 LLM | 14 |
| Streamlit 并行 | 全局约束 + 15 |
| 不跑 CLI 选股/缓存进 API | 全局 + 10/11 文案 |
| P5 真组合/权重落库/下线 Streamlit | 明确排除 |

## Placeholder / 一致性自检

- 无 TBD；策略 name 固定为 `ma_cross`/`macd`/`bollinger`/`rsi`/`donchian`；集中度用 `cache.read_series`。
- 路由前缀统一 `/api/v1`；前端经 Vite proxy 用相对路径 `/api/...`。
- `ts_code` 全程带后缀；Home/Portfolio 跳转不得丢后缀。
