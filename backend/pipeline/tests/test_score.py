import pytest

from kompas.aggregate import Point
from kompas.config import Params
from kompas.score import RungState, project, source_state, status_from, trend

P = Params()


def pts(values, raw=10):
    return [Point(f"2026-{i + 1:02d}", v, raw, "x") for i, v in enumerate(values)]


def test_z_score_against_own_history():
    # flat history then a jump: smoothed current = (0.10 + 0.30) / 2 = 0.20 vs mean 0.10
    t, low = trend([0.10, 0.10, 0.10, 0.10, 0.10, 0.30], P)
    assert not low
    assert t == pytest.approx((0.20 - 0.10) / (0.1 * 0.10))  # std floored at 10% of the mean


def test_short_history_falls_back_to_growth_and_low_confidence():
    t, low = trend([0.10, 0.10, 0.20], P)
    assert low
    assert t == pytest.approx(0.15 / 0.10 - 1)


def test_volume_floor_blocks_tiny_counts():
    assert not source_state("hn_hiring", pts([0.0] * 5 + [0.5], raw=2), "count", P).active
    assert source_state("hn_hiring", pts([0.0] * 5 + [0.5], raw=20), "count", P).active


def test_decline_needs_material_volume():
    falling = [0.5, 0.5, 0.5, 0.5, 0.5, 0.1]
    assert source_state("hn_hiring", pts(falling, raw=40), "count", P).declining
    assert not source_state("hn_hiring", pts(falling, raw=2), "count", P).declining


def rungs(r1=False, r2=False, r3=False, level="concept", declining2=False):
    return {1: RungState(active=r1), 2: RungState(active=r2, declining=declining2),
            3: RungState(active=r3, level=level)}


def test_status_rules():
    assert status_from(rungs(r1=True)) == "Watch"
    assert status_from(rungs(r1=True, r2=True)) == "Emerging"
    assert status_from(rungs(r3=True)) == "Act now"
    assert status_from(rungs(declining2=True)) == "Declining"
    assert status_from(rungs()) == "Stable"


def test_family_level_demand_never_gives_act_now():
    assert status_from(rungs(r1=True, r3=True, level="family")) == "Watch"


def test_projection_fast_moves_further_than_moderate():
    proj = project("Watch", "2026-10-01", P)
    assert proj["moderate"] == "Emerging"
    assert proj["fast"] == "Act now"
    assert project("Stable", "2026-10-01", P) == {"moderate": "Stable", "fast": "Stable"}
