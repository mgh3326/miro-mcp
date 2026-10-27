"""Tool implementations.

Importing this package registers every tool via ``miro_mcp.registry.tool``.
Each module groups one REST resource area; implementations take a
``MiroClient`` as their first argument and return JSON-serializable dicts.
"""

from . import (  # noqa: F401
    boards,
    connectors,
    docs,
    export,
    groups,
    items,
    members,
    mindmap,
    misc,
    tags,
)
