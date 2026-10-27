"""Connectors: list, get, create, update, delete."""

from __future__ import annotations

import logging
from typing import Any, Literal

from ..client import MiroClient
from ..registry import ESSENTIAL, tool
from .common import cursor_result, drop_none, require_confirm

log = logging.getLogger("miro_mcp")

StrokeStyle = Literal["normal", "dotted", "dashed"]
StrokeCap = Literal["none", "arrow", "triangle", "stealth", "rounded", "diamond"]


def _cap(value: StrokeCap | None) -> str | None:
    return value


@tool()
async def list_connectors(
    client: MiroClient,
    board_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List connectors on a board (cursor-paginated)."""
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(f"/v2/boards/{board_id}/connectors", params=params)
    return cursor_result(page, compact=False)


@tool()
async def get_connector(
    client: MiroClient, board_id: str, connector_id: str
) -> dict[str, Any]:
    """Get one connector (start/end items, captions, style)."""
    return await client.get(f"/v2/boards/{board_id}/connectors/{connector_id}")


def _connector_style(
    stroke_color: str | None,
    stroke_width: float | None,
    stroke_style: StrokeStyle | None,
    start_stroke_cap: StrokeCap | None,
    end_stroke_cap: StrokeCap | None,
    color: str | None,
    font_size: float | None,
    text_orientation: str | None,
) -> dict[str, Any] | None:
    style = drop_none(
        {
            "strokeColor": stroke_color,
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "startStrokeCap": _cap(start_stroke_cap),
            "endStrokeCap": _cap(end_stroke_cap),
            "color": color,
            "fontSize": font_size,
            "textOrientation": text_orientation,
        }
    )
    return style or None


@tool(profile=ESSENTIAL)
async def create_connector(
    client: MiroClient,
    board_id: str,
    start_item_id: str,
    end_item_id: str,
    caption: str | None = None,
    stroke_color: str | None = None,
    stroke_width: float | None = None,
    stroke_style: StrokeStyle | None = None,
    start_stroke_cap: StrokeCap | None = None,
    end_stroke_cap: StrokeCap | None = None,
    color: str | None = None,
    font_size: float | None = None,
    text_orientation: str | None = None,
) -> dict[str, Any]:
    """Connect two items. ``caption`` adds a text label. Caps like
    ``end_stroke_cap="arrow"`` control arrowheads; ``stroke_style`` is
    normal, dotted or dashed."""
    body: dict[str, Any] = {
        "startItem": {"id": start_item_id},
        "endItem": {"id": end_item_id},
    }
    if caption:
        body["captions"] = [{"content": caption}]
    if style := _connector_style(
        stroke_color,
        stroke_width,
        stroke_style,
        start_stroke_cap,
        end_stroke_cap,
        color,
        font_size,
        text_orientation,
    ):
        body["style"] = style
    return await client.post(f"/v2/boards/{board_id}/connectors", json_body=body)


@tool()
async def update_connector(
    client: MiroClient,
    board_id: str,
    connector_id: str,
    start_item_id: str | None = None,
    end_item_id: str | None = None,
    caption: str | None = None,
    stroke_color: str | None = None,
    stroke_width: float | None = None,
    stroke_style: StrokeStyle | None = None,
    start_stroke_cap: StrokeCap | None = None,
    end_stroke_cap: StrokeCap | None = None,
    color: str | None = None,
    font_size: float | None = None,
    text_orientation: str | None = None,
) -> dict[str, Any]:
    """Update a connector's endpoints, caption or style."""
    body: dict[str, Any] = {}
    if start_item_id:
        body["startItem"] = {"id": start_item_id}
    if end_item_id:
        body["endItem"] = {"id": end_item_id}
    if caption is not None:
        body["captions"] = [{"content": caption}] if caption else []
    if style := _connector_style(
        stroke_color,
        stroke_width,
        stroke_style,
        start_stroke_cap,
        end_stroke_cap,
        color,
        font_size,
        text_orientation,
    ):
        body["style"] = style
    return await client.patch(
        f"/v2/boards/{board_id}/connectors/{connector_id}", json_body=body
    )


@tool(destructive=True)
async def delete_connector(
    client: MiroClient,
    board_id: str,
    connector_id: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete a connector. Requires ``confirm=true``."""
    if blocked := require_confirm(confirm, f"delete connector {connector_id}"):
        return blocked
    log.warning(
        "Deleting connector %s on board %s (confirmed)",
        connector_id,
        board_id,
    )
    await client.delete(f"/v2/boards/{board_id}/connectors/{connector_id}")
    return {"deleted": connector_id}
