"""选股跑批入口。

用法：
    python -m quant.screening.cli                      # 最新交易日，默认参数
    python -m quant.screening.cli --date 20260731 --top-n-volume 250 --top-k 50
    python -m quant.screening.cli --from 20260701 --to 20260731   # 区间逐日回算
    python -m quant.screening.cli --from 20260701 --skip-existing # 跳过已算过的日期
    python -m quant.screening.cli --w-strategy 0.5 --w-structure 0.3 --w-volume 0.2
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from quant.data import loader  # noqa: E402
from quant.screening import pipeline, store  # noqa: E402


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="多策略加权选股跑批")
    ap.add_argument("--date", help="单日 YYYYMMDD，缺省取库内最新")
    ap.add_argument("--from", dest="from_date", help="区间开始 YYYYMMDD（逐日回算）")
    ap.add_argument("--to", dest="to_date", help="区间结束 YYYYMMDD，缺省到库内最新")
    ap.add_argument("--skip-existing", action="store_true",
                    help="区间模式下跳过已有结果的日期")
    ap.add_argument("--top-n-volume", type=int, default=250, help="成交额缩圈数量")
    ap.add_argument("--top-k", type=int, default=50, help="最终选股数量")
    ap.add_argument("--w-strategy", type=float, help="策略组权重")
    ap.add_argument("--w-structure", type=float, help="结构组权重")
    ap.add_argument("--w-volume", type=float, help="量价组权重")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落库")
    args = ap.parse_args()
    if args.date and args.from_date:
        ap.error("--date 与 --from 只能二选一")
    return args


def _group_weights(args) -> dict | None:
    gw = {
        "strategy": args.w_strategy,
        "structure": args.w_structure,
        "volume": args.w_volume,
    }
    return {k: v for k, v in gw.items() if v is not None} or None


def _run_one(trade_date: str, args, gw) -> None:
    """单日：跑管线、打印榜单、落库（除非 dry-run）。"""
    results = pipeline.run(
        trade_date=trade_date,
        top_n_volume=args.top_n_volume,
        top_k=args.top_k,
        group_weights=gw,
    )
    show = results.copy()
    for c in ["total_score", "score_strategy", "score_structure", "score_volume"]:
        show[c] = show[c].astype(float).round(4)
    print(show[["rank_no", "ts_code", "total_score", "score_strategy",
                "score_structure", "score_volume"]].to_string(index=False))
    if args.dry_run:
        print("\n[dry-run] 未落库。")
        return
    n = store.save_results(trade_date, results)
    print(f"\n已保存 {n} 条到 screening_results（trade_date={trade_date}）。")


def _run_range(args, gw) -> None:
    end = args.to_date or "99991231"
    dates = loader.trading_dates(args.from_date, end)
    if not dates:
        raise SystemExit(f"区间内无交易日数据：{args.from_date} ~ {end}")
    existing = set(store.list_dates()) if args.skip_existing else set()
    todo = [d for d in dates if d not in existing]
    print(f"区间 {dates[0]} ~ {dates[-1]} 共 {len(dates)} 个交易日，"
          f"跳过已有 {len(dates) - len(todo)} 天，待算 {len(todo)} 天。")
    for i, d in enumerate(todo, 1):
        results = pipeline.run(
            trade_date=d,
            top_n_volume=args.top_n_volume,
            top_k=args.top_k,
            group_weights=gw,
        )
        top1 = results.iloc[0]
        if args.dry_run:
            print(f"[{i}/{len(todo)}] {d} [dry-run] 榜首 {top1['ts_code']} "
                  f"{float(top1['total_score']):.4f}")
        else:
            n = store.save_results(d, results)
            print(f"[{i}/{len(todo)}] {d} 保存 {n} 条，榜首 {top1['ts_code']} "
                  f"{float(top1['total_score']):.4f}")


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    gw = _group_weights(args)
    if args.from_date:
        _run_range(args, gw)
    else:
        _run_one(args.date or pipeline._latest_trade_date(), args, gw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
