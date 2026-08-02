from __future__ import annotations

import pytest

from quant.screening import explain


def _row(
    total=0.8,
    s_strategy=1.0,
    s_structure=0.7,
    s_volume=0.6,
    strategy_detail=None,
    divergence=None,
    trendline=None,
    wave=None,
    volume=None,
    weights=None,
):
    if strategy_detail is None:
        strategy_detail = {
            "ma_cross": {"signal": 1, "weight": 0.5},
            "macd": {"signal": 1, "weight": 0.5},
        }
    factors = {
        "strategy": strategy_detail,
        "structure": {
            "divergence": divergence if divergence is not None else {"score": 0.5},
            "trendline": trendline if trendline is not None else {"score": 0.5},
            "wave": wave if wave is not None else {"score": 0.5, "verdict": None},
        },
        "volume": volume if volume is not None else {},
    }
    return {
        "total_score": total,
        "score_strategy": s_strategy,
        "score_structure": s_structure,
        "score_volume": s_volume,
        "factors": factors,
        "weights": weights or {"sharpe": {"ma_cross": 1.0, "macd": 0.8}},
    }


def test_high_score_buy_action():
    rep = explain.explain_row(_row(total=0.8))
    assert rep["action"] == "买入参考"
    assert rep["action_index"] == 0
    assert "分批建仓" in rep["position_advice"]
    assert any("全部策略均处于持仓状态" in r for r in rep["reasons"])


def test_mid_score_observe():
    assert explain.explain_row(_row(total=0.5))["action"] == "观望"
    assert explain.explain_row(_row(total=0.65))["action"] == "轻仓试探"
    assert explain.explain_row(_row(total=0.3))["action"] == "减仓/回避"


def test_confirmed_top_divergence_downgrades():
    div = {
        "score": 0.1,
        "top": {"status": "confirmed", "level": "strong",
                "p2_date": "2026-07-28", "bars_since": 3, "magnitude": 0.9},
    }
    rep = explain.explain_row(_row(total=0.8, divergence=div))
    assert rep["action"] == "轻仓试探"  # 0 + 1 个硬伤
    assert any("顶背离" in r for r in rep["reasons"])


def test_multiple_hard_risks_downgrade_by_count():
    div = {"score": 0.0,
           "top": {"status": "confirmed", "level": "strong",
                   "p2_date": "2026-07-28", "bars_since": 3, "magnitude": 0.9}}
    tl = {"score": 0.1,
          "up_line": {"status": "broken", "touch_count": 3, "distance_pct": -0.03}}
    rep = explain.explain_row(_row(total=0.8, divergence=div, trendline=tl))
    assert rep["action"] == "观望"  # 买入参考档 + 2 个硬伤降两级


def test_low_score_plus_hard_risk_to_avoid():
    div = {"score": 0.0,
           "top": {"status": "confirmed", "level": "strong",
                   "p2_date": "2026-07-28", "bars_since": 3, "magnitude": 0.9}}
    rep = explain.explain_row(_row(total=0.5, divergence=div))
    assert rep["action"] == "减仓/回避"  # 观望档 + 1 个硬伤
    assert "逢高减仓" in rep["position_advice"]


def test_confirmed_bottom_divergence_boost():
    div = {
        "score": 0.9,
        "bottom": {"status": "confirmed", "level": "medium",
                   "p2_date": "2026-07-28", "bars_since": 2, "magnitude": 0.7},
    }
    rep = explain.explain_row(_row(total=0.65, divergence=div))
    assert rep["action"] == "轻仓试探"
    assert any("底背离" in r for r in rep["reasons"])
    struct_lines = rep["sections"][1]["lines"]
    assert any("底背离（中，已确认）" in line for line in struct_lines)


def test_no_strategy_holding_adds_risk():
    rep = explain.explain_row(_row(
        strategy_detail={"ma_cross": {"signal": 0, "weight": 1.0}},
    ))
    assert any("无任何策略处于持仓状态" in r for r in rep["reasons"])


def test_sections_have_three_groups_with_scores():
    rep = explain.explain_row(_row())
    titles = [s["title"] for s in rep["sections"]]
    assert any("策略组" in t and "1.00" in t for t in titles)
    assert any("结构组" in t for t in titles)
    assert any("量价组" in t for t in titles)


def test_wave_and_trendline_text():
    wave = {"score": 1.0, "direction": "up", "verdict": "extend", "ratio": 1.3}
    tl = {"score": 1.0,
          "down_line": {"status": "broken", "touch_count": 4, "distance_pct": 0.02}}
    rep = explain.explain_row(_row(wave=wave, trendline=tl))
    reasons = " ".join(rep["reasons"])
    assert "三浪加速" in reasons
    assert "突破下降压力线" in reasons


def test_fallback_weight_note():
    rep = explain.explain_row(_row(weights={"fallback": "all_non_positive"}))
    strat_lines = rep["sections"][0]["lines"]
    assert any("退化为等权" in line for line in strat_lines)


def test_volume_lines():
    vol = {"heat": {"rank_pct": 0.92, "vol_ratio": 2.5},
           "momentum": {"ret20": 0.085, "pct": 0.9}}
    rep = explain.explain_row(_row(volume=vol))
    lines = rep["sections"][2]["lines"]
    assert any("92%" in line for line in lines)
    assert any("明显放量" in line for line in lines)
    assert any("+8.5%" in line for line in lines)


def test_disclaimer_present():
    rep = explain.explain_row(_row())
    assert "不构成投资建议" in rep["disclaimer"]
    assert len(explain.ACTIONS) == 4


def _regime(level, cap):
    return {"level": level, "score": -0.6, "cap_index": cap}


def test_regime_weak_caps_to_observe():
    row = _row(total=0.8)  # 基础档位「买入参考」
    row["regime"] = _regime("弱势", 2)
    rep = explain.explain_row(row)
    assert rep["action"] == "观望"
    assert rep["action_index"] == 2
    assert any("市场环境弱势" in r and "下调" in r for r in rep["reasons"])


def test_regime_mild_weak_caps_to_probe():
    row = _row(total=0.8)
    row["regime"] = _regime("偏弱", 1)
    rep = explain.explain_row(row)
    assert rep["action"] == "轻仓试探"
    assert rep["action_index"] == 1


def test_regime_strong_no_cap():
    row = _row(total=0.8)
    row["regime"] = _regime("强势", 0)
    rep = explain.explain_row(row)
    assert rep["action"] == "买入参考"
    assert not any("市场环境" in r for r in rep["reasons"])


def test_regime_never_upgrades():
    row = _row(total=0.4)  # 基础档位「减仓/回避」(3)
    row["regime"] = _regime("偏弱", 1)  # cap 更低（更激进）时不生效
    rep = explain.explain_row(row)
    assert rep["action"] == "减仓/回避"
    assert rep["action_index"] == 3
