"""Async HTTP client for the Miro REST API v2.

Auth: the bearer token is resolved from the MIRO_ACCESS_TOKEN environment
variable, or from the dotenv-style file at MIRO_ENV_FILE
(default ~/.config/miro-mcp/miro.env). The token is never logged.

Resilience: 429 responses are retried honoring Retry-After, with an adaptive
exponential backoff that grows on consecutive throttled requests and resets on
success. 502/503/504 are retried with plain exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx

log = logging.getLogger("miro_mcp")

MIRO_API_BASE = "https://api.miro.com"
DEFAULT_ENV_FILE = "~/.config/miro-mcp/miro.env"

MAX_RETRIES = 5
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0

RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

# Header names Miro or intermediaries may use to report rate-limit state.
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-miro-rate-limit-remaining",
    "x-credits-remaining",
)


class MiroError(RuntimeError):
    """Base error raised by miro-mcp."""


class MiroAuthError(MiroError):
    """The access token could not be resolved."""


class MiroApiError(MiroError):
    """A non-retryable API error."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Miro API error {status}: {message}")


class MiroRateLimitError(MiroApiError):
    """429 persisted after all retries."""


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def load_token(env_file: str | None = None) -> str:
    """Resolve MIRO_ACCESS_TOKEN from the environment or the env file."""
    token = os.environ.get("MIRO_ACCESS_TOKEN")
    if token:
        return token
    path = Path(
        env_file or os.environ.get("MIRO_ENV_FILE") or DEFAULT_ENV_FILE
    ).expanduser()
    if not path.is_file():
        raise MiroAuthError(
            f"No MIRO_ACCESS_TOKEN in environment and env file not found: {path}. "
            "Create it with a line 'MIRO_ACCESS_TOKEN=<token>' or set MIRO_ENV_FILE."
        )
    token = _parse_env_file(path).get("MIRO_ACCESS_TOKEN")
    if not token:
        raise MiroAuthError(f"MIRO_ACCESS_TOKEN not set in {path}")
    return token


class MiroClient:
    """Thin async wrapper over the Miro REST API v2."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = MIRO_API_BASE,
        timeout: float = 30.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        #: Rate-limit headers observed on the most recent response, if any.
        self.rate_limit: dict[str, str] = {}
        self._rl_strikes = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    def _capture_rate_headers(self, resp: httpx.Response) -> None:
        self.rate_limit = {
            h: resp.headers[h] for h in RATE_LIMIT_HEADERS if h in resp.headers
        }

    @staticmethod
    def _error_message(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict):
                msg = str(body.get("message") or body.get("error") or resp.text[:500])
                fields = (body.get("context") or {}).get("fields") or []
                details = "; ".join(
                    f"{f.get('field')}: {f.get('message')}"
                    for f in fields
                    if isinstance(f, dict)
                )
                return f"{msg} ({details})" if details else msg
        except Exception:
            pass
        return resp.text[:500] or resp.reason_phrase

    def _throttle_delay(self, resp: httpx.Response) -> float:
        """Adaptive backoff: Retry-After wins, else 2^strikes with a cap."""
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), BACKOFF_MAX_S)
            except ValueError:
                pass
        return float(min(BACKOFF_BASE_S * (2**self._rl_strikes), BACKOFF_MAX_S))

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request, retrying 429/502/503/504 per backoff rules."""
        attempt = 0
        while True:
            resp = await self._http.request(
                method, path, params=params, json=json_body, files=files
            )
            self._capture_rate_headers(resp)
            status = resp.status_code
            if status in RETRYABLE_STATUSES:
                if attempt >= MAX_RETRIES:
                    if status == 429:
                        raise MiroRateLimitError(429, self._error_message(resp))
                    raise MiroApiError(status, self._error_message(resp))
                attempt += 1
                if status == 429:
                    self._rl_strikes += 1
                    delay = self._throttle_delay(resp)
                else:
                    delay = float(min(BACKOFF_BASE_S * attempt, BACKOFF_MAX_S))
                log.warning(
                    "Miro %d; retry %d/%d in %.2fs",
                    status,
                    attempt,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            self._rl_strikes = 0
            if status >= 400:
                raise MiroApiError(status, self._error_message(resp))
            if status == 204 or not resp.content:
                return {}
            return resp.json()

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(dict[str, Any], await self.request("GET", path, params=params))

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.request(
                "POST", path, params=params, json_body=json_body, files=files
            ),
        )

    async def put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.request("PUT", path, params=params, json_body=json_body),
        )

    async def patch(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.request("PATCH", path, params=params, json_body=json_body),
        )

    async def delete(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(dict[str, Any], await self.request("DELETE", path, params=params))

    async def iter_cursor(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield items from a Miro cursor-paginated endpoint.

        Pages are shaped ``{"data": [...], "cursor": "..."}``; iteration stops
        when the response carries no cursor or ``max_pages`` is reached.
        """
        p = dict(params or {})
        cursor = p.pop("cursor", None)
        pages = 0
        while True:
            if cursor:
                p["cursor"] = cursor
            page = await self.get(path, params=p)
            pages += 1
            data = page.get("data") or []
            for item in data:
                yield item
            cursor = page.get("cursor")
            if not cursor or (max_pages is not None and pages >= max_pages):
                return

    async def iter_offset(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = 20,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield items from a Miro offset-paginated endpoint.

        Pages are shaped ``{"data": [...], "total": n, "offset": n}``; iteration
        stops on an empty page, when ``total`` is reached, or ``max_pages``.
        """
        p = dict(params or {})
        offset = int(p.pop("offset", 0) or 0)
        p.setdefault("limit", limit)
        pages = 0
        while True:
            p["offset"] = str(offset)
            page = await self.get(path, params=p)
            pages += 1
            data = page.get("data") or []
            for item in data:
                yield item
            offset += len(data)
            total = page.get("total")
            if (
                not data
                or (total is not None and offset >= int(total))
                or (max_pages is not None and pages >= max_pages)
            ):
                return
