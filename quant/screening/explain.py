"""选股结果的解释性文案与规则化交易建议。

输入为一行选股结果（分数 + 解析后的 factors/weights 字典），
输出中文分节解读、支撑/风险因素清单与操作建议。纯规则计算，不依赖 LLM，可单测。
"""
from __future__ import annotations

from quant.backtest import strategies

# 动作档位（0 最积极 -> 3 最消极）
ACTIONS = ["买入参考", "轻仓试探", "观望", "减仓/回避"]

DISCLAIMER = "以上内容由规则与数据自动生成，仅供研究参考，不构成投资建议。"

_LEVEL_CN = {"strong": "强", "medium": "中", "weak": "弱"}
_STATUS_CN = {"confirmed": "已确认", "pending": "钝化中"}
_SIDE_CN = {"top": "顶", "bottom": "底"}
_VERDICT_CN = {"extend": "加速", "similar": "相当", "end": "衰竭"}
_WAVE_DIR_CN = {"up": "上涨", "down": "下跌"}
_LINE_CN = {"up": "上升趋势线（支撑）", "down": "下降趋势线（压力）"}
_LINE_STATUS_CN = {
    ("up", "above"): "股价位于支撑线上方，支撑有效",
    ("up", "broken"): "股价跌破支撑线，趋势转弱",
    ("down", "below"): "股价仍受压力线压制",
    ("down", "broken"): "股价向上突破压力线，趋势转强",
}

_POSITION_ADVICE = {
    "买入参考": "若未持有：可考虑分批建仓（参考 3~5 成仓）；若已持有：可继续持有或小幅加仓。止损参考：跌破上升趋势线支撑。",
    "轻仓试探": "若未持有：小仓位试探（不超过 2 成），等信号进一步确认再加仓；若已持有：持有为主，暂不加仓。",
    "观望": "暂不开仓，等待评分或结构信号改善；若已持有：可持有但收紧止损。",
    "减仓/回避": "不建议参与；若已持有：逢高减仓或落袋，控制风险。",
}


def _strat_label(name: str) -> str:
    try:
        return strategies.get(name).label
    except Exception:
        return name


def _score_title(label: str, score: float) -> str:
    return f"{label}组（得分 {score:.2f}，0.50 为中性）"


def _strategy_section(factors: dict, weights: dict) -> list[str]:
    detail = factors.get("strategy") or {}
    sharpe = weights.get("sharpe") or {}
    fallback = weights.get("fallback")
    lines = []
    if fallback == "insufficient_data":
        lines.append("历史数据不足，策略权重退化为等权。")
    elif fallback == "all_non_positive":
        lines.append("近 120 日全部策略回测夏普非正，权重退化为等权（该股票近期不适合这些策略）。")
    else:
        lines.append("权重依据：各策略近 120 日滚动回测夏普比率归一化（近期表现好的策略话语权更大）。")
    holding = []
    for name, d in detail.items():
        sig = d.get("signal", 0)
        w = d.get("weight", 0.0)
        label = _strat_label(name)
        s = sharpe.get(name)
        s_txt = f"，近 120 日夏普 {s:.2f}" if isinstance(s, (int, float)) else ""
        state = "当前持仓中" if sig else "当前空仓"
        lines.append(f"- {label}：{state}（权重 {w:.0%}{s_txt}）")
        if sig:
            holding.append(label)
    if holding:
        lines.append(f"持仓中策略：{'、'.join(holding)}。")
    else:
        lines.append("当前没有任何策略处于持仓状态。")
    return lines


def _divergence_lines(d: dict) -> tuple[list[str], list[str], list[str]]:
    lines, risks, boosts = [], [], []
    for side in ("bottom", "top"):
        ev = d.get(side)
        if not ev:
            continue
        cn = f"{_SIDE_CN[side]}背离（{_LEVEL_CN.get(ev.get('level'), ev.get('level', ''))}，{_STATUS_CN.get(ev.get('status'), ev.get('status', ''))}）"
        ago = ev.get("bars_since")
        ago_txt = f"，{ago} 个交易日前形成" if isinstance(ago, int) else ""
        lines.append(f"- 识别到{cn}{ago_txt}。")
        if side == "bottom":
            if ev.get("status") == "confirmed":
                boosts.append(f"{cn}，下跌动能衰竭、反弹概率上升")
            else:
                boosts.append(f"{cn}，潜在转强信号，等待确认")
        else:
            if ev.get("status") == "confirmed":
                risks.append(f"{cn}，上涨动能衰竭，追高需谨慎")
            else:
                risks.append(f"{cn}，短期注意回落风险")
    if not lines:
        lines.append("- 近 60 个交易日未识别到有效背离，中性。")
    return lines, risks, boosts


