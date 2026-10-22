import os
from dataclasses import asdict, dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent


def _load_env_file(path: Path):
    """Reads KEY=VALUE lines from pipeline/.env (gitignored). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file(PIPELINE_DIR / ".env")

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
