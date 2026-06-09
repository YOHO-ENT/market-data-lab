from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from market_data_lab import cli, services
from market_data_lab.api.app import app
from market_data_lab.models import RefreshResponse, RefreshTickerResult
from market_data_lab.storage import ParquetPriceStore
from market_data_lab.moomoo_integration import build_universe_from_export
from market_data_lab.watchlist_sync import sync_configs


def standard_frame(dates: list[str], closes: list[float] | None = None) -> pd.DataFrame:
    closes = closes or [10.0 + index for index, _ in enumerate(dates)]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "ticker": "BSX",
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [100_000] * len(dates),
            "dividends": [0.0] * len(dates),
            "stock_splits": [0.0] * len(dates),
            "currency": "USD",
            "source": "test",
            "fetched_at": [pd.Timestamp("2026-06-01T00:00:00Z").isoformat()] * len(dates),
        }
    )


def generated_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-06-05", periods=rows)
    closes = [100.0 + idx * 0.2 for idx in range(rows)]
    return standard_frame([str(date.date()) for date in dates], closes=closes)


def declining_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-06-05", periods=rows)
    closes = [200.0 - idx * 0.2 for idx in range(rows)]
    return standard_frame([str(date.date()) for date in dates], closes=closes)


def flat_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-06-05", periods=rows)
    return standard_frame([str(date.date()) for date in dates], closes=[100.0] * rows)


def isolated_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ParquetPriceStore:
    store = ParquetPriceStore(tmp_path / "price_history")
    monkeypatch.setattr(services, "_store", lambda: store)
    return store


def fail_if_fetcher_called() -> None:
    raise AssertionError("GET endpoints must not call yfinance")


def test_health():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "market-data-lab"


def test_invalid_history_ticker_returns_400():
    client = TestClient(app)

    response = client.get("/history/A..PL")

    assert response.status_code == 400


def test_history_missing_cache_returns_404_without_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolated_store(monkeypatch, tmp_path)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/history/BSX")

    assert response.status_code == 404


