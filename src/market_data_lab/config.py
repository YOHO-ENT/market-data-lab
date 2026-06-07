"""Project paths and runtime defaults for Market Data Lab."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
PRICE_HISTORY_DIR = DATA_DIR / "price_history"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
RUNS_DIR = DATA_DIR / "runs"
REFRESH_RUN_DIR = RUNS_DIR / "refresh"
UNIVERSE_PATH = CONFIG_DIR / "universe.yaml"

DEFAULT_PERIOD = "5y"
DEFAULT_INTERVAL = "1d"
DEFAULT_BENCHMARK = "SPY"
DEFAULT_CHART_RANGE = "1y"
STALE_PRICE_MAX_AGE_DAYS = 7

SUPPORTED_CHART_RANGES: dict[str, int] = {
    "6mo": 126,
    "1y": 252,
    "2y": 504,
    "5y": 1260,
}


def ensure_data_dirs() -> None:
    """Create local data directories if they do not already exist."""

    PRICE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    REFRESH_RUN_DIR.mkdir(parents=True, exist_ok=True)
