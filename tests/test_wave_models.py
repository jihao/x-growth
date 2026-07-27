from quant.structure.models import WaveLeg, WaveTriple, WaveSpeedResult


def test_wave_leg_fields():
    leg = WaveLeg(
        start_date="a", end_date="b", start_price=10.0, end_price=12.0,
        bars=5, speed=0.4, ret=0.2,
    )
    assert leg.bars == 5 and leg.speed == 0.4


def test_wave_speed_result_empty():
    r = WaveSpeedResult(current=None, previous_available=False)
    assert r.current is None and r.previous_available is False