def test_snapshot_missing_cache_returns_stable_unavailable_without_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated_store(monkeypatch, tmp_path)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/snapshot/BSX")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "BSX"
    assert data["price"] is None
    assert data["trend"] == "unavailable"
    assert data["support_levels"] == []
    assert data["relative_strength_vs_spy"]["status"] == "unavailable"
    assert data["data_quality"]["status"] == "unavailable"
    assert "cached price history unavailable" in data["data_quality"]["warnings"][0]
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_chart_missing_cache_returns_stable_unavailable_without_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated_store(monkeypatch, tmp_path)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/chart/BSX")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "BSX"
    assert data["has_image"] is False
    assert data["points"] == []
    assert data["ma20"] == []
    assert data["data_quality"]["status"] == "unavailable"
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_snapshot_uses_cached_primary_even_when_benchmark_cache_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("BSX", generated_frame())
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/snapshot/BSX?benchmark=SPY")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "BSX"
    assert data["price"] is not None
    assert data["relative_strength_vs_spy"]["status"] == "unavailable"
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_snapshots_batches_in_requested_order_and_applies_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("AAPL", generated_frame())
    store.write("BSX", generated_frame())
    store.write("MRK", generated_frame())
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/snapshots?tickers=AAPL,BSX,MRK&limit=2&benchmark=SPY")

    assert response.status_code == 200
    data = response.json()
    assert data["benchmark"] == "SPY"
    assert data["limit"] == 2
    assert data["requested_count"] == 3
    assert data["count"] == 2
    assert data["tickers"] == ["AAPL", "BSX"]
    assert [snapshot["ticker"] for snapshot in data["snapshots"]] == ["AAPL", "BSX"]
    assert all(snapshot["price"] is not None for snapshot in data["snapshots"])
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_snapshots_missing_cache_returns_unavailable_snapshots_without_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated_store(monkeypatch, tmp_path)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/snapshots?tickers=AAPL,BSX&limit=100&benchmark=SPY")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [snapshot["ticker"] for snapshot in data["snapshots"]] == ["AAPL", "BSX"]
    for snapshot in data["snapshots"]:
        assert snapshot["price"] is None
        assert snapshot["trend"] == "unavailable"
        assert snapshot["support_levels"] == []
        assert snapshot["relative_strength_vs_spy"]["status"] == "unavailable"
        assert snapshot["data_quality"]["status"] == "unavailable"
        assert "cached price history unavailable" in snapshot["data_quality"]["warnings"][0]
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_status_reports_cache_tickers_latest_stale_and_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("BSX", standard_frame(["2024-01-02", "2024-01-03"], closes=[10.0, 11.0]))
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "BSX.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(services, "SNAPSHOT_DIR", snapshot_dir)
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir(exist_ok=True)
    universe_path.write_text(
        yaml.safe_dump({"groups": {"healthcare": ["BSX", "MRK"]}}, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    client = TestClient(app)

    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["price_history_files"] == 1
    assert data["cached_tickers"] == ["BSX"]
    assert data["cached_ticker_count"] == 1
    assert data["latest_as_of"] == "2024-01-03"
    assert data["last_refresh"] == "2026-06-01T00:00:00+00:00"
    assert data["stale_count"] == 1
    assert data["stale_tickers"] == ["BSX"]
    assert data["unavailable_count"] == 0
    assert data["snapshots"] == 1
    assert data["snapshot_count"] == 1
    assert data["snapshot_tickers"] == ["BSX"]
    assert data["groups"]["healthcare"] == ["BSX", "MRK"]
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_status_reports_quality_details_for_local_parquet_issues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    frame = standard_frame(["2024-01-01", "2024-01-02", "2024-01-03"], closes=[10.0, 11.0, 12.0])
    frame.loc[1, "close"] = pd.NA
    frame.loc[1, "volume"] = pd.NA
    frame.loc[2, "high"] = float("inf")
    frame.to_parquet(store.path_for("BSX"), index=False)
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    monkeypatch.setattr(services, "SNAPSHOT_DIR", snapshot_dir)
    client = TestClient(app)

    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    checks = data["data_quality"]["checks"]
    assert data["cache_status"] == "partial"
    assert data["cached_ticker_count"] == 1
    assert data["latest_as_of"] == "2024-01-03"
    assert data["last_refresh"] == "2026-06-01T00:00:00+00:00"
    assert checks["missing_price"]["count"] == 1
    assert checks["missing_price"]["details"][0]["count"] == 1
    assert checks["missing_volume"]["count"] == 1
    assert checks["stale_data"]["count"] == 1
    assert checks["short_history"]["count"] == 1
    assert checks["invalid_values"]["count"] == 1
    assert checks["invalid_values"]["details"][0]["columns"] == ["high"]
    assert data["data_quality_report"]["invalid_values"] == checks["invalid_values"]
    assert data["entries"][0]["data_quality"]["status"] == "partial"
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_quality_endpoint_returns_quality_summary_and_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    frame = standard_frame(["2024-01-01", "2024-01-02", "2024-01-03"], closes=[10.0, 11.0, 12.0])
    frame.loc[1, "close"] = pd.NA
    frame.loc[1, "volume"] = pd.NA
    frame.to_parquet(store.path_for("BSX"), index=False)
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    monkeypatch.setattr(services, "SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get("/quality")

    assert response.status_code == 200
    data = response.json()
    assert data["cache_status"] == "partial"
    assert data["cached_ticker_count"] == 1
    assert data["data_quality"]["status"] == "partial"
    assert data["data_quality"]["checks"]["missing_price"]["count"] == 1
    assert data["data_quality_report"] == data["data_quality"]["checks"]
    assert data["data_quality_report"]["missing_volume"]["details"][0]["ticker"] == "BSX"
    assert data["entries"][0]["ticker"] == "BSX"
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_screen_filters_cached_snapshots_without_fetch_and_returns_json_safe_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("BSX", generated_frame())
    store.write("MRK", declining_frame())
    store.write("SPY", flat_frame())
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    client = TestClient(app)

    response = client.get(
        "/screen",
        params={
            "tickers": "BSX,MRK",
            "trend": "bullish",
            "breakout_status": "near_breakout",
            "data_quality": "ok",
            "rsi_min": 80,
            "trend_score_min": 90,
            "liquidity_score_min": 40,
            "relative_strength": "outperforming",
            "ma_distance_max": 0.02,
            "ma": "20",
            "week52_position_min": 0.9,
            "volume_ratio_min": 1.0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_count"] == 2
    assert data["count"] == 1
    assert data["default_views"]
    assert data["filters"]["trend"] == ["bullish"]
    row = data["results"][0]
    assert row["ticker"] == "BSX"
    assert row["trend"] == "bullish"
    assert row["breakout_status"] == "near_breakout"
    assert row["data_quality_status"] == "ok"
    assert row["relative_strength_status"] == "outperforming"
    assert row["rsi14"] >= 80
    assert abs(row["distance_from_ma20"]) <= 0.02
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_universe_api_mutates_config_with_normalized_deduped_tickers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir()
    universe_path.write_text(
        yaml.safe_dump({"groups": {"core": ["spy", "SPY", "btc-usd"]}}, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    client = TestClient(app)

    response = client.get("/universes")
    assert response.status_code == 200
    assert response.json()["groups"]["core"] == ["SPY", "BTC-USD"]
    assert response.json()["editable"] is False

    response = client.put(
        "/universes/watch",
        json={"tickers": ["aapl"]},
    )
    assert response.status_code == 403

    monkeypatch.setattr(services, "MARKET_DATA_UNIVERSE_EDITABLE", True)

    response = client.get("/universes")
    assert response.status_code == 200
    assert response.json()["editable"] is True

    response = client.put(
        "/universes/watch",
        json={"tickers": ["aapl", "AAPL", "btc-usd", "brk.b"]},
    )
    assert response.status_code == 200
    assert response.json()["tickers"] == ["AAPL", "BTC-USD", "BRK.B"]

    response = client.post(
        "/universes/watch/tickers",
        json={"tickers": ["msft", "BTC-USD"]},
    )
    assert response.status_code == 200
    assert response.json()["tickers"] == ["AAPL", "BTC-USD", "BRK.B", "MSFT"]

    response = client.delete("/universes/watch/tickers/BTC-USD")
    assert response.status_code == 200
    assert response.json()["tickers"] == ["AAPL", "BRK.B", "MSFT"]

    response = client.delete("/universes/watch")
    assert response.status_code == 200
    assert "watch" not in response.json()["groups"]

    saved = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    assert saved["groups"]["core"] == ["SPY", "BTC-USD"]
    assert "watch" not in saved["groups"]
    assert "NaN" not in json.dumps(response.json(), allow_nan=False)


def moomoo_export_payload() -> dict:
    return {
        "source": "moomoo-account-web",
        "status": "ok",
        "synced_at": "2026-06-08T00:00:00+00:00",
        "market": "US",
        "positions_status": "ok",
        "watchlists_status": "ok",
        "items": [
            {
                "code": "US.NVDA",
                "name": "NVIDIA",
                "market_data_ticker": "NVDA",
                "mapping_status": "mapped",
                "held": True,
                "universe_order": 0,
                "watchlist_refs": [
                    {"group_name": "AI Watch", "group_order": 1, "security_order": 1},
                ],
                "sources": ["positions", "watchlist:AI Watch"],
            },
            {
                "code": "HK.00700",
                "name": "Tencent",
                "market_data_ticker": "0700.HK",
                "mapping_status": "mapped",
                "held": False,
                "universe_order": 1,
                "watchlist_refs": [
                    {"group_name": "AI Watch", "group_order": 1, "security_order": 0},
                    {"group_name": "Hong Kong", "group_order": 0, "security_order": 0},
                ],
                "sources": ["watchlist:AI Watch", "watchlist:Hong Kong"],
            },
            {
                "code": "US.NVDA",
                "name": "NVIDIA duplicate",
                "market_data_ticker": "NVDA",
                "mapping_status": "mapped",
                "held": False,
                "universe_order": 2,
                "watchlist_refs": [
                    {"group_name": "AI Watch", "group_order": 1, "security_order": 1},
                ],
                "sources": ["watchlist:AI Watch"],
            },
            {
                "code": "AU.BHP",
                "name": "BHP",
                "market_data_ticker": None,
                "mapping_status": "unsupported",
                "held": False,
                "sources": ["watchlist:Australia"],
            },
            {
                "code": "BAD",
                "name": "Bad",
                "market_data_ticker": "BAD/TICKER",
                "mapping_status": "mapped",
                "held": False,
                "sources": ["watchlist:Bad"],
            },
        ],
    }


def test_moomoo_export_builds_universe_groups_with_skipped_items() -> None:
    result = build_universe_from_export(moomoo_export_payload())

    assert result["status"] == "ok"
    assert result["mapped_count"] == 3
    assert result["unsupported_count"] == 1
    assert result["invalid_count"] == 1
    assert "moomoo_all" not in result["groups"]
    assert result["groups"]["moomoo_positions"] == ["NVDA"]
    assert list(result["groups"])[:3] == [
        "moomoo_positions",
        "moomoo_watchlist_hong_kong",
        "moomoo_watchlist_ai_watch",
    ]
    assert result["groups"]["moomoo_watchlist_ai_watch"] == ["0700.HK", "NVDA"]
    assert result["groups"]["moomoo_watchlist_hong_kong"] == ["0700.HK"]
    assert result["group_meta"]["moomoo_watchlist_ai_watch"]["label"] == "Moomoo Watchlist: AI Watch"
    assert result["group_meta"]["moomoo_watchlist_hong_kong"]["group_order"] == 0
    assert result["group_meta"]["moomoo_watchlist_ai_watch"]["group_order"] == 1
    assert [item["reason"] for item in result["skipped_items"]] == ["unsupported", "invalid_ticker"]
    assert "NaN" not in json.dumps(result, allow_nan=False)


def test_watchlist_sync_only_allows_universe_to_firn(tmp_path: Path) -> None:
    universe_path = tmp_path / "market-data-lab" / "config" / "universe.yaml"
    watchlist_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    watchlist_path.parent.mkdir(parents=True)
    universe_path.parent.mkdir(parents=True)
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "categories": {
                    "semiconductors": {
                        "label": "Semiconductors",
                        "tags": ["semiconductors", "ai-hardware"],
                        "tickers": ["nvda", "NVDA", "mrvl"],
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    universe_path.write_text(
        yaml.safe_dump(
            {
                "groups": {
                    "semiconductors": ["nvda", "NVDA", "avgo"],
                },
                "group_meta": {
                    "semiconductors": {
                        "label": "Semiconductors",
                        "tags": ["semiconductors", "ai-hardware"],
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        sync_configs(prefer="watchlist", universe_path=universe_path, watchlist_path=watchlist_path)

    with pytest.raises(ValueError):
        sync_configs(prefer="newer", universe_path=universe_path, watchlist_path=watchlist_path)

    winner = sync_configs(
        prefer="universe",
        universe_path=universe_path,
        watchlist_path=watchlist_path,
    )

    assert winner == "universe"
    universe = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    assert universe["groups"]["semiconductors"] == ["nvda", "NVDA", "avgo"]
    watchlist = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    assert watchlist["categories"]["semiconductors"]["tickers"] == ["NVDA", "AVGO"]
    assert watchlist["categories"]["semiconductors"]["tags"] == ["semiconductors", "ai-hardware"]


def test_moomoo_preview_does_not_write_configs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    firn_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    universe_path.parent.mkdir(parents=True)
    firn_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    firn_path.write_text(yaml.safe_dump({"categories": {"old": {"tickers": ["OLD"]}}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", firn_path)
    monkeypatch.setattr(services, "preview_research_universe", lambda **kwargs: build_universe_from_export(moomoo_export_payload()))

    result = services.preview_moomoo_research_universe()

    assert "moomoo_all" not in result["groups"]
    assert result["groups"]["moomoo_watchlist_ai_watch"] == ["0700.HK", "NVDA"]
    assert yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"] == {"old": ["OLD"]}
    assert yaml.safe_load(firn_path.read_text(encoding="utf-8"))["categories"]["old"]["tickers"] == ["OLD"]


def test_moomoo_sync_replaces_lab_universe_and_pushes_firn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    firn_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    universe_path.parent.mkdir(parents=True)
    firn_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    firn_path.write_text(yaml.safe_dump({"categories": {"old": {"tickers": ["OLD"]}}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", firn_path)
    monkeypatch.setattr(services, "preview_research_universe", lambda **kwargs: build_universe_from_export(moomoo_export_payload()))

    result = services.sync_moomoo_research_universe()

    saved = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    assert result["synced"] is True
    assert result["firn_synced"] is True
    assert set(saved["groups"]) == {
        "moomoo_positions",
        "moomoo_watchlist_ai_watch",
        "moomoo_watchlist_hong_kong",
    }
    assert saved["groups"]["moomoo_watchlist_ai_watch"] == ["0700.HK", "NVDA"]
    assert "old" not in saved["groups"]
    watchlist = yaml.safe_load(firn_path.read_text(encoding="utf-8"))
    assert "moomoo_all" not in watchlist["categories"]
    assert watchlist["categories"]["moomoo_positions"]["tickers"] == ["NVDA"]


def test_moomoo_sync_error_does_not_write_configs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    firn_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    universe_path.parent.mkdir(parents=True)
    firn_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    firn_path.write_text(yaml.safe_dump({"categories": {"old": {"tickers": ["OLD"]}}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", firn_path)

    def fail_preview(**kwargs):
        raise TimeoutError("moomoo unavailable")

    monkeypatch.setattr(services, "preview_research_universe", fail_preview)

    with pytest.raises(TimeoutError):
        services.sync_moomoo_research_universe()

    assert yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"] == {"old": ["OLD"]}
    assert yaml.safe_load(firn_path.read_text(encoding="utf-8"))["categories"]["old"]["tickers"] == ["OLD"]


def test_moomoo_sync_requires_firn_path_before_writing_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", None)
    monkeypatch.setattr(
        services,
        "preview_research_universe",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("moomoo should not be called")),
    )

    with pytest.raises(ValueError, match="FIRN_WATCHLIST_PATH"):
        services.sync_moomoo_research_universe(sync_firn=True)

    assert yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"] == {"old": ["OLD"]}


def test_refresh_api_writes_lists_and_gets_run_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("BSX", generated_frame())
    run_dir = tmp_path / "runs" / "refresh"
    monkeypatch.setattr(services, "REFRESH_RUN_DIR", run_dir)
    monkeypatch.setattr(services, "ensure_data_dirs", lambda: None)

    def fake_fetcher(ticker: str, **kwargs):
        if ticker == "AAPL":
            return generated_frame()
        raise RuntimeError("provider down")

    monkeypatch.setattr(services, "_fetcher", lambda: fake_fetcher)
    client = TestClient(app)

    response = client.post(
        "/refresh",
        json={"tickers": ["AAPL", "BSX", "MRK"], "period": "1mo", "force": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    files = list(run_dir.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["period"] == "1mo"
    assert saved["source"] == "fake_fetcher"
    assert saved["requested_tickers"] == ["AAPL", "BSX", "MRK"]
    assert saved["success"] == 1
    assert saved["fail"] == 1
    assert saved["stale"] == 1
    assert saved["per_ticker"] == saved["results"]
    assert [(item["ticker"], item["status"]) for item in saved["results"]] == [
        ("AAPL", "ok"),
        ("BSX", "stale"),
        ("MRK", "unavailable"),
    ]
    assert saved["results"][0]["rows"] == 260
    assert saved["results"][0]["as_of"] == "2026-06-05"
    assert saved["results"][1]["error"] == "provider down"
    assert "NaN" not in json.dumps(saved, allow_nan=False)

    list_response = client.get("/runs/refresh")
    assert list_response.status_code == 200
    runs = list_response.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == saved["run_id"]
    assert runs[0]["success"] == 1
    assert runs[0]["fail"] == 1
    assert runs[0]["stale"] == 1

    get_response = client.get(f"/runs/refresh/{saved['run_id']}")
    assert get_response.status_code == 200
    assert get_response.json() == saved
    assert "NaN" not in json.dumps(get_response.json(), allow_nan=False)


def test_history_output_cleans_non_json_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    frame = standard_frame(["2026-06-04", "2026-06-05"], closes=[10.0, 11.0])
    frame.loc[1, "dividends"] = float("inf")
    frame.loc[1, "currency"] = pd.NA
    store.write("BSX", frame)
    client = TestClient(app)

    response = client.get("/history/BSX")

    assert response.status_code == 200
    data = response.json()
    assert data["rows"][1]["dividends"] is None
    assert data["rows"][1]["currency"] is None
    assert "NaN" not in json.dumps(data, allow_nan=False)


def test_get_api_endpoints_do_not_call_fetcher(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = isolated_store(monkeypatch, tmp_path)
    store.write("BSX", generated_frame())
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    run_dir = tmp_path / "runs" / "refresh"
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir()
    universe_path.write_text(yaml.safe_dump({"groups": {"core": ["BSX"]}}), encoding="utf-8")
    original_universe = universe_path.read_text(encoding="utf-8")
    monkeypatch.setattr(services, "SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(services, "REFRESH_RUN_DIR", run_dir)
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "_fetcher", fail_if_fetcher_called)
    monkeypatch.setattr(
        services,
        "preview_research_universe",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("ordinary GET endpoints must not call moomoo")),
    )
    client = TestClient(app)

    responses = [
        client.get("/health"),
        client.get("/status"),
        client.get("/quality"),
        client.get("/screen?tickers=BSX"),
        client.get("/universes"),
        client.get("/runs/refresh"),
        client.get("/history/BSX"),
        client.get("/snapshot/BSX"),
        client.get("/chart/BSX"),
        client.get("/snapshots?tickers=BSX,AAPL&limit=2&benchmark=SPY"),
    ]

    assert [response.status_code for response in responses] == [200] * 10
    assert universe_path.read_text(encoding="utf-8") == original_universe


def test_moomoo_api_preview_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    firn_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    universe_path.parent.mkdir(parents=True)
    firn_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    firn_path.write_text(yaml.safe_dump({"categories": {"old": {"tickers": ["OLD"]}}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", firn_path)
    monkeypatch.setattr(services, "preview_research_universe", lambda **kwargs: build_universe_from_export(moomoo_export_payload()))
    client = TestClient(app)

    response = client.get("/integrations/moomoo/research-universe/preview")
    assert response.status_code == 200
    preview_payload = response.json()
    assert "moomoo_all" not in preview_payload["groups"]
    assert preview_payload["groups"]["moomoo_watchlist_ai_watch"] == ["0700.HK", "NVDA"]
    assert yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"] == {"old": ["OLD"]}

    response = client.post("/integrations/moomoo/research-universe/sync", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["firn_synced"] is True
    saved_groups = yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"]
    assert "moomoo_all" not in saved_groups
    assert saved_groups["moomoo_watchlist_ai_watch"] == ["0700.HK", "NVDA"]
    firn_categories = yaml.safe_load(firn_path.read_text(encoding="utf-8"))["categories"]
    assert "moomoo_all" not in firn_categories
    assert firn_categories["moomoo_watchlist_ai_watch"]["tickers"] == ["0700.HK", "NVDA"]


def test_moomoo_api_unavailable_returns_503_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    universe_path = tmp_path / "config" / "universe.yaml"
    firn_path = tmp_path / "global-market-agent" / "config" / "digest_watchlist.yaml"
    universe_path.parent.mkdir(parents=True)
    firn_path.parent.mkdir(parents=True)
    universe_path.write_text(yaml.safe_dump({"groups": {"old": ["OLD"]}}), encoding="utf-8")
    firn_path.write_text(yaml.safe_dump({"categories": {"old": {"tickers": ["OLD"]}}}), encoding="utf-8")
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(services, "DEFAULT_FIRN_WATCHLIST_PATH", firn_path)
    monkeypatch.setattr(
        services,
        "preview_research_universe",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError("moomoo unavailable")),
    )
    client = TestClient(app)

    response = client.post("/integrations/moomoo/research-universe/sync", json={})

    assert response.status_code == 503
    assert yaml.safe_load(universe_path.read_text(encoding="utf-8"))["groups"] == {"old": ["OLD"]}
    assert yaml.safe_load(firn_path.read_text(encoding="utf-8"))["categories"]["old"]["tickers"] == ["OLD"]


def test_cli_refresh_universe_reads_config_and_dedupes_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_refresh_history(tickers, *, period, force):
        captured["tickers"] = tickers
        return RefreshResponse(
            status="complete",
            total=len(tickers),
            succeeded=len(tickers),
            failed=0,
            results=[
                RefreshTickerResult(ticker=ticker, status="ok", rows=1, as_of="2026-06-05")
                for ticker in tickers
            ],
        )

    monkeypatch.setattr(cli, "refresh_history", fake_refresh_history)
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir()
    universe_path.write_text(
        yaml.safe_dump({"groups": {"healthcare": ["bsx", "MRK", "UNH", "VRTX", "ISRG"]}}, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(sys, "argv", ["market-data", "refresh", "--universe", "healthcare", "BSX"])

    cli.main()

    assert captured["tickers"] == ["BSX", "MRK", "UNH", "VRTX", "ISRG"]
    assert "Refresh complete" in capsys.readouterr().out


def test_cli_refresh_all_reads_every_universe_group_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_refresh_history(tickers, *, period, force):
        captured["tickers"] = tickers
        return RefreshResponse(
            status="complete",
            total=len(tickers),
            succeeded=len(tickers),
            failed=0,
            results=[
                RefreshTickerResult(ticker=ticker, status="ok", rows=1, as_of="2026-06-05")
                for ticker in tickers
            ],
        )

    monkeypatch.setattr(cli, "refresh_history", fake_refresh_history)
    universe_path = tmp_path / "config" / "universe.yaml"
    universe_path.parent.mkdir()
    universe_path.write_text(
        yaml.safe_dump(
            {
                "groups": {
                    "indices": ["SPY", "QQQ", "IWM"],
                    "growth": ["AAPL", "NFLX", "QQQ"],
                    "themes": ["SMH", "RKLB"],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "UNIVERSE_PATH", universe_path)
    monkeypatch.setattr(sys, "argv", ["market-data", "refresh", "--all"])

    cli.main()

    tickers = captured["tickers"]
    assert tickers[:3] == ["SPY", "QQQ", "IWM"]
    assert "AAPL" in tickers
    assert "NFLX" in tickers
    assert "SMH" in tickers
    assert "RKLB" in tickers
    assert tickers.count("SPY") == 1
    assert "Refresh complete" in capsys.readouterr().out


def test_cli_status_verbose_passes_verbose_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, bool] = {}

    def fake_status_summary(*, verbose: bool):
        captured["verbose"] = verbose
        payload = {
            "status": "ok",
            "cached_tickers": ["BSX"],
            "cached_ticker_count": 1,
        }
        if verbose:
            payload["entries"] = [{"ticker": "BSX"}]
        return payload

    monkeypatch.setattr(cli, "status_summary", fake_status_summary)
    monkeypatch.setattr(sys, "argv", ["market-data", "status", "--verbose"])

    cli.main()

    assert captured["verbose"] is True
    assert json.loads(capsys.readouterr().out)["entries"] == [{"ticker": "BSX"}]


def test_cli_quality_prints_compact_readable_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, bool] = {}

    def fake_status_summary(*, verbose: bool):
        captured["verbose"] = verbose
        return {
            "cache_status": "partial",
            "cached_ticker_count": 2,
            "latest_as_of": "2026-06-05",
            "last_refresh": "2026-06-06T00:00:00+00:00",
            "stale_count": 1,
            "unavailable_count": 0,
            "data_quality": {
                "status": "partial",
                "issue_count": 2,
            },
            "data_quality_report": {
                "missing_price": {
                    "count": 1,
                    "tickers": ["BSX"],
                    "details": [
                        {
                            "ticker": "BSX",
                            "message": "1 cached rows have no close price",
                        }
                    ],
                },
                "stale_data": {
                    "count": 1,
                    "tickers": ["MRK"],
                    "details": [
                        {
                            "ticker": "MRK",
                            "message": "latest cached date is 8 days old",
                        }
                    ],
                },
                "missing_volume": {
                    "count": 0,
                    "tickers": [],
                    "details": [],
                },
            },
        }

    monkeypatch.setattr(cli, "status_summary", fake_status_summary)
    monkeypatch.setattr(sys, "argv", ["market-data", "quality"])

    cli.main()

    output = capsys.readouterr().out
    assert captured["verbose"] is True
    assert "Market data quality: partial (2 issues)" in output
    assert "Cached tickers: 2 | latest as-of: 2026-06-05 | last refresh: 2026-06-06T00:00:00+00:00" in output
    assert "- Missing Price: 1 (BSX)" in output
    assert "BSX: 1 cached rows have no close price" in output
    assert "- Stale Data: 1 (MRK)" in output
    assert "MRK: latest cached date is 8 days old" in output
    assert "Missing Volume" not in output


def test_cli_moomoo_preview_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview_calls: list[dict] = []
    sync_calls: list[dict] = []
    result = build_universe_from_export(moomoo_export_payload())

    def fake_preview(**kwargs):
        preview_calls.append(kwargs)
        return result

    def fake_sync(**kwargs):
        sync_calls.append(kwargs)
        return {
            **result,
            "synced": True,
            "universe_path": "/tmp/universe.yaml",
            "firn_synced": kwargs["sync_firn"],
        }

    monkeypatch.setattr(cli, "preview_moomoo_research_universe", fake_preview)
    monkeypatch.setattr(cli, "sync_moomoo_research_universe", fake_sync)

    monkeypatch.setattr(sys, "argv", ["market-data", "moomoo-preview", "--market", "US"])
    cli.main()
    preview_output = capsys.readouterr().out
    assert preview_calls[0]["market"] == "US"
    assert "Moomoo preview: ok" in preview_output
    assert "moomoo_watchlist_ai_watch: 2" in preview_output
    assert "moomoo_all" not in preview_output

    monkeypatch.setattr(sys, "argv", ["market-data", "moomoo-sync", "--no-firn"])
    cli.main()
    sync_output = capsys.readouterr().out
    assert sync_calls[0]["sync_firn"] is False
    assert "Moomoo sync: ok" in sync_output
    assert "firn_synced=False" in sync_output


def test_refresh_daily_script_exists_with_safe_refresh_workflow() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_daily.sh"
    script = path.read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    assert 'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"' in script
    assert 'ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"' in script
    assert "uv run market-data moomoo-sync" in script
    assert "uv run market-data refresh --all --period 5y" in script
    assert "uv run market-data status --verbose" in script
    assert "uv run market-data quality" in script
    assert path.stat().st_mode & 0o111


def test_universe_config_has_moomoo_groups_and_metadata() -> None:
    data = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "universe.yaml").read_text())
    groups = data["groups"]

    assert "moomoo_all" not in groups
    assert "moomoo_positions" in groups
    assert set(groups) == set(data["group_meta"])
    configured = {ticker for tickers in groups.values() for ticker in tickers}
    for ticker in {"AAPL", "MSFT", "NVDA", "BSX", "AVGO"}:
        assert ticker in configured
    assert set(groups["moomoo_positions"]).issubset(configured)
    assert data["group_meta"]["moomoo_positions"]["label"] == "Moomoo Positions"
