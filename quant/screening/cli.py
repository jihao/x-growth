"""选股跑批入口。

用法：
    python -m quant.screening.cli                      # 最新交易日，默认参数
    python -m quant.screening.cli --date 20260731 --top-n-volume 250 --top-k 50
    python -m quant.screening.cli --w-strategy 0.5 --w-structure 0.3 --w-volume 0.2
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from quant.screening import pipeline, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="多策略加权选股跑批")
    ap.add_argument("--date", help="交易日 YYYYMMDD，缺省取库内最新")
    ap.add_argument("--top-n-volume", type=int, default=250, help="成交额缩圈数量")
    ap.add_argument("--top-k", type=int, default=50, help="最终选股数量")
    ap.add_argument("--w-strategy", type=float, help="策略组权重")
    ap.add_argument("--w-structure", type=float, help="结构组权重")
    ap.add_argument("--w-volume", type=float, help="量价组权重")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落库")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    group_weights = {
        "strategy": args.w_strategy,
        "structure": args.w_structure,
        "volume": args.w_volume,
    }
    group_weights = {k: v for k, v in group_weights.items() if v is not None} or None

    results = pipeline.run(
        trade_date=args.date,
        top_n_volume=args.top_n_volume,
        top_k=args.top_k,
        group_weights=group_weights,
    )
    show = results.copy()
    for c in ["total_score", "score_strategy", "score_structure", "score_volume"]:
        show[c] = show[c].astype(float).round(4)
    print(show[["rank_no", "ts_code", "total_score", "score_strategy",
                "score_structure", "score_volume"]].to_string(index=False))

    if args.dry_run:
        print("\n[dry-run] 未落库。")
        return 0
    d = args.date or pipeline._latest_trade_date()
    n = store.save_results(d, results)
    print(f"\n已保存 {n} 条到 screening_results（trade_date={d}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
