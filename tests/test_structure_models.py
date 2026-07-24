from quant.structure.models import Trendline, TrendlineResult


def test_trendline_price_at():
    tl = Trendline(
        side="up", slope=0.5, intercept=10.0,
        touch_dates=[], touch_count=2, score=20.0,
        start_date=None, end_date=None,
    )
    assert tl.price_at(0) == 10.0
    assert tl.price_at(4) == 12.0


def test_result_holds_lists():
    r = TrendlineResult(up=[], down=[], best_up=None, best_down=None)
    assert r.up == [] and r.best_down is None
