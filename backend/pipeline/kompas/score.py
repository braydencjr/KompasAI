"""Signal Ladder scoring: trend per series, rung activation, status, family status, scenario projection."""

import math
from dataclasses import dataclass, field
from statistics import fmean, pstdev

from .aggregate import Point, Series
from .config import Params
from .curated import Curated
from .periods import quarters_between

LADDER = ("Watch", "Emerging", "Act now")


@dataclass
class SourceState:
    source: str
    trend: float | None
    low_confidence: bool
    active: bool
    declining: bool
    latest_period: str | None
    latest_value: float
    latest_raw_count: float


@dataclass
class RungState:
    active: bool = False
    declining: bool = False
    trend: float | None = None
    low_confidence: bool = True
    sources: list[str] = field(default_factory=list)       # sources with data on this rung
    active_sources: list[str] = field(default_factory=list)
    # concept | family (borrowed from an ancestor) | group (DOSM major groups of the concept's occupations:
    # context only, never active or declining, so it can't move the status)
    level: str = "concept"
    groups: list[str] = field(default_factory=list)        # level "group": the MASCO major groups behind it

    def to_dict(self) -> dict:
        return {
            "active": self.active, "declining": self.declining,
            "trend": None if self.trend is None else round(self.trend, 3),
            "low_confidence": self.low_confidence, "sources": self.sources,
            "active_sources": self.active_sources, "level": self.level, "groups": self.groups,
        }


@dataclass
class ConceptState:
    concept_id: str
    status: str
    rungs: dict[int, RungState]
    family_status: str | None = None
    family_id: str | None = None
    projected: dict[str, str] = field(default_factory=dict)
    sources: dict[str, SourceState] = field(default_factory=dict)


def smooth(values: list[float], window: int) -> list[float]:
    return [fmean(values[max(0, i - window + 1): i + 1]) for i in range(len(values))]


def trend(values: list[float], p: Params) -> tuple[float | None, bool]:
    """Returns (trend, low_confidence). With enough history this is a z-score against the previous k
    periods; otherwise growth vs the previous period, flagged low confidence."""
    s = smooth(values, p.smoothing)
    if len(s) < 2:
        return None, True
    current, history = s[-1], s[:-1][-p.k:]
    if len(history) >= p.min_history:
        mean = fmean(history)
        sd = max(pstdev(history), p.std_floor_ratio * abs(mean), 1e-9)
        return (current - mean) / sd, False
    prev = history[-1]
    if prev <= 0:
        return (1.0 if current > 0 else 0.0), True
    return current / prev - 1, True


def source_state(source: str, points: list[Point], volume: str, p: Params) -> SourceState:
    if not points:
        return SourceState(source, None, True, False, False, None, 0.0, 0.0)
    t, low = trend([pt.value for pt in points], p)
    last = points[-1]
    if volume == "share":
        enough, material = last.value >= p.min_share, max(pt.value for pt in points) >= p.min_share
    else:
        enough, material = last.raw_count >= p.min_mentions, max(pt.raw_count for pt in points) >= p.min_mentions
    up, down = (p.growth_active, p.growth_decline) if low else (p.z_active, -p.z_active)
    return SourceState(
        source, t, low,
        active=t is not None and t >= up and enough,
        # a fall only counts as Declining if the skill had real volume to begin with
        declining=t is not None and t <= down and material,
        latest_period=last.period, latest_value=last.value, latest_raw_count=last.raw_count,
    )


def status_from(rungs: dict[int, RungState]) -> str:
    if rungs[2].declining or (rungs[3].declining and rungs[3].level == "concept"):
        return "Declining"
    if rungs[3].active and rungs[3].level == "concept":
        return "Act now"
    if rungs[2].active:
        return "Emerging"
    if rungs[1].active:
        return "Watch"
    return "Stable"


