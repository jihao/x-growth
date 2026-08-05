# x-growth

astock trade strategy analysis

## Streamlit（迁移期并行保留）

```bash
.venv/bin/streamlit run app/main.py
```

## Web UI + API（开发中）

```bash
# 终端 1 — API
.venv/bin/uvicorn api.main:app --reload --port 8000

# 终端 2 — Web
cd web && npm install && npm run dev
```

打开 http://127.0.0.1:5173/

### 手工烟测清单

1. `/` 搜「茅台」→ 进个股
2. K 线缩放 / 画线 / MA·EMA·BOLL
3. 结构叠加摘要有数据
4. 策略页提交经典回测出 metrics
5. 组合页收藏增删；个股页 ★
6. 市场页集中度 / 选股 / 跟踪（有缓存/跑批时）
7. Streamlit 仍能启动

### 测试

```bash
.venv/bin/python -m pytest tests/test_api_*.py -q
cd web && npm test && npm run build
```
