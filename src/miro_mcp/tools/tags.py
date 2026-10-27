"""Tags: board tag CRUD, attach/detach on items, item tag listing."""

from __future__ import annotations

import logging
from typing import Any

from ..client import MiroClient
from ..registry import ESSENTIAL, tool
from .common import cursor_result, drop_none, require_confirm

log = logging.getLogger("miro_mcp")


@tool()
async def list_tags(
    client: MiroClient,
    board_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List all tags on a board (cursor-paginated)."""
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(f"/v2/boards/{board_id}/tags", params=params)
    return cursor_result(page, compact=False)


@tool()
async def create_tag(
    client: MiroClient,
    board_id: str,
    title: str,
    fill_color: str | None = None,
) -> dict[str, Any]:
    """Create a tag. ``fill_color`` is a hex string like ``#24716f``."""
    return await client.post(
        f"/v2/boards/{board_id}/tags",
        json_body=drop_none({"title": title, "fillColor": fill_color}),
    )


@tool()
async def get_tag(client: MiroClient, board_id: str, tag_id: str) -> dict[str, Any]:
    """Get one tag."""
    return await client.get(f"/v2/boards/{board_id}/tags/{tag_id}")


@tool()
async def update_tag(
    client: MiroClient,
    board_id: str,
    tag_id: str,
    title: str | None = None,
    fill_color: str | None = None,
) -> dict[str, Any]:
    """Rename a tag or change its color. Note: tag changes via REST are
    not reflected on the board in realtime — refresh the board to see them."""
    return await client.patch(
        f"/v2/boards/{board_id}/tags/{tag_id}",
        json_body=drop_none({"title": title, "fillColor": fill_color}),
    )


@tool(destructive=True)
async def delete_tag(
    client: MiroClient, board_id: str, tag_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Delete a tag from the board. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"delete tag {tag_id}"):
        return blocked
    log.warning("Deleting tag %s on board %s (confirmed)", tag_id, board_id)
    await client.delete(f"/v2/boards/{board_id}/tags/{tag_id}")
    return {"deleted": tag_id}


@tool(profile=ESSENTIAL)
async def attach_tag(
    client: MiroClient, board_id: str, item_id: str, tag_id: str
) -> dict[str, Any]:
    """Attach a tag to an item (cards/stickies: max 8 tags). Changes are
    not reflected in realtime — refresh the board to see them."""
    await client.post(
        f"/v2/boards/{board_id}/items/{item_id}",
        params={"tag_id": tag_id},
    )
    return {"attached": tag_id, "item_id": item_id}


@tool(destructive=True)
async def detach_tag(
    client: MiroClient,
    board_id: str,
    item_id: str,
    tag_id: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Remove a tag from an item. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"detach tag {tag_id} from item {item_id}"):
        return blocked
    await client.delete(
        f"/v2/boards/{board_id}/items/{item_id}",
        params={"tag_id": tag_id},
    )
    return {"detached": tag_id, "item_id": item_id}


@tool()
async def get_item_tags(
    client: MiroClient, board_id: str, item_id: str
) -> dict[str, Any]:
    """List the tags attached to an item."""
    page = await client.get(f"/v2/boards/{board_id}/items/{item_id}/tags")
    data = page.get("data") or page.get("tags") or []
    return {"items": data, "count": len(data)}
