import os
from dataclasses import asdict, dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent


def _load_env_file(path: Path):
    """Reads KEY=VALUE lines from backend/.env (gitignored), the same file backend/app uses. Real
    environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file(REPO_ROOT / ".env")

CURATED_DIR = Path(os.environ.get("KOMPAS_CURATED_DIR", PIPELINE_DIR / "curated"))
DATA_DIR = Path(os.environ.get("KOMPAS_DATA_DIR", REPO_ROOT / "data"))


def db_path() -> Path:
    return Path(os.environ.get("KOMPAS_DB", DATA_DIR / "kompas.db"))


def snapshot_dir() -> Path:
    return Path(os.environ.get("KOMPAS_SNAPSHOT_DIR", DATA_DIR / "snapshots"))


MANUAL_DIR = DATA_DIR / "manual"


@dataclass(frozen=True)
class Params:
    """Scoring parameters. Written into every snapshot so results can be reproduced."""

    z_active: float = 1.5           # trend score needed to activate a rung
    growth_active: float = 0.5      # low-confidence fallback: +50% vs previous period
    growth_decline: float = -0.33   # low-confidence fallback for Declining
    min_mentions: int = 5           # volume floor for count sources
    min_share: float = 0.005        # volume floor for share sources (DOSM)
    smoothing: int = 2              # rolling-mean window, in periods
    k: int = 8                      # max history periods compared against
    min_history: int = 4            # below this, use growth and flag low confidence
    std_floor_ratio: float = 0.1    # std is at least 10% of the mean, so flat series don't explode
    lead_quarters: float = 6        # default lead time per ladder step (documented default, not measured)
    fast_lead_factor: float = 0.5   # Fast scenario compresses lead time
    horizon: str = "2028-12-31"     # Ghost CV projection horizon
    stalled_periods: int = 9        # rung 1 active this long with no rung 2 -> Stalled
    hn_min_points: int = 100        # HN stories below this are not counted as buzz
    feed_window_days: int = 30     # repos created within this window can trend
    feed_hn_hours: int = 48        # HN stories older than this are no longer "moving"
    feed_min_points: int = 100         # front-page level on Hacker News
    feed_min_stars: int = 200          # a repo below this hasn't got anyone's attention yet
    feed_min_stars_per_day: float = 25
    feed_size: int = 50

    def to_dict(self) -> dict:
        return asdict(self)


PARAMS = Params()


@dataclass(frozen=True)
class Stream:
    """One ingestion stream: a source can have several (e.g. GitHub's monthly counts and its live poll).

    max_age_hours: a stream whose last successful run is older than this is reported stale.
    data_max_age_days: the newest *published* record may be at most this old before the data itself counts
    as stale (None: not measured, e.g. live polls where "nothing new" is normal)."""

    source: str
    stream: str
    kinds: tuple[str, ...]
    description: str
    max_age_hours: float
    data_max_age_days: float | None = None
    live: bool = False          # only expected while live polling is on (KOMPAS_LIVE=1)
    manual_file: str | None = None   # in data/manual/: needs a file a person provides

    @property
    def manual(self) -> bool:
        return self.manual_file is not None


STREAMS = [
    Stream("arxiv", "monthly", ("paper", "paper_count", "paper_baseline"),
           "Monthly paper counts per concept, plus the top papers", 24 * 35, 62),
    Stream("github", "counts", ("repo_count",), "New repositories per topic per month", 24 * 35, 62),
    Stream("github", "live", ("repo",), "Most-starred recent repos per topic, with star observations", 6,
           live=True),
    Stream("hn_front", "backfill", ("story",), "Hacker News stories with 100+ points", 24 * 35, 40),
    Stream("hn_front", "live", ("story",), "Current Hacker News top stories", 2, live=True),
    Stream("hn_hiring", "threads", ("hiring_post",), "Monthly 'Who is hiring?' threads", 24 * 35, 62),
    # JMI releases come out quarterly, months after the quarter ends (Q2 2026 was released 18 Aug 2026)
    Stream("dosm_jmi", "groups", ("occupation_group_stat",),
           "Official JMI release workbooks: online job offerings by MASCO major group", 24 * 8, 300),
    Stream("dosm_jmi", "occupations", ("occupation_stat",),
           "Manual CSV of 4-digit MASCO occupations (data/manual/dosm_jmi.csv)", 24 * 120, 300,
           manual_file="dosm_jmi.csv"),
    # MyCOL editions come out about once a year; an edition older than ~2 years is out of date
    Stream("mycol", "editions", ("critical_occupation", "shortage_assessment"),
           "MyCOL critical occupations and shortage indicators (data/manual/mycol_editions.csv)", 24 * 400, 800,
           manual_file="mycol_editions.csv"),
]


def stream(source: str, name: str) -> Stream:
    return next(s for s in STREAMS if s.source == source and s.stream == name)


# How far back incremental runs re-fetch, so late-indexed or still-changing records get picked up again.
OVERLAP_MONTHS = 1          # arXiv, GitHub counts, HN hiring threads
HN_OVERLAP_DAYS = 3         # HN points settle within a few days
HN_THREAD_FINAL_DAYS = 35   # a hiring thread still gets posts for about a month
LOCK_LEASE_MINUTES = 30     # renewed on every commit; a crashed run's lock frees itself after this

# DOSM Job Market Insights. Any release's archive page lists the whole series; two anchors so the list
# still works if one release page is ever withdrawn.
DOSM_JMI_BASE = "https://www.dosm.gov.my"
DOSM_JMI_ANCHORS = tuple(os.environ.get(
    "KOMPAS_DOSM_JMI_ANCHORS",
    "big-data-analytics-job-market-insights-and-my-job-profile-q12024,big-data-analytics-job-market-insights-q32025",
).split(","))
