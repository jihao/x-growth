# Web 前端（原型基座）设计

日期：2026-08-05  
状态：已设计（待实现）  
范围：新建独立 `web/`（Vite + React）与 `api/`（FastAPI）；以 `docs/kline-prototype` 为 UI/图表交互参考；算法仍在 `quant/`；Streamlit 迁移期并行保留

## 背景

现有量化系统以 Streamlit + Plotly（`app/main.py`）为界面，能力已覆盖个股分析、收藏、资金集中度、选股榜、跟踪复盘与策略回测。另有一份 React + Canvas 原型（`docs/kline-prototype`，本地约 `http://localhost:3000/`）展示了更接近交易终端的 K 线交互与整套壳层（首页对话、个股、组合、策略、市场）。

Streamlit 难以 1:1 还原原型的 Canvas 画线、滚轮缩放与布局密度。需要新建独立 Web 前端，以原型为视觉与交互基座，后端继续用 Python/`quant/` 提供分析能力。

## 目标

1. 新建 `web/`：Vite + React 19 + TypeScript + Tailwind 4 + React Router；移植原型主题与 Canvas K 线，图表细节对照原型。
2. 新建 `api/`：FastAPI 薄封装 `quant/`，对外 JSON；不在 API/前端重写选股、结构、回测等算法。
3. 一期对齐现有 Streamlit 能力并接真数据：个股 K 线链路、结构叠加、单策略回测、收藏、市场 regime、集中度、选股榜、跟踪复盘、首页搜股与可选 LLM 问答。
4. 迁移期 Streamlit 并行保留；功能对齐后可再下线（P5，另开 spec）。
5. `docs/kline-prototype/` 只作参考，不参与生产构建；不引入 vinext / Cloudflare D1 / ChatGPT Sites 鉴权。

## 非目标

- 实时盘中推送 / WebSocket 行情
- 多租户账号与权限体系
- 把 Plotly（`quant/charts/plots.py`）作为 Web 渲染源
- 在 API 内触发全市场选股扫描或集中度缓存重建（仍用现有 CLI）
- 一期交付真「多组合收益曲线 / 因子权重持久化 / 组合绑定策略」（壳可保留，逻辑二期）
- 图表像素级 CI；一期以人工对照原型为主

## 决策摘要

| 项 | 选择 |
|---|---|
| 落地路径 | 原型为 UI 基座 + Python 后端（方案 B） |
| 一期范围 | 整壳 + 尽量对齐 Streamlit 真数据（方案 C） |
| Streamlit | 迁移期并行，完成后下线（方案 A） |
| 技术栈 | Vite React SPA + FastAPI（方案 1） |

## 总体架构

```
浏览器 (web/)                    本机 Python
┌─────────────────────┐         ┌──────────────────────────────┐
│ Vite + React SPA    │  HTTP   │ api/  FastAPI                │
│ · 原型 UI / CSS     │ ──────► │  JSON 适配层（无业务算法）    │
│ · Canvas K 线       │ ◄────── │         │                    │
│ · 路由：个股/组合/  │         │         ▼                    │
│   策略/市场/对话    │         │ quant/  现有分析库（主算法）  │
└─────────────────────┘         │ database/mysql  行情与结果表 │
                                └──────────────────────────────┘
并行保留：app/main.py (Streamlit) 仍直接调 quant/，迁移期不删
```

原则：

- **算法只在 `quant/`**：指标计算库、结构、回测、选股、集中度、跟踪、LLM 解读不搬到前端或 API 重写。
- **`api/` 只做适配**：参数校验、DataFrame→JSON、错误码。
- **`web/` 只做展示与交互**：图表绘制、画线、页面状态；OHLCV 上的常见叠加（MA/EMA/BOLL 等）可前端算以对齐原型交互；结构/选股/回测必须走后端。
- **`docs/kline-prototype/`**：只读参考。

## 目录结构

```
api/
  main.py              # FastAPI 入口、CORS、生命周期
  routes/              # stocks / favorites / market / screening / tracking / ...
  schemas/             # Pydantic 请求/响应
  deps.py              # 共享依赖（鉴权占位可选）
web/
  package.json         # Vite + React 19 + TS + Tailwind 4
  src/
    main.tsx
    App.tsx            # 路由与全局导航（对齐原型 global-nav）
    styles/            # 从原型 globals.css 移植主题变量
    components/charts/ # ChartCanvas、成交量、副图
    pages/             # Home / Stock / Portfolio / Strategy / Market
    api/               # fetch 客户端
    types/
docs/kline-prototype/  # 只读参考，不进生产依赖
app/main.py            # Streamlit，迁移期并行
quant/                 # 算法主库，保持稳定
```

## 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | Vite + React 19 + TypeScript + Tailwind 4 + React Router | 不采用 vinext/Next |
| 图表 | 自研 Canvas（移植原型） | 不用 Plotly / TradingView |
| API | FastAPI + uvicorn | 依赖加入 `requirements.txt`，与现有 `.venv` 共存 |
| 数据 | MySQL via `quant.data.loader` 及既有 store | API 不直写 SQL（除已有 store 模块） |
| 本地开发 | `uvicorn api.main:app` + `web/` 下 `npm run dev` | CORS 放行 Vite 源（如 `localhost:5173`） |

## 页面路由与能力映射

