"""Board members: list, get, share (invite), change role, remove."""

from __future__ import annotations

import logging
from typing import Any, Literal

from ..client import MiroClient
from ..registry import tool
from .common import offset_result, require_confirm

log = logging.getLogger("miro_mcp")

BoardRole = Literal["viewer", "commenter", "editor", "coowner"]

ROLES_DOC = "one of viewer, commenter, editor, coowner"


@tool()
async def list_board_members(
    client: MiroClient,
    board_id: str,
    limit: int = 20,
    offset: int = 0,
    fetch_all: bool = False,
) -> dict[str, Any]:
    """List members of a board (offset-paginated). Set ``fetch_all`` to
    walk all pages."""
    path = f"/v2/boards/{board_id}/members"
    if fetch_all:
        items = [
            m async for m in client.iter_offset(path, limit=min(max(limit, 1), 50))
        ]
        return {"items": items, "count": len(items)}
    page = await client.get(path, params={"limit": str(limit), "offset": str(offset)})
    return offset_result(page, compact=False)


@tool()
async def get_board_member(
    client: MiroClient, board_id: str, member_id: str
) -> dict[str, Any]:
    """Get one board member (role, type)."""
    return await client.get(f"/v2/boards/{board_id}/members/{member_id}")


@tool(destructive=True)
async def share_board(
    client: MiroClient,
    board_id: str,
    emails: list[str],
    role: BoardRole = "viewer",
    message: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Invite users to a board by email (up to 20 per call).

    ``role`` is one of viewer, commenter, editor, coowner. Grants access —
    requires ``confirm=true``.
    """
    if blocked := require_confirm(
        confirm, f"share board {board_id} with {len(emails)} email(s)"
    ):
        return blocked
    body: dict[str, Any] = {"emails": emails, "role": role}
    if message:
        body["message"] = message
    return await client.post(f"/v2/boards/{board_id}/members", json_body=body)


@tool(destructive=True)
async def update_board_member(
    client: MiroClient,
    board_id: str,
    member_id: str,
    role: BoardRole,
    confirm: bool = False,
) -> dict[str, Any]:
    """Change a board member's role (viewer, commenter, editor, coowner).

    Requires ``confirm=true``.
    """
    if blocked := require_confirm(confirm, f"set role={role} on member {member_id}"):
        return blocked
    return await client.patch(
        f"/v2/boards/{board_id}/members/{member_id}",
        json_body={"role": role},
    )


@tool(destructive=True)
async def remove_board_member(
    client: MiroClient, board_id: str, member_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Remove a member from a board. Requires ``confirm=true``."""
    if blocked := require_confirm(
        confirm, f"remove member {member_id} from board {board_id}"
    ):
        return blocked
    log.warning("Removing member %s from board %s (confirmed)", member_id, board_id)
    await client.delete(f"/v2/boards/{board_id}/members/{member_id}")
    return {"removed": member_id}
