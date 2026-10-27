"""Tool implementations.

Importing this package registers every tool via ``miro_mcp.registry.tool``.
Each module groups one REST resource area; implementations take a
``MiroClient`` as their first argument and return JSON-serializable dicts.
"""

from . import boards, items, members, misc  # noqa: F401
