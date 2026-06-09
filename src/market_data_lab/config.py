"""Project paths and runtime defaults for Market Data Lab."""

from __future__ import annotations

import os
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


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return Path(value).expanduser()


MOOMOO_ACCOUNT_WEB_URL = os.getenv("MOOMOO_ACCOUNT_WEB_URL", "http://127.0.0.1:8501")
MOOMOO_EXPORT_HOST = os.getenv("MOOMOO_EXPORT_HOST", "127.0.0.1")
MOOMOO_EXPORT_PORT = int(os.getenv("MOOMOO_EXPORT_PORT", "11111"))
MOOMOO_EXPORT_MARKET = os.getenv("MOOMOO_EXPORT_MARKET", "US")
MOOMOO_EXPORT_GROUP_TYPE = os.getenv("MOOMOO_EXPORT_GROUP_TYPE", "CUSTOM")
MARKET_DATA_UNIVERSE_EDITABLE = _env_flag("MARKET_DATA_UNIVERSE_EDITABLE", False)
FIRN_WATCHLIST_PATH = _env_path("FIRN_WATCHLIST_PATH")

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
