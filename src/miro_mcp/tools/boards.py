"""Board CRUD: list, get, create, copy, update, delete (confirm)."""

from __future__ import annotations

import logging
from typing import Any

from ..client import MiroClient
from ..registry import ESSENTIAL, tool
from .common import drop_none, offset_result, require_confirm

log = logging.getLogger("miro_mcp")


def _compact_board(board: dict[str, Any]) -> dict[str, Any]:
    owner = board.get("owner") or {}
    team = board.get("team") or {}
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "description": board.get("description"),
        "view_link": board.get("viewLink"),
        "owner_id": owner.get("id"),
        "team_id": team.get("id"),
        "created_at": board.get("createdAt"),
        "modified_at": board.get("modifiedAt"),
    }


@tool(profile=ESSENTIAL)
async def list_boards(
    client: MiroClient,
    team_id: str | None = None,
    project_id: str | None = None,
    query: str | None = None,
    owner: str | None = None,
    sort: str | None = None,
    limit: int = 20,
    offset: int = 0,
    fetch_all: bool = False,
) -> dict[str, Any]:
    """List boards visible to the token.

    Offset-paginated. ``query`` filters on board name/description,
    ``owner`` accepts e.g. ``me`` or a user id, ``sort`` e.g. ``default``,
    ``alphabetically``, ``last_opened``, ``last_created``, ``last_modified``.
    Set ``fetch_all`` to walk all pages (careful on large accounts).
    """
    params = drop_none(
        {
            "team_id": team_id,
            "project_id": project_id,
            "query": query,
            "owner": owner,
            "sort": sort,
        }
    )
    if fetch_all:
        items = [
            _compact_board(b)
            async for b in client.iter_offset(
                "/v2/boards", params=params, limit=min(max(limit, 1), 50)
            )
        ]
        return {"items": items, "count": len(items)}
    params.update({"limit": str(limit), "offset": str(offset)})
    page = await client.get("/v2/boards", params=params)
    out = offset_result(page, compact=False)
    out["items"] = [_compact_board(b) for b in page.get("data") or []]
    return out


@tool(profile=ESSENTIAL)
async def get_board(client: MiroClient, board_id: str) -> dict[str, Any]:
    """Get full details of one board (name, owner, links, sharing policy)."""
    return await client.get(f"/v2/boards/{board_id}")


@tool()
async def create_board(
    client: MiroClient,
    name: str,
    description: str | None = None,
    team_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Create a new board. ``team_id`` targets a team; ``project_id``
    targets a Miro space (projects were renamed to spaces)."""
    body = drop_none(
        {
            "name": name,
            "description": description,
            "teamId": team_id,
            "projectId": project_id,
        }
    )
    return await client.post("/v2/boards", json_body=body)


@tool()
async def copy_board(
    client: MiroClient,
    board_id: str,
    name: str | None = None,
    description: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Copy an existing board, optionally renaming or moving it to a team."""
    body = drop_none({"name": name, "description": description, "teamId": team_id})
    return await client.put(
        "/v2/boards", params={"copy_from": board_id}, json_body=body
    )


@tool()
async def update_board(
    client: MiroClient,
    board_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Rename a board or change its description."""
    body = drop_none({"name": name, "description": description})
    return await client.patch(f"/v2/boards/{board_id}", json_body=body)


@tool(destructive=True)
async def delete_board(
    client: MiroClient, board_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Delete a board permanently. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"delete board {board_id}"):
        return blocked
    log.warning("Deleting board %s (confirmed)", board_id)
    await client.delete(f"/v2/boards/{board_id}")
    return {"deleted": board_id}