def _rungs(states: list[tuple[SourceState, int]]) -> dict[int, RungState]:
    rungs = {1: RungState(), 2: RungState(), 3: RungState()}
    for st, rung in states:
        r = rungs[rung]
        r.sources.append(st.source)
        if st.active:
            r.active_sources.append(st.source)
        r.active |= st.active
        r.declining |= st.declining
        if st.trend is not None and (r.trend is None or st.trend > r.trend):
            r.trend = st.trend
    for rung, r in rungs.items():
        r.low_confidence = all(st.low_confidence for st, n in states if n == rung)
    return rungs


def _stalled(series: Series, cur: Curated, cid: str, p: Params) -> bool:
    """Rung 1 has been active for the last stalled_periods periods while rung 2 never was."""
    r1 = [(k, v) for k, v in series.items() if k[0] == cid and cur.sources[k[1]].rung == 1]
    r2 = [(k, v) for k, v in series.items() if k[0] == cid and cur.sources[k[1]].rung == 2]
    if not r1 or not r2:
        return False
    for back in range(p.stalled_periods):
        r1_active = any(
            len(pts) > back and source_state(k[1], pts[: len(pts) - back], cur.sources[k[1]].volume, p).active
            for k, pts in r1
        )
        r2_active = any(
            len(pts) > back and source_state(k[1], pts[: len(pts) - back], cur.sources[k[1]].volume, p).active
            for k, pts in r2
        )
        if not r1_active or r2_active:
            return False
    return True


def project(status: str, as_of: str, p: Params) -> dict[str, str]:
    """Ghost CV projection. Lead time per ladder step is a documented default, not a measurement."""
    horizon = max(quarters_between(as_of, p.horizon), 0)
    out = {}
    for scenario, factor in (("moderate", 1.0), ("fast", p.fast_lead_factor)):
        if status in ("Watch", "Emerging"):
            steps = math.floor(horizon / (p.lead_quarters * factor))
            out[scenario] = LADDER[min(LADDER.index(status) + steps, len(LADDER) - 1)]
        else:
            out[scenario] = status
    return out


def score_all(series: Series, cur: Curated, as_of: str, p: Params,
              groups: dict[str, tuple[list[str], list[Point]]] | None = None) -> dict[str, ConceptState]:
    by_concept: dict[str, dict[str, SourceState]] = {cid: {} for cid in cur.concepts}
    for (cid, source), pts in series.items():
        if cid in by_concept:
            by_concept[cid][source] = source_state(source, pts, cur.sources[source].volume, p)

    states: dict[str, ConceptState] = {}
    for cid, sources in by_concept.items():
        rungs = _rungs([(st, cur.sources[s].rung) for s, st in sources.items()])
        states[cid] = ConceptState(cid, "Stable", rungs, sources=sources)

    # Rung 3 is occupation-level: a concept without its own Malaysian series borrows its nearest
    # ancestor's, labelled level="family", and that borrowed rung can never make it "Act now".
    for cid, st in states.items():
        family = next((a for a in cur.ancestors(cid) if states[a].rungs[3].sources), None)
        if family:
            st.family_id = family
        if not st.rungs[3].sources and family:
            borrowed = states[family].rungs[3]
            st.rungs[3] = RungState(borrowed.active, borrowed.declining, borrowed.trend, borrowed.low_confidence,
                                    list(borrowed.sources), list(borrowed.active_sources), level="family")

    # Still no Malaysian figures: show where hiring for the concept's major occupation groups is heading.
    for cid, st in states.items():
        if not st.rungs[3].sources and cid in (groups or {}):
            names, pts = groups[cid]
            g = source_state("dosm_jmi", pts, "share", p)
            st.rungs[3] = RungState(False, False, g.trend, g.low_confidence, ["dosm_jmi"], [], level="group",
                                    groups=names)

    for cid, st in states.items():
        st.status = status_from(st.rungs)
        if st.status == "Watch" and _stalled(series, cur, cid, p):
            st.status = "Stalled"
    for cid, st in states.items():
        if st.family_id:
            st.family_status = states[st.family_id].status
        st.projected = project(st.status, as_of, p)
    return states
