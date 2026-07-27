from quant.structure.models import DivergenceEvent, DivergenceResult


def test_divergence_event_pending_fields():
    ev = DivergenceEvent(
        side="top",
        status="pending",
        p1_date="a",
        p1_price=10.0,
        d1=1.0,
        d1_date="a",
        p2_date="b",
        p2_price=11.0,
        d2=0.8,
        d2_date="b",
    )
    assert ev.side == "top" and ev.status == "pending"
    assert ev.confirm_date is None and ev.confirm_dif is None


def test_divergence_result_defaults():
    r = DivergenceResult()
    assert r.events == [] and r.overlay_events == []
