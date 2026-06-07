"""Shared Pydantic models and ticker helpers."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

TICKER_RE = re.compile(r"^[A-Z0-9^][A-Z0-9._^=-]{0,31}$")


def normalize_ticker(ticker: object) -> str:
    """Uppercase and validate one ticker symbol."""

    normalized = str(ticker).strip().upper()
    if (
        not normalized
        or ".." in normalized
        or "/" in normalized
        or "\\" in normalized
        or not TICKER_RE.match(normalized)
    ):
        raise ValueError(f"Invalid ticker format: {ticker!r}")
    return normalized


def normalize_tickers(tickers: list[object]) -> list[str]:
    """Normalize and de-duplicate tickers while preserving input order."""

    seen: set[str] = set()
    result: list[str] = []
    for raw in tickers:
        ticker = normalize_ticker(raw)
        if ticker not in seen:
            seen.add(ticker)
            result.append(ticker)
    return result


class RefreshRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)
    period: str = "5y"
    force: bool = False

    @field_validator("tickers")
    @classmethod
    def normalize_request_tickers(cls, value: list[str]) -> list[str]:
        return normalize_tickers(value)


class RefreshTickerResult(BaseModel):
    ticker: str
    status: str
    rows: int = 0
    as_of: str | None = None
    error: str | None = None


class RefreshResponse(BaseModel):
    status: str
    total: int
    succeeded: int
    failed: int
    results: list[RefreshTickerResult]


class HistoryResponse(BaseModel):
    ticker: str
    count: int
    start: date | None = None
    end: date | None = None
    rows: list[dict[str, Any]]


class SnapshotRefreshRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)
    benchmark: str = "SPY"

    @field_validator("tickers")
    @classmethod
    def normalize_request_tickers(cls, value: list[str]) -> list[str]:
        return normalize_tickers(value)

    @field_validator("benchmark")
    @classmethod
    def normalize_benchmark(cls, value: str) -> str:
        return normalize_ticker(value)


class SnapshotRefreshResponse(BaseModel):
    status: str
    total: int
    succeeded: int
    failed: int
    snapshots: dict[str, dict[str, Any]]
    errors: dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "market-data-lab"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