def _trendline_lines(d: dict) -> tuple[list[str], list[str], list[str]]:
    lines, risks, boosts = [], [], []
    for side in ("up", "down"):
        tl = d.get(f"{side}_line")
        if not tl:
            continue
        status = tl.get("status")
        txt = _LINE_STATUS_CN.get((side, status), f"状态 {status}")
        touch = tl.get("touch_count")
        touch_txt = f"（触点 {touch} 次，触点越多线越可靠）" if touch else ""
        lines.append(f"- {_LINE_CN[side]}：{txt}{touch_txt}。")
        if (side, status) == ("down", "broken"):
            boosts.append("向上突破下降压力线，中期趋势转强")
        elif (side, status) == ("up", "broken"):
            risks.append("跌破上升趋势线支撑，趋势走弱")
    if not lines:
        lines.append("- 未识别到可靠趋势线，中性。")
    return lines, risks, boosts


def _wave_lines(d: dict) -> tuple[list[str], list[str], list[str]]:
    if d.get("verdict") is None:
        return ["- 未识别到完整三浪结构，中性。"], [], []
    direction = d.get("direction")
    verdict = d.get("verdict")
    ratio = d.get("ratio")
    ratio_txt = f"（三浪/一浪速度比 {ratio:.2f}）" if isinstance(ratio, (int, float)) else ""
    lines = [
        f"- {_WAVE_DIR_CN.get(direction, direction)}三浪，"
        f"第三浪速度{_VERDICT_CN.get(verdict, verdict)}{ratio_txt}。"
    ]
    risks, boosts = [], []
    if (direction, verdict) == ("up", "extend"):
        boosts.append("上涨第三浪加速，主升段特征")
    elif (direction, verdict) == ("down", "extend"):
        risks.append("下跌第三浪加速，切勿接飞刀")
    return lines, risks, boosts


def _volume_lines(d: dict) -> list[str]:
    heat = d.get("heat") or {}
    mom = d.get("momentum") or {}
    lines = []
    rank_pct = heat.get("rank_pct")
    vol_ratio = heat.get("vol_ratio")
    if isinstance(rank_pct, (int, float)):
        lines.append(f"- 成交额超过候选池 {rank_pct:.0%} 的股票，市场关注度高。")
    if isinstance(vol_ratio, (int, float)):
        if vol_ratio >= 2:
            lines.append(f"- 量比 {vol_ratio:.1f}，明显放量。")
        elif vol_ratio <= 0.6:
            lines.append(f"- 量比 {vol_ratio:.1f}，成交萎缩。")
        else:
            lines.append(f"- 量比 {vol_ratio:.1f}，量能正常。")
    ret20 = mom.get("ret20")
    if isinstance(ret20, (int, float)):
        lines.append(f"- 近 20 日涨跌幅 {ret20:+.1%}。")
    return lines


def _base_action(total_score: float) -> int:
    if total_score >= 0.75:
        return 0
    if total_score >= 0.60:
        return 1
    if total_score >= 0.45:
        return 2
    return 3


def explain_row(row: dict) -> dict:
    """生成解读报告。

    row 需包含：total_score / score_strategy / score_structure / score_volume
    以及解析后的 factors（dict）与 weights（dict）。
    返回 {action, action_index, position_advice, reasons, sections, disclaimer}。
    """
    factors = row.get("factors") or {}
    weights = row.get("weights") or {}
    total = float(row.get("total_score") or 0.0)
    s_strategy = float(row.get("score_strategy") or 0.0)
    s_structure = float(row.get("score_structure") or 0.0)
    s_volume = float(row.get("score_volume") or 0.0)

    structure = factors.get("structure") or {}
    div_lines, div_risks, div_boosts = _divergence_lines(structure.get("divergence") or {})
    tl_lines, tl_risks, tl_boosts = _trendline_lines(structure.get("trendline") or {})
    wave_lines, wave_risks, wave_boosts = _wave_lines(structure.get("wave") or {})

    hard_risks = [
        r for r in (div_risks + tl_risks + wave_risks)
        if ("已确认" in r) or ("跌破" in r) or ("加速" in r)
    ]
    risks = div_risks + tl_risks + wave_risks
    boosts = div_boosts + tl_boosts + wave_boosts

    strategy_detail = factors.get("strategy") or {}
    n_holding = sum(1 for d in strategy_detail.values() if d.get("signal"))
    if n_holding == 0 and strategy_detail:
        risks.append("当前无任何策略处于持仓状态，信号一致性差")
    elif n_holding == len(strategy_detail) and strategy_detail:
        boosts.append("全部策略均处于持仓状态，信号一致性好")

    idx = _base_action(total)
    idx = min(idx + len(hard_risks), len(ACTIONS) - 1)
    action = ACTIONS[idx]

    reasons = []
    if boosts:
        reasons.append("支撑因素：" + "；".join(boosts))
    if risks:
        reasons.append("风险因素：" + "；".join(risks))
    if not reasons:
        reasons.append("各因子无明显倾向，评分主要来自量价与统计特征。")

    sections = [
        {"title": _score_title("策略", s_strategy),
         "lines": _strategy_section(factors, weights)},
        {"title": _score_title("结构", s_structure),
         "lines": div_lines + tl_lines + wave_lines},
        {"title": _score_title("量价", s_volume),
         "lines": _volume_lines(factors.get("volume") or {})},
    ]
    return {
        "action": action,
        "action_index": idx,
        "position_advice": _POSITION_ADVICE[action],
        "reasons": reasons,
        "sections": sections,
        "disclaimer": DISCLAIMER,
    }