| 路由 | 页面 | 真数据来源 | 一期说明 |
|---|---|---|---|
| `/` | 首页对话 | `list_stocks`；可选 `screening.llm` | 搜股跳转个股；问答可简化 |
| `/stocks/:code` | 个股分析 | 日线、结构、回测、收藏 | Canvas 对照原型；报价条 + 主图/量/副图 + 工具条 + 结构/回测面板 |
| `/portfolios` | 组合 | `favorites.store` | **一期 = 收藏列表**；点开进个股；组合收益/调仓二期 |
| `/strategies` | 策略 | `backtest.strategies` + `engine` + `metrics` | 经典策略回测接真；原型多因子滑条先作 UI，落库/组合绑定二期 |
| `/market` | 市场 | regime、集中度、选股榜、跟踪 | 原型「市场日报」卡片用 regime + concentration 填充 |

导航保留原型四栏：`个股 | 组合 | 策略 | 市场`。Streamlit 的「收藏 / 集中度 / 选股榜 / 跟踪复盘」并入上表，不另开第五顶栏。

### 一期必须真数据

- 个股 K 线链路（含指标切换、缩放平移、画线工具交互）
- 结构叠加、单策略回测
- 收藏、集中度、选股榜、跟踪、市场 regime

### 一期可壳/简化

- 多组合收益曲线、策略因子权重持久化、首页长对话产品化

## API 边界与数据契约

- Base：`http://127.0.0.1:8000/api/v1`
- 日期：对外 `YYYY-MM-DD`，进入 `quant` 前转 `YYYYMMDD`
- 股票代码：统一 `ts_code`（如 `600519.SH`）
- 错误：`{ "detail": "..." }`；空列表用 `200 + []`；股票不存在用 `404`
- CORS：开发环境放行 Vite 源

### 一期端点

| 方法 | 路径 | 调用 | 说明 |
|---|---|---|---|
| GET | `/stocks` | `loader.list_stocks` | 股票列表 |
| GET | `/stocks/{ts_code}/daily` | `loader.load_daily` | query: `start,end`；`bars: [{date,open,high,low,close,volume,amount}]` |
| GET | `/stocks/{ts_code}/structure` | `quant.structure.*` | 趋势线 / 浪型 / 背离几何 JSON |
| POST | `/stocks/{ts_code}/backtest` | strategies + engine + metrics | body: `strategy,start,end` |
| GET/POST/DELETE | `/favorites` | `favorites.store` | 列表 / 添加 / 删除 |
| GET | `/market/regime` | `market.regime` | query: `date` |
| GET | `/market/concentration` | `concentration.cache` | 序列 + 可选截面 |
| GET | `/screening/dates` | `screening.store.list_dates` | |
| GET | `/screening/results` | `load_results` | query: `date` |
| GET | `/screening/explain` | `explain` / 可选 `llm` | query: `date,ts_code`；`deep=1` 走 LLM |
| GET | `/tracking/review` | `tracking.review_date` | |
| GET | `/tracking/stock` | `tracking.track_pick` | |

### 图表数据分工

- **OHLCV**：仅 `/daily`；前端做日/周/月聚合与常见叠加，对齐原型交互。
- **结构**：`/structure` 返回点/线，Canvas 绘制。
- **回测**：`/backtest` 返回序列，个股页内轻量展示（不必 Plotly）。

### 不进 API

- 全市场选股跑批（`python -m quant.screening.cli`）
- 集中度缓存重建（`python -m quant.concentration.build_cache`）

## 迁移分期

| 期 | 交付 | 验收 |
|---|---|---|
| P0 | `api/` 脚手架 + `/stocks`、`/daily`；`web/` 壳 + 导航 + 主题 CSS | 能列股票并拉真日线 JSON |
| P1 | 个股 Canvas（主图/量/副图、缩放平移、指标、画线） | 对照原型视觉/交互；数据为真行情 |
| P2 | `/structure` + `/backtest` 接入个股页 | 结构可叠加；回测可出结果 |
| P3 | 市场页：regime、集中度、选股榜、跟踪 | 与 Streamlit 同源可读；解读/可选 LLM |
| P4 | 组合=收藏；策略页经典回测；首页搜股+简易问答 | 一期「必须真数据」齐；Streamlit 可标次入口 |
| P5（二期） | 真组合收益、因子权重落库、Streamlit 下线 | 另开 spec |

## 错误与空态

- DB/查询失败 → API `5xx` + `detail`；前端横幅/toast，不白屏
- 无日线 / 无选股结果 / 无集中度缓存 → 空态 + 提示对应 CLI（与 Streamlit 文案对齐）
- LLM 未配置 → 深度解读禁用或明确「未配置」

## 测试

- 现有 `pytest`（`quant/`）不变
- API：薄层契约测试（mock loader 或 fixture）
- `web/`：周期聚合、MA 等纯函数用 Vitest；图表回归一期人工对照原型
- README 写明双进程启动步骤

## 成功标准

1. 本地可同时启动 API + Web，浏览器完成「搜股 → 个股 K 线 → 结构/回测 → 市场选股/跟踪」主路径。
2. 个股图表交互与视觉以原型为对照基准（非 Plotly 观感）。
3. 上述路径数据与 Streamlit 同源（同一 `quant/` / MySQL）。
4. Streamlit 在 P0–P4 期间仍可独立运行。
