"""Tool registry and profile metadata.

Tool implementations are plain async functions whose first parameter is a
``MiroClient``. The ``@tool`` decorator records them in ``TOOLS``; the server
installs them on the FastMCP app, filtering by the active profile.

Profiles:
- ``full`` — every registered tool.
- ``essential`` — only tools marked ``profile="essential"`` (a small
  read/create subset that keeps the tool list cheap for the client model).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

ToolFn = Callable[..., Awaitable[dict[str, Any]]]
Profile = Literal["essential", "full"]

ESSENTIAL: Profile = "essential"
FULL: Profile = "full"

#: Profile name -> set of tool profiles it includes.
PROFILES: dict[str, frozenset[str]] = {
    ESSENTIAL: frozenset({ESSENTIAL}),
    FULL: frozenset({ESSENTIAL, FULL}),
}


@dataclass(frozen=True)
class ToolSpec:
    fn: ToolFn
    name: str
    profile: Profile
    destructive: bool


TOOLS: dict[str, ToolSpec] = {}


def tool(
    *,
    profile: Profile = FULL,
    destructive: bool = False,
    name: str | None = None,
) -> Callable[[ToolFn], ToolFn]:
    """Register an async tool implementation.

    ``destructive`` marks tools that delete or change sharing state; those
    implementations must take a ``confirm`` argument and gate on it.
    """

    def decorate(fn: ToolFn) -> ToolFn:
        TOOLS[name or fn.__name__] = ToolSpec(
            fn=fn,
            name=name or fn.__name__,
            profile=profile,
            destructive=destructive,
        )
        return fn

    return decorate
