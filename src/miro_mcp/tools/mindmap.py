"""Mind map nodes — /v2-experimental endpoints, marked experimental."""

from __future__ import annotations

import logging
from typing import Any

from ..client import MiroClient
from ..registry import tool
from .common import cursor_result, parent_of, position, require_confirm

log = logging.getLogger("miro_mcp")

BASE_PATH = "/v2-experimental/boards/{board_id}/mindmap_nodes"


@tool()
async def list_mindmap_nodes(
    client: MiroClient,
    board_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List mind map nodes on a board. EXPERIMENTAL — the
    /v2-experimental API may change."""
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(BASE_PATH.format(board_id=board_id), params=params)
    return cursor_result(page, compact=False)


@tool()
async def get_mindmap_node(
    client: MiroClient, board_id: str, item_id: str
) -> dict[str, Any]:
    """Get one mind map node. EXPERIMENTAL."""
    return await client.get(f"{BASE_PATH.format(board_id=board_id)}/{item_id}")


@tool()
async def create_mindmap_node(
    client: MiroClient,
    board_id: str,
    content: str,
    x: float | None = None,
    y: float | None = None,
    parent_node_id: str | None = None,
    width: float | None = None,
) -> dict[str, Any]:
    """Create a mind map node (text type). EXPERIMENTAL.

    With ``parent_node_id`` the node becomes a child of that node;
    without it Miro creates/extends the root structure.
    """
    body: dict[str, Any] = {
        "data": {"nodeView": {"data": {"type": "text", "content": content}}}
    }
    if pos := position(x, y):
        body["position"] = pos
    if width is not None:
        body["geometry"] = {"width": width}
    if par := parent_of(parent_node_id):
        body["parent"] = par
    return await client.post(BASE_PATH.format(board_id=board_id), json_body=body)


@tool(destructive=True)
async def delete_mindmap_node(
    client: MiroClient,
    board_id: str,
    item_id: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete a mind map node. EXPERIMENTAL. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"delete mindmap node {item_id}"):
        return blocked
    log.warning("Deleting mindmap node %s on board %s (confirmed)", item_id, board_id)
    await client.delete(f"{BASE_PATH.format(board_id=board_id)}/{item_id}")
    return {"deleted": item_id}
