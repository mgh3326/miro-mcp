"""Async HTTP client for the Miro REST API v2.

Auth: the bearer token is resolved from the MIRO_ACCESS_TOKEN environment
variable, or from the dotenv-style file at MIRO_ENV_FILE
(default ~/.config/miro-mcp/miro.env). The token is never logged.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("miro_mcp")

MIRO_API_BASE = "https://api.miro.com"
DEFAULT_ENV_FILE = "~/.config/miro-mcp/miro.env"

MAX_RETRIES = 4
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0

# Header names Miro or intermediaries may use to report remaining credits.
RATE_LIMIT_HEADERS = (
    "x-miro-rate-limit-remaining",
    "x-ratelimit-remaining",
    "x-rate-limit-remaining",
    "x-credits-remaining",
)


class MiroError(RuntimeError):
    """Base error raised by miro-mcp-lite."""


class MiroAuthError(MiroError):
    """The access token could not be resolved."""


class MiroApiError(MiroError):
    """A non-429 API error."""

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
                return str(body.get("message") or body.get("error") or resp.text[:500])
        except Exception:
            pass
        return resp.text[:500] or resp.reason_phrase

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), BACKOFF_MAX_S)
            except ValueError:
                pass
        return float(min(BACKOFF_BASE_S * (2 ** (attempt - 1)), BACKOFF_MAX_S))

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request, retrying 429s per Retry-After / exponential backoff."""
        attempt = 0
        while True:
            resp = await self._http.request(
                method, path, params=params, json=json_body, files=files
            )
            self._capture_rate_headers(resp)
            if resp.status_code == 429:
                if attempt >= MAX_RETRIES:
                    raise MiroRateLimitError(429, self._error_message(resp))
                attempt += 1
                delay = self._retry_delay(resp, attempt)
                log.warning(
                    "Miro rate limit (429); retry %d/%d in %.2fs",
                    attempt,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise MiroApiError(resp.status_code, self._error_message(resp))
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
