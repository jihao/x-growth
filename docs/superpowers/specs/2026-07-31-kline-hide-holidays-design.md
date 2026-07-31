# K 线隐藏周末与中国法定假日设计

日期：2026-07-31  
状态：已确认设计  
范围：K 线 Plotly 轴隐藏周六/周日与 2020–2026 法定放假日；静态 JSON 固化；运行时不联网

## 背景

日线数据本身多为交易日，但 Plotly 按自然日画 x 轴会在周末、节假日留下空白。需要在画 K 线时排除这些空隙。

## 目标

1. 固化 2020–2026 中国法定**放假日**列表（来源 timor.tech，一次拉取进仓库）。
2. `kline_chart` 用 `rangebreaks` 隐藏：周六、周日 + 上述放假日。
3. 运行时只读本地 JSON，不调用外网 API。

## 非目标

- MySQL 存假日；运行时请求 timor。
- 按「库中缺失自然日」自动隐藏（非本次选型）。
- 改回测图 / 集中度图。
- 处理「调休补班」为交易日（A 股周末仍休市；rangebreaks 周末规则已覆盖）。

## 技术选型

- 数据源：`https://timor.tech/api/holiday/year/{YYYY}/`，只保留 `holiday: true` 的日期。
- 存储：`quant/calendar/cn_holidays_2020_2026.json`
- 画图：Plotly `fig.update_xaxes(rangebreaks=[...])`，周末 `bounds=["sat", "mon"]`

## 目录结构

```
quant/calendar/
  __init__.py
  cn_holidays.py                 # load_holidays()
  cn_holidays_2020_2026.json     # 固化放假日
  fetch_cn_holidays.py           # 可选：重新拉取生成 JSON
quant/charts/plots.py            # kline_chart 接入 rangebreaks
tests/
  test_cn_holidays.py
  test_charts.py                 # 断言 rangebreaks
```

说明：勿使用 `quant/config/` 包名，会遮蔽现有模块 `quant/config.py`（注入 mysql_config 路径）。

## 行为说明

- JSON：`source`、`years`、`holidays`（`YYYY-MM-DD` 排序列表）。
- `load_holidays()` 读文件并进程内缓存。
- `kline_chart` 对所有相关 x 轴应用相同 rangebreaks（共享轴一致）。

## 测试

- JSON 年份覆盖、抽样假日、日期格式。
- `kline_chart` 含周末 bounds 与假日 values 的 rangebreaks。
