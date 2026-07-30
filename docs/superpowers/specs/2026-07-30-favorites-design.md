# 股票收藏与侧栏导航设计

日期：2026-07-30  
状态：已确认设计；实现计划见 `docs/superpowers/plans/2026-07-30-favorites.md`  
范围：全局 MySQL 收藏表；Streamlit 侧栏「首页 / 收藏」竖向切换；收藏列表可点并留在收藏页看分析

## 背景

量化分析系统（`app/main.py`）目前在侧栏用下拉框选股，主区为「行情分析 / 资金集中度 / 策略回测」。用户希望能收藏常用股票，并通过左侧竖向 tab 在「首页」与「收藏」之间切换；在收藏页可浏览已收藏列表并点击查看分析。

## 目标

1. 支持对当前股票一键收藏 / 取消收藏（★ / ☆）。
2. 侧栏顶部竖向切换「首页」与「收藏」。
3. 收藏页展示已收藏股票列表（可点击）；点击后留在收藏页，主区显示该股分析。
4. 收藏数据持久化到 MySQL，全局单份列表（无用户体系）。

## 非目标

- 多用户 / 登录 / 按账号隔离
- 收藏分组、拖拽排序、备注、导出
- 完整 Streamlit UI 自动化测试
- 重构主区三大 tab 的分析逻辑（仅复用，不拆业务）

## 技术选型

- **存储**：现有 MySQL（`MYSQL_DATABASE`，一般为 `astocks_qfq`）新建 `favorites` 表
- **访问层**：独立模块 `quant/favorites/store.py`，复用 `mysql_config.connect_mysql` / `load_dotenv`，风格对齐 `quant/data/loader.py`
- **UI**：继续单文件 `app/main.py`；侧栏 `st.radio` 竖排导航；分析区代码路径共用，不复制两份
- **建表**：应用首次调用 store 时 `CREATE TABLE IF NOT EXISTS`（无需单独迁移脚本）

## 目录结构

```
quant/favorites/
  __init__.py
  store.py              # ensure_table / list / is_favorite / add / remove
app/main.py             # 侧栏导航、★ 按钮、收藏列表、共用分析主区
tests/
  test_favorites_store.py
  test_app_import.py    # 补充导航/收藏相关源码断言
```

## 数据模型

表 `favorites`：

| 列 | 类型 | 说明 |
|----|------|------|
| `ts_code` | VARCHAR(16) PK | 股票代码，与 `stocks.ts_code` 一致 |
| `created_at` | DATETIME | 默认 `CURRENT_TIMESTAMP`；列表按此倒序 |

无 `user_id`。`list_favorites()` 左联 `stocks` 取 `name`；名称为空时 UI 仍显示 `ts_code`。

### Store API

- `ensure_table()` — `CREATE TABLE IF NOT EXISTS`
- `list_favorites() -> pd.DataFrame` — 列：`ts_code`, `name`, `created_at`，按 `created_at` DESC
- `is_favorite(ts_code) -> bool`
- `add(ts_code)` — `INSERT IGNORE`，幂等
- `remove(ts_code)` — `DELETE`；0 行也视为成功

## UI / 交互

### 导航

侧栏顶部：`st.radio(["首页", "收藏"], …)`，状态存 `st.session_state.nav`（竖向展示）。

### 首页

- 保留现有股票下拉、开始/结束日期
- 股票旁 ★ / ☆：已收藏显示 ★（点 → `remove`）；未收藏显示 ☆（点 → `add`）
- 主区：现有三个横向 tab，行为不变

### 收藏

- 侧栏：可点击收藏列表，文案 `ts_code  name`；空列表提示「暂无收藏」
- 仍显示开始/结束日期，与首页共用日期 `session_state`（切换导航不丢区间）
- 点击某只股票：写入当前 `ts_code`（`session_state`），**不切换**到首页；主区用同一套三个分析 tab 渲染
- 每条列表项提供取消收藏控件，与首页 ★ 共用 store API

### 代码组织约定

先根据 `nav` 解析出当前 `ts_code` 与日期，再进入现有 tab1/tab2/tab3 渲染逻辑，避免复制分析代码。

## 错误处理

- 整库连不上：与现有一致（提示后 `st.stop()`）
- 收藏读写失败：`st.error` 说明原因；在首页仍可尝试浏览（若连接已恢复）
- 重复收藏 / 取消不存在：幂等，不报错打扰用户

## 测试

- `tests/test_favorites_store.py`：增删查、幂等、`ensure_table` 可调用（mock 连接或跟随仓库现有 DB 测法）
- `tests/test_app_import.py`：断言源码含侧栏导航与收藏相关关键字（延续现有静态检查风格）

## 实现顺序建议

1. `quant/favorites/store.py` + 单元测试  
2. `app/main.py` 接入导航、★、收藏列表与共用主区  
3. 更新 `test_app_import.py`，手动点验首页收藏与收藏页点击看图  
