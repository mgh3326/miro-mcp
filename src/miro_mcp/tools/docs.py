"""Doc format items (markdown documents on the board).

REST supports create, read and delete only — no update. ``replace_doc``
implements "edit" as read + delete + create, preserving position, size
and parent, and is labelled as such.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from ..client import MiroClient
from ..registry import tool
from .common import drop_none, parent_of, position, require_confirm

log = logging.getLogger("miro_mcp")

DocContentType = Literal["markdown", "html"]


@tool()
async def create_doc(
    client: MiroClient,
    board_id: str,
    content: str,
    x: float,
    y: float,
    content_type: DocContentType = "markdown",
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a doc format item on the board.

    ``content_type`` is ``markdown`` or ``html``. Docs cannot be edited
    via REST after creation — see ``replace_doc``.
    """
    body = drop_none(
        {
            "data": {"contentType": content_type, "content": content},
            "position": position(x, y),
            "parent": parent_of(parent_frame_id),
        }
    )
    return await client.post(f"/v2/boards/{board_id}/docs", json_body=body)


@tool()
async def get_doc(client: MiroClient, board_id: str, item_id: str) -> dict[str, Any]:
    """Get a doc format item including its markdown/html content."""
    return await client.get(f"/v2/boards/{board_id}/docs/{item_id}")


@tool(destructive=True)
async def delete_doc(
    client: MiroClient, board_id: str, item_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Delete a doc format item. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"delete doc {item_id}"):
        return blocked
    log.warning("Deleting doc %s on board %s (confirmed)", item_id, board_id)
    await client.delete(f"/v2/boards/{board_id}/docs/{item_id}")
    return {"deleted": item_id}


@tool(destructive=True)
async def replace_doc(
    client: MiroClient,
    board_id: str,
    item_id: str,
    content: str,
    content_type: DocContentType | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Replace a doc's content — implemented as read + delete + create
    because REST has no doc update endpoint.

    The new doc gets a NEW item id; the old id stops existing. Preserves
    position, geometry, parent and content type (unless overridden).
    Requires ``confirm=true``.
    """
    if blocked := require_confirm(
        confirm, f"replace doc {item_id} (delete + recreate, new id)"
    ):
        return blocked
    old = await client.get(f"/v2/boards/{board_id}/docs/{item_id}")
    old_data = old.get("data") or {}
    ctype = content_type or old_data.get("contentType") or "markdown"
    body = drop_none(
        {
            "data": {"contentType": ctype, "content": content},
            "position": old.get("position"),
            "geometry": old.get("geometry"),
            "parent": old.get("parent"),
        }
    )
    await client.delete(f"/v2/boards/{board_id}/docs/{item_id}")
    new = await client.post(f"/v2/boards/{board_id}/docs", json_body=body)
    return {
        "replaced": item_id,
        "new_item": new,
        "note": "doc was deleted and recreated (REST has no doc update)",
    }
