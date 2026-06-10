"""HTTP adapter for Firn watchlist sync."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any


WATCHLIST_PATH = "api/config/watchlist"


class FirnSyncError(RuntimeError):
    """Raised when Firn rejects or cannot process a watchlist sync."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def watchlist_endpoint(base_url: str) -> str:
    """Return the Firn watchlist endpoint for a base URL."""

    return f"{base_url.rstrip('/')}/{WATCHLIST_PATH}"


def put_watchlist(
    *,
    base_url: str,
    categories: dict[str, dict[str, Any]],
    token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Send a normalized watchlist payload to Firn."""

    payload = json.dumps({"categories": categories}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "market-data-lab/firn-watchlist-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        watchlist_endpoint(base_url),
        data=payload,
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset("utf-8")
            body = response.read().decode(charset)
            if not body.strip():
                return {"status": "ok"}
            decoded = json.loads(body)
            if not isinstance(decoded, dict):
                raise FirnSyncError("Firn watchlist response must be a JSON object")
            return decoded
    except urllib.error.HTTPError as exc:
        detail = _read_error_detail(exc)
        message = f"Firn watchlist sync failed with HTTP {exc.code}"
        if detail:
            message = f"{message}: {detail}"
        raise FirnSyncError(message, status_code=exc.code) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise FirnSyncError(f"Firn watchlist sync request failed: {exc}") from None
    except json.JSONDecodeError as exc:
        raise FirnSyncError(f"Firn watchlist response was not valid JSON: {exc}") from None


def _read_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    if not body.strip():
        return ""
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()
    detail = decoded.get("detail") if isinstance(decoded, dict) else decoded
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False)
