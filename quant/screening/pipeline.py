"""选股扫描管线：全市场截面缩圈 -> 逐股因子计算 -> 动态加权合成 -> 排序。

跑批入口见 quant/screening/cli.py；结果落库见 quant/screening/store.py。
"""
from __future__ import annotations

import logging

import pandas as pd

from quant import config  # noqa: F401  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv
from quant.data import loader
from quant.screening import factors, weights

log = logging.getLogger(__name__)

_LOOKBACK_CAL_DAYS = 400  # 逐股加载约 400 个自然日，保证指标/回测窗口充足
_RESULT_COLS = [
    "ts_code", "rank_no", "total_score", "score_strategy",
    "score_structure", "score_volume", "weights_json", "factors_json",
]


def _latest_trade_date() -> str:
    load_dotenv()
    conn = connect_mysql()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(trade_date) FROM daily_qfq")
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise RuntimeError("daily_qfq 为空，请先运行日线更新脚本。")
    return str(row[0])


def _filter_universe(cross: pd.DataFrame, top_n_volume: int) -> pd.DataFrame:
    """剔除 ST / 停牌（volume=0）/ 无成交，按成交额取 top_n。"""
    df = cross.copy()
    if "name" in df.columns:
        df = df[~df["name"].fillna("").str.contains("ST", case=False)]
    df = df[(df["volume"] > 0) & (df["amount"] > 0)]
    return df.nlargest(top_n_volume, "amount")


def _start_for(trade_date: str) -> str:
    dt = pd.to_datetime(trade_date, format="%Y%m%d") - pd.Timedelta(
        days=_LOOKBACK_CAL_DAYS
    )
    return dt.strftime("%Y%m%d")


def _score_one(row: pd.Series, df: pd.DataFrame) -> dict | None:
    """计算一只候选股的组分数与明细；数据不足/异常返回 None。"""
    if df.empty or len(df) < 80:
        return None
    strat_w, w_detail = weights.dynamic_strategy_weights(df)
    s_strategy, d_strategy = factors.strategy_score(df, strat_w)
    s_structure, d_structure = factors.structure_score(df)
    return {
        "ts_code": row["ts_code"],
        "name": row.get("name", ""),
        "score_strategy": s_strategy,
        "score_structure": s_structure,
        "amount_today": float(row["amount"]),
        "amount_avg20": factors.amount_avg(df),
        "ret20": factors.ret20(df),
        "weights_json": {"strategy_weights": strat_w, **w_detail},
        "factors_json": {"strategy": d_strategy, "structure": d_structure},
    }


def run(
    trade_date: str | None = None,
    top_n_volume: int = 250,
    top_k: int = 50,
    group_weights: dict | None = None,
    progress_cb=None,
) -> pd.DataFrame:
    """执行一次选股扫描，返回按总分降序的 top_k 结果 DataFrame（不落库）。"""
    d = config.fmt_date(trade_date) if trade_date else _latest_trade_date()
    gw = weights.normalize_group_weights(group_weights)
    cross = loader.load_cross_section(d)
    if cross.empty:
        raise RuntimeError(f"{d} 无截面数据，请确认该日为交易日且日线已更新。")
    universe = _filter_universe(cross, top_n_volume)
    log.info("%s 全市场 %d 只，过滤后候选 %d 只", d, len(cross), len(universe))

    start = _start_for(d)
    scored: list[dict] = []
    for i, (_, row) in enumerate(universe.iterrows(), 1):
        try:
            df = loader.load_daily(row["ts_code"], start=start, end=d)
            rec = _score_one(row, df)
            if rec is not None:
                scored.append(rec)
        except Exception as exc:  # 单股异常不阻断整批
            log.warning("跳过 %s：%s", row["ts_code"], exc)
        if progress_cb:
            progress_cb(i, len(universe), row["ts_code"])

    if not scored:
        raise RuntimeError("候选池全部计算失败，无法生成选股结果。")

    panel = pd.DataFrame(scored)
    panel_amounts = panel["amount_today"]
    panel_rets = panel["ret20"].dropna()

    volume_scores, factor_extra = [], []
    for rec in scored:
        s_heat, d_heat = factors.heat_score(
            rec["amount_today"], rec["amount_avg20"], panel_amounts
        )
        s_mom, d_mom = factors.momentum_score(rec["ret20"], panel_rets)
        volume_scores.append(0.5 * s_heat + 0.5 * s_mom)
        factor_extra.append({"heat": d_heat, "momentum": d_mom})

    panel["score_volume"] = volume_scores
    panel["total_score"] = [
        weights.combine_scores(
            {"strategy": r["score_strategy"], "structure": r["score_structure"],
             "volume": r["score_volume"]},
            gw,
        )
        for _, r in panel.iterrows()
    ]
    for rec, extra in zip(scored, factor_extra):
        rec["factors_json"]["volume"] = extra

    panel = panel.sort_values("total_score", ascending=False).head(top_k)
    panel["rank_no"] = range(1, len(panel) + 1)
    return panel[_RESULT_COLS].reset_index(drop=True)
