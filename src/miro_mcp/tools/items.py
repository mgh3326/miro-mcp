"""Board items: generic list/get/search/position/delete/bulk plus typed
create + update for sticky_note, shape, text, card, app_card, frame,
embed, document, image, and experimental code widgets."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Literal

from ..client import MiroClient
from ..registry import ESSENTIAL, tool
from .common import (
    compact_item,
    cursor_result,
    drop_none,
    geometry,
    item_path,
    offset_result,
    parent_of,
    position,
    require_confirm,
    strip_html,
)

log = logging.getLogger("miro_mcp")

StickyShape = Literal["square", "rectangle"]
StickyColor = Literal[
    "gray",
    "light_yellow",
    "yellow",
    "orange",
    "light_green",
    "green",
    "dark_green",
    "cyan",
    "light_pink",
    "pink",
    "violet",
    "red",
    "light_blue",
    "blue",
    "dark_blue",
    "black",
]
TextAlign = Literal["left", "right", "center"]
TextAlignVertical = Literal["top", "middle", "bottom"]
BorderStyle = Literal["normal", "dotted", "dashed"]
EmbedMode = Literal["inline", "modal"]
AppCardStatus = Literal["disconnected", "connected", "disabled"]
BorderShape = Literal["round", "square"]

#: Shape names accepted by the stable /v2 shapes endpoint.
SHAPE_NAMES_DOC = (
    "rectangle, round_rectangle, circle, triangle, rhombus, parallelogram, "
    "trapezoid, pentagon, hexagon, octagon, wedge_round_rectangle_callout, "
    "star, flow_chart_predefined_process, cloud, cross, can, right_arrow, "
    "left_arrow, left_right_arrow, left_brace, right_brace"
)


def _item_body(
    *,
    data: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    body = drop_none({"data": data, "style": style})
    if pos := position(x, y):
        body["position"] = pos
    if geo := geometry(width, height):
        body["geometry"] = geo
    if par := parent_of(parent_frame_id):
        body["parent"] = par
    return body


def _mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _load_file(file_path: str) -> tuple[str, bytes, str]:
    p = Path(file_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {p}")
    return p.name, p.read_bytes(), _mime(p)


async def _multipart_upload(
    client: MiroClient,
    path: str,
    file_path: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    import anyio.to_thread

    name, content, mime = await anyio.to_thread.run_sync(_load_file, file_path)
    files: dict[str, Any] = {"resource": (name, content, mime)}
    if metadata:
        files["data"] = (None, json.dumps(metadata), "application/json")
    return await client.post(path, files=files)


# ---------------------------------------------------------------------------
# Generic item endpoints
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def list_items(
    client: MiroClient,
    board_id: str,
    type: str | None = None,
    parent_item_id: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    fetch_all: bool = False,
) -> dict[str, Any]:
    """List items on a board in a compact shape (id, type, x, y, size,
    parent, text).

    ``type`` filters to one item type (app_card, card, doc_format, document,
    embed, frame, image, shape, sticky_note, text). ``parent_item_id``
    lists children of a frame. Cursor-paginated; ``fetch_all`` walks all
    pages.
    """
    path = f"/v2/boards/{board_id}/items"
    params = drop_none({"type": type, "parent_item_id": parent_item_id})
    if fetch_all:
        items = [
            compact_item(i)
            async for i in client.iter_cursor(
                path, params=params | {"limit": str(min(max(limit, 10), 50))}
            )
        ]
        return {"items": items, "count": len(items)}
    params.update({"limit": str(limit)})
    if cursor:
        params["cursor"] = cursor
    page = await client.get(path, params=params)
    return cursor_result(page)


@tool(profile=ESSENTIAL)
async def get_item(client: MiroClient, board_id: str, item_id: str) -> dict[str, Any]:
    """Get the full JSON of one item (data, style, position, geometry,
    parent, timestamps)."""
    return await client.get(f"/v2/boards/{board_id}/items/{item_id}")


@tool(profile=ESSENTIAL)
async def search_items(
    client: MiroClient,
    board_id: str,
    query: str,
    type: str | None = None,
    case_sensitive: bool = False,
    max_pages: int = 20,
) -> dict[str, Any]:
    """Search items by text content (client-side scan of titles/content).

    Scans up to ``max_pages`` x 50 items. Returns compact matches.
    """
    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    params = drop_none({"type": type})
    scanned = 0
    async for item in client.iter_cursor(
        f"/v2/boards/{board_id}/items",
        params=params | {"limit": "50"},
        max_pages=max_pages,
    ):
        scanned += 1
        data = item.get("data") or {}
        hay = " ".join(
            str(v)
            for v in (
                data.get("title"),
                strip_html(data.get("content") or ""),
                strip_html(data.get("description") or ""),
            )
            if v
        )
        haystack = hay if case_sensitive else hay.lower()
        if needle in haystack:
            matches.append(compact_item(item))
    return {"items": matches, "count": len(matches), "scanned": scanned}


@tool()
async def update_item_position(
    client: MiroClient,
    board_id: str,
    item_id: str,
    x: float | None = None,
    y: float | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Move an item on the canvas or reparent it into/out of a frame.

    Works on any item type. ``parent_id`` set to a frame id nests the item;
    use ``"none"`` semantics per Miro docs to detach (send parent omitted
    and change position instead).
    """
    body: dict[str, Any] = {}
    if pos := position(x, y):
        body["position"] = pos
    if parent_id:
        body["parent"] = {"id": parent_id}
    if not body:
        return {
            "error": "nothing_to_update",
            "message": "provide x, y, and/or parent_id",
        }
    return await client.patch(f"/v2/boards/{board_id}/items/{item_id}", json_body=body)


