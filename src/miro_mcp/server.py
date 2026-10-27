"""FastMCP server: profile selection, client injection, stdio transport."""

from __future__ import annotations

import inspect
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools as _tools_pkg  # noqa: F401 — import registers all tools
from .client import MiroClient, load_token
from .registry import PROFILES, TOOLS, ToolSpec

log = logging.getLogger("miro_mcp")

mcp: FastMCP = FastMCP(
    "miro-mcp",
    instructions=(
        "Miro REST API v2 server. Destructive tools (delete_*, remove_*, "
        "share/update member) require confirm=true or they return a "
        "confirmation_required error without acting."
    ),
)

_client: MiroClient | None = None


def get_client() -> MiroClient:
    """Lazily resolve the token and build the shared client."""
    global _client
    if _client is None:
        _client = MiroClient(load_token())
    return _client


def _make_wrapper(spec: ToolSpec) -> Any:
    """Wrap an impl so ``client`` is injected and rate-limit info is appended.

    ``__signature__`` hides the ``client`` parameter from the MCP tool schema.
    """
    impl = spec.fn
    sig = inspect.signature(impl)
    params = [p for p in sig.parameters.values() if p.name != "client"]

    async def wrapper(**kwargs: Any) -> Any:
        client = get_client()
        result = await impl(client, **kwargs)
        if isinstance(result, dict) and client.rate_limit:
            result = {**result, "rate_limit": dict(client.rate_limit)}
        return result

    wrapper.__name__ = spec.name
    wrapper.__doc__ = impl.__doc__
    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
    return wrapper


def install_tools(profile: str = "full") -> int:
    """Register tools on the FastMCP app for the given profile."""
    allowed = PROFILES.get(profile)
    if allowed is None:
        raise ValueError(
            f"unknown MIRO_MCP_PROFILE {profile!r}; expected one of {sorted(PROFILES)}"
        )
    count = 0
    for spec in TOOLS.values():
        if spec.profile not in allowed:
            continue
        mcp.add_tool(_make_wrapper(spec), name=spec.name)
        count += 1
    return count


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MIRO_MCP_LOG", "INFO").upper(),
        stream=sys.stderr,  # stdio transport: stdout is reserved for JSON-RPC
    )
    profile = os.environ.get("MIRO_MCP_PROFILE", "full").strip().lower() or "full"
    count = install_tools(profile)
    log.info("miro-mcp starting: profile=%s tools=%d", profile, count)
    mcp.run(transport="stdio")
