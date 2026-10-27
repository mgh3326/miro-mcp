"""Groups: create, list, get, get items, replace items, ungroup, delete."""

from __future__ import annotations

import logging
from typing import Any

from ..client import MiroClient
from ..registry import tool
from .common import cursor_result, require_confirm

log = logging.getLogger("miro_mcp")


@tool()
async def create_group(
    client: MiroClient, board_id: str, item_ids: list[str]
) -> dict[str, Any]:
    """Group items together. ``item_ids`` are the items to group."""
    return await client.post(
        f"/v2/boards/{board_id}/groups",
        json_body={"data": {"items": item_ids}},
    )


@tool()
async def list_groups(
    client: MiroClient,
    board_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List all groups on a board (cursor-paginated)."""
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(f"/v2/boards/{board_id}/groups", params=params)
    return cursor_result(page, compact=False)


@tool()
async def get_group(client: MiroClient, board_id: str, group_id: str) -> dict[str, Any]:
    """Get one group with the items it contains."""
    return await client.get(f"/v2/boards/{board_id}/groups/{group_id}")


@tool()
async def get_group_items(
    client: MiroClient,
    board_id: str,
    group_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List the items that belong to a group (cursor-paginated)."""
    params = {"group_item_id": group_id, "limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(f"/v2/boards/{board_id}/groups/items", params=params)
    return cursor_result(page, compact=False)


@tool()
async def update_group(
    client: MiroClient, board_id: str, group_id: str, item_ids: list[str]
) -> dict[str, Any]:
    """Replace a group's membership entirely with a new set of items.

    A new group id is assigned by Miro on update.
    """
    return await client.put(
        f"/v2/boards/{board_id}/groups/{group_id}",
        json_body={"data": {"items": item_ids}},
    )


@tool(destructive=True)
async def ungroup(
    client: MiroClient, board_id: str, group_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Dissolve a group (items stay on the board). Requires
    ``confirm=true``."""
    if blocked := require_confirm(confirm, f"ungroup {group_id}"):
        return blocked
    await client.delete(f"/v2/boards/{board_id}/groups/{group_id}")
    return {"ungrouped": group_id}