@tool(profile=ESSENTIAL, destructive=True)
async def delete_item(
    client: MiroClient, board_id: str, item_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Delete any single item. Requires ``confirm=true``; the item id is
    logged when confirmed."""
    if blocked := require_confirm(confirm, f"delete item {item_id}"):
        return blocked
    log.warning("Deleting item %s on board %s (confirmed)", item_id, board_id)
    await client.delete(f"/v2/boards/{board_id}/items/{item_id}")
    return {"deleted": item_id}


@tool()
async def get_items_by_tag(
    client: MiroClient,
    board_id: str,
    tag_id: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List items carrying a given tag (offset-paginated)."""
    page = await client.get(
        f"/v2/boards/{board_id}/items",
        params={
            "tag_id": tag_id,
            "limit": str(limit),
            "offset": str(offset),
        },
    )
    return offset_result(page)


@tool()
async def bulk_create_items(
    client: MiroClient, board_id: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create up to 20 items in one call.

    Each entry follows the Miro bulk schema: ``{"type": "sticky_note",
    "data": {...}, "style": {...}, "position": {"x":..,"y":..},
    "geometry": {...}, "parent": {"id": frame_id}}``. Types: app_card,
    card, document, embed, image (URL), shape, sticky_note, text.
    """
    if not items:
        return {"error": "empty_items", "message": "items must be non-empty"}
    if len(items) > 20:
        return {
            "error": "too_many_items",
            "message": "the bulk endpoint accepts at most 20 items per call",
        }
    return await client.post(f"/v2/boards/{board_id}/items/bulk", json_body=items)


@tool()
async def bulk_update_items(
    client: MiroClient,
    board_id: str,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Update many items concurrently (client-side batch; no bulk-update
    endpoint exists in REST).

    Each entry: ``{"item_id": str, "item_type": str?}`` plus any of
    ``data``, ``style``, ``position``, ``geometry``, ``parent`` dicts sent
    verbatim. With ``item_type`` the typed endpoint is used (e.g.
    sticky_notes); without it, the generic position/parent endpoint.
    Returns per-item ok/error results.
    """

    async def one(u: dict[str, Any]) -> dict[str, Any]:
        item_id = u["item_id"]
        item_type = u.get("item_type")
        if item_type:
            path = item_path(board_id, str(item_type), str(item_id))
        else:
            path = f"/v2/boards/{board_id}/items/{item_id}"
        body = drop_none(
            {
                "data": u.get("data"),
                "style": u.get("style"),
                "position": u.get("position"),
                "geometry": u.get("geometry"),
                "parent": u.get("parent"),
            }
        )
        try:
            item = await client.patch(path, json_body=body)
            return {"item_id": item_id, "ok": True, "item": item}
        except Exception as exc:
            return {"item_id": item_id, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(one(u) for u in updates))
    ok = sum(1 for r in results if r["ok"])
    return {"results": results, "updated": ok, "failed": len(results) - ok}


@tool(destructive=True)
async def bulk_delete_items(
    client: MiroClient,
    board_id: str,
    item_ids: list[str],
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete many items concurrently. Requires ``confirm=true``; ids are
    logged when confirmed."""
    if blocked := require_confirm(
        confirm, f"delete {len(item_ids)} item(s) on board {board_id}"
    ):
        return blocked
    log.warning(
        "Bulk-deleting %d items on board %s: %s",
        len(item_ids),
        board_id,
        item_ids,
    )

    async def one(item_id: str) -> dict[str, Any]:
        try:
            await client.delete(f"/v2/boards/{board_id}/items/{item_id}")
            return {"item_id": item_id, "ok": True}
        except Exception as exc:
            return {"item_id": item_id, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(one(i) for i in item_ids))
    ok = sum(1 for r in results if r["ok"])
    return {"results": results, "deleted": ok, "failed": len(results) - ok}


# ---------------------------------------------------------------------------
# Sticky notes
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def create_sticky_note(
    client: MiroClient,
    board_id: str,
    content: str,
    x: float,
    y: float,
    shape: StickyShape = "square",
    fill_color: StickyColor | None = None,
    text_align: TextAlign | None = None,
    text_align_vertical: TextAlignVertical | None = None,
    width: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a sticky note. ``content`` accepts simple HTML (``<p>``,
    ``<b>``, ``<br/>``...). ``fill_color`` is a Miro palette name
    (gray, light_yellow, yellow, orange, light_green, green, dark_green,
    cyan, light_pink, pink, violet, red, light_blue, blue, dark_blue,
    black)."""
    body = _item_body(
        data=drop_none({"content": content, "shape": shape}),
        style=drop_none(
            {
                "fillColor": fill_color,
                "textAlign": text_align,
                "textAlignVertical": text_align_vertical,
            }
        ),
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/sticky_notes", json_body=body)


@tool()
async def update_sticky_note(
    client: MiroClient,
    board_id: str,
    item_id: str,
    content: str | None = None,
    shape: StickyShape | None = None,
    fill_color: StickyColor | None = None,
    text_align: TextAlign | None = None,
    text_align_vertical: TextAlignVertical | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a sticky note's content, style, position or parent."""
    body = _item_body(
        data=drop_none({"content": content, "shape": shape}) or None,
        style=drop_none(
            {
                "fillColor": fill_color,
                "textAlign": text_align,
                "textAlignVertical": text_align_vertical,
            }
        )
        or None,
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(
        f"/v2/boards/{board_id}/sticky_notes/{item_id}", json_body=body
    )


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def create_shape(
    client: MiroClient,
    board_id: str,
    x: float,
    y: float,
    content: str = "",
    shape: str = "rectangle",
    width: float | None = None,
    height: float | None = None,
    fill_color: str | None = None,
    border_color: str | None = None,
    border_width: float | None = None,
    border_style: BorderStyle | None = None,
    color: str | None = None,
    font_size: float | None = None,
    text_align: TextAlign | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a shape. ``shape`` is one of: rectangle, round_rectangle,
    circle, triangle, rhombus, parallelogram, trapezoid, pentagon, hexagon,
    octagon, wedge_round_rectangle_callout, star,
    flow_chart_predefined_process, cloud, cross, can, right_arrow,
    left_arrow, left_right_arrow, left_brace, right_brace. Colors are hex
    strings like ``#ff0000``."""
    body = _item_body(
        data=drop_none({"content": content, "shape": shape}),
        style=drop_none(
            {
                "fillColor": fill_color,
                "borderColor": border_color,
                "borderWidth": border_width,
                "borderStyle": border_style,
                "color": color,
                "fontSize": font_size,
                "textAlign": text_align,
            }
        ),
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/shapes", json_body=body)


@tool()
async def update_shape(
    client: MiroClient,
    board_id: str,
    item_id: str,
    content: str | None = None,
    shape: str | None = None,
    fill_color: str | None = None,
    border_color: str | None = None,
    border_width: float | None = None,
    border_style: BorderStyle | None = None,
    color: str | None = None,
    font_size: float | None = None,
    text_align: TextAlign | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a shape's content, style, position or parent."""
    body = _item_body(
        data=drop_none({"content": content, "shape": shape}) or None,
        style=drop_none(
            {
                "fillColor": fill_color,
                "borderColor": border_color,
                "borderWidth": border_width,
                "borderStyle": border_style,
                "color": color,
                "fontSize": font_size,
                "textAlign": text_align,
            }
        )
        or None,
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(f"/v2/boards/{board_id}/shapes/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def create_text(
    client: MiroClient,
    board_id: str,
    content: str,
    x: float,
    y: float,
    width: float | None = None,
    color: str | None = None,
    font_size: float | None = None,
    font_family: str | None = None,
    text_align: TextAlign | None = None,
    rotation: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a standalone text item. ``content`` accepts simple HTML."""
    body = _item_body(
        data=drop_none({"content": content}),
        style=drop_none(
            {
                "color": color,
                "fontSize": font_size,
                "fontFamily": font_family,
                "textAlign": text_align,
            }
        ),
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    if rotation is not None:
        body["rotation"] = rotation
    return await client.post(f"/v2/boards/{board_id}/texts", json_body=body)


@tool()
async def update_text(
    client: MiroClient,
    board_id: str,
    item_id: str,
    content: str | None = None,
    color: str | None = None,
    font_size: float | None = None,
    font_family: str | None = None,
    text_align: TextAlign | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    strike: bool | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    rotation: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a text item's content, style, position or parent."""
    body = _item_body(
        data=drop_none({"content": content}) or None,
        style=drop_none(
            {
                "color": color,
                "fontSize": font_size,
                "fontFamily": font_family,
                "textAlign": text_align,
                "bold": bold,
                "italic": italic,
                "underline": underline,
                "strike": strike,
            }
        )
        or None,
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    if rotation is not None:
        body["rotation"] = rotation
    return await client.patch(f"/v2/boards/{board_id}/texts/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def create_card(
    client: MiroClient,
    board_id: str,
    title: str,
    x: float,
    y: float,
    description: str | None = None,
    due_date: str | None = None,
    assignee_id: str | None = None,
    fill_color: str | None = None,
    card_theme: str | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a card. ``due_date`` is ISO 8601 (``2026-12-31``)."""
    body = _item_body(
        data=drop_none(
            {
                "title": title,
                "description": description,
                "dueDate": due_date,
                "assigneeId": assignee_id,
            }
        ),
        style=drop_none({"fillColor": fill_color, "cardTheme": card_theme}),
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/cards", json_body=body)


@tool()
async def update_card(
    client: MiroClient,
    board_id: str,
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    assignee_id: str | None = None,
    fill_color: str | None = None,
    card_theme: str | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a card's data, style, position or parent."""
    body = _item_body(
        data=drop_none(
            {
                "title": title,
                "description": description,
                "dueDate": due_date,
                "assigneeId": assignee_id,
            }
        )
        or None,
        style=drop_none({"fillColor": fill_color, "cardTheme": card_theme}) or None,
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(f"/v2/boards/{board_id}/cards/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# App cards
# ---------------------------------------------------------------------------


@tool()
async def create_app_card(
    client: MiroClient,
    board_id: str,
    title: str,
    x: float,
    y: float,
    description: str | None = None,
    status: AppCardStatus | None = None,
    fields: list[str] | None = None,
    card_theme: str | None = None,
    border_shape: BorderShape | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create an app card (widget card linked to an app).

    ``status``: disconnected, connected or disabled. ``fields`` is a list
    of field values shown on the card. ``border_shape``: round or square.
    """
    body = _item_body(
        data=drop_none(
            {
                "title": title,
                "description": description,
                "status": status,
                "fields": [{"value": v} for v in fields] if fields else None,
            }
        ),
        style=drop_none({"cardTheme": card_theme, "borderShape": border_shape}),
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/app_cards", json_body=body)


@tool()
async def update_app_card(
    client: MiroClient,
    board_id: str,
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    status: AppCardStatus | None = None,
    fields: list[str] | None = None,
    card_theme: str | None = None,
    border_shape: BorderShape | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update an app card's data, style, position or parent."""
    body = _item_body(
        data=drop_none(
            {
                "title": title,
                "description": description,
                "status": status,
                "fields": [{"value": v} for v in fields] if fields else None,
            }
        )
        or None,
        style=drop_none({"cardTheme": card_theme, "borderShape": border_shape}) or None,
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(
        f"/v2/boards/{board_id}/app_cards/{item_id}", json_body=body
    )


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def create_frame(
    client: MiroClient,
    board_id: str,
    title: str,
    x: float,
    y: float,
    width: float | None = None,
    height: float | None = None,
    fill_color: str | None = None,
    show_content: bool | None = None,
    format: str | None = None,
) -> dict[str, Any]:
    """Create a frame. ``show_content`` hides/shows children on the canvas.
    ``format`` accepts ``custom``; frame ``type`` defaults to freeform."""
    body = _item_body(
        data=drop_none(
            {
                "title": title,
                "showContent": show_content,
                "format": format,
                "type": "freeform",
            }
        ),
        style=drop_none({"fillColor": fill_color}),
        x=x,
        y=y,
        width=width,
        height=height,
    )
    return await client.post(f"/v2/boards/{board_id}/frames", json_body=body)


@tool()
async def update_frame(
    client: MiroClient,
    board_id: str,
    item_id: str,
    title: str | None = None,
    show_content: bool | None = None,
    fill_color: str | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
) -> dict[str, Any]:
    """Update a frame's title, visibility, style, size or position."""
    body = _item_body(
        data=drop_none({"title": title, "showContent": show_content}) or None,
        style=drop_none({"fillColor": fill_color}) or None,
        x=x,
        y=y,
        width=width,
        height=height,
    )
    return await client.patch(f"/v2/boards/{board_id}/frames/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# Embeds
# ---------------------------------------------------------------------------


@tool()
async def create_embed(
    client: MiroClient,
    board_id: str,
    url: str,
    x: float,
    y: float,
    mode: EmbedMode | None = None,
    preview_url: str | None = None,
    provider_name: str | None = None,
    provider_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create an embed item from a URL. ``mode``: inline or modal."""
    body = _item_body(
        data=drop_none(
            {
                "url": url,
                "mode": mode,
                "previewUrl": preview_url,
                "providerName": provider_name,
                "providerUrl": provider_url,
                "title": title,
                "description": description,
            }
        ),
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/embeds", json_body=body)


@tool()
async def update_embed(
    client: MiroClient,
    board_id: str,
    item_id: str,
    url: str | None = None,
    mode: EmbedMode | None = None,
    preview_url: str | None = None,
    provider_name: str | None = None,
    provider_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update an embed item's data, position or parent."""
    body = _item_body(
        data=drop_none(
            {
                "url": url,
                "mode": mode,
                "previewUrl": preview_url,
                "providerName": provider_name,
                "providerUrl": provider_url,
                "title": title,
                "description": description,
            }
        )
        or None,
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(f"/v2/boards/{board_id}/embeds/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@tool()
async def create_document_from_url(
    client: MiroClient,
    board_id: str,
    document_url: str,
    x: float,
    y: float,
    title: str | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Add a document item (PDF, etc.) to the board from a URL."""
    body = _item_body(
        data=drop_none({"documentUrl": document_url, "title": title}),
        x=x,
        y=y,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/documents", json_body=body)


@tool()
async def upload_document(
    client: MiroClient,
    board_id: str,
    file_path: str,
    x: float,
    y: float,
    title: str | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Upload a document file from the local disk (PDF, DOCX, PPTX, XLSX,
    CSV; max ~30 MB)."""
    metadata = drop_none(
        {
            "title": title,
            "position": position(x, y),
            "parent": parent_of(parent_frame_id),
        }
    )
    return await _multipart_upload(
        client, f"/v2/boards/{board_id}/documents", file_path, metadata
    )


@tool()
async def update_document(
    client: MiroClient,
    board_id: str,
    item_id: str,
    document_url: str | None = None,
    title: str | None = None,
    x: float | None = None,
    y: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a document item (replace its URL, retitle, move)."""
    body = _item_body(
        data=drop_none({"documentUrl": document_url, "title": title}) or None,
        x=x,
        y=y,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(
        f"/v2/boards/{board_id}/documents/{item_id}", json_body=body
    )


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


@tool(profile=ESSENTIAL)
async def upload_image(
    client: MiroClient,
    board_id: str,
    file_path: str,
    x: float,
    y: float,
    width: float | None = None,
    title: str | None = None,
    alt_text: str | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Upload a local image file to the board (PNG/JPG/SVG, max 6 MB).

    This is a real multipart upload — the main gap vs. the hosted Miro
    connector.
    """
    metadata = drop_none(
        {
            "title": title,
            "altText": alt_text,
            "position": position(x, y),
            "geometry": geometry(width),
            "parent": parent_of(parent_frame_id),
        }
    )
    return await _multipart_upload(
        client, f"/v2/boards/{board_id}/images", file_path, metadata
    )


@tool()
async def create_image_from_url(
    client: MiroClient,
    board_id: str,
    url: str,
    x: float,
    y: float,
    width: float | None = None,
    title: str | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create an image item from a public URL."""
    body = _item_body(
        data=drop_none({"url": url, "title": title}),
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(f"/v2/boards/{board_id}/images", json_body=body)


@tool()
async def update_image(
    client: MiroClient,
    board_id: str,
    item_id: str,
    url: str | None = None,
    title: str | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update an image item (swap URL, retitle, move/resize)."""
    body = _item_body(
        data=drop_none({"url": url, "title": title}) or None,
        x=x,
        y=y,
        width=width,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(f"/v2/boards/{board_id}/images/{item_id}", json_body=body)


# ---------------------------------------------------------------------------
# Code widgets (experimental API)
# ---------------------------------------------------------------------------


@tool()
async def list_code_widgets(
    client: MiroClient,
    board_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List code widget items. EXPERIMENTAL: uses the
    ``/v2-experimental`` endpoints which may change."""
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    page = await client.get(
        f"/v2-experimental/boards/{board_id}/code_widgets", params=params
    )
    return cursor_result(page)


@tool()
async def get_code_widget(
    client: MiroClient, board_id: str, item_id: str
) -> dict[str, Any]:
    """Get one code widget. EXPERIMENTAL."""
    return await client.get(
        f"/v2-experimental/boards/{board_id}/code_widgets/{item_id}"
    )


@tool()
async def create_code_widget(
    client: MiroClient,
    board_id: str,
    code: str,
    x: float,
    y: float,
    language: str | None = None,
    title: str | None = None,
    line_numbers_visible: bool | None = None,
    width: float | None = None,
    height: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Create a code widget (syntax-highlighted code block).
    EXPERIMENTAL."""
    body = _item_body(
        data=drop_none(
            {
                "code": code,
                "language": language,
                "title": title,
                "lineNumbersVisible": line_numbers_visible,
            }
        ),
        x=x,
        y=y,
        width=width,
        height=height,
        parent_frame_id=parent_frame_id,
    )
    return await client.post(
        f"/v2-experimental/boards/{board_id}/code_widgets", json_body=body
    )


@tool()
async def update_code_widget(
    client: MiroClient,
    board_id: str,
    item_id: str,
    code: str | None = None,
    language: str | None = None,
    title: str | None = None,
    line_numbers_visible: bool | None = None,
    x: float | None = None,
    y: float | None = None,
    parent_frame_id: str | None = None,
) -> dict[str, Any]:
    """Update a code widget. EXPERIMENTAL."""
    body = _item_body(
        data=drop_none(
            {
                "code": code,
                "language": language,
                "title": title,
                "lineNumbersVisible": line_numbers_visible,
            }
        )
        or None,
        x=x,
        y=y,
        parent_frame_id=parent_frame_id,
    )
    return await client.patch(
        f"/v2-experimental/boards/{board_id}/code_widgets/{item_id}",
        json_body=body,
    )
