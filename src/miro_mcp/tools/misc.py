"""Miscellaneous account/token tools."""

from __future__ import annotations

from typing import Any

from ..client import MiroClient
from ..registry import ESSENTIAL, tool


@tool(profile=ESSENTIAL)
async def whoami(client: MiroClient) -> dict[str, Any]:
    """Show the context of the current access token.

    Returns the token type, the user the token belongs to, the team it was
    installed on, and the granted scopes. Useful to verify auth before other
    calls. Requires no board.
    """
    return await client.get("/v1/oauth-token")
