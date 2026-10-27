"""Shared helpers for tool implementations."""

from __future__ import annotations

import re
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: Miro item type -> REST path segment under /v2/boards/{board_id}/
ITEM_PATHS = {
    "app_card": "app_cards",
    "card": "cards",
    "connector": "connectors",
    "doc_format": "docs",
    "document": "documents",
    "embed": "embeds",
    "frame": "frames",
    "image": "images",
    "shape": "shapes",
    "sticky_note": "sticky_notes",
    "text": "texts",
}


def drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def position(x: float | None, y: float | None) -> dict[str, Any] | None:
    if x is None and y is None:
        return None
    return drop_none({"x": x, "y": y, "origin": "center"})


def geometry(
    width: float | None = None, height: float | None = None
) -> dict[str, Any] | None:
    g = drop_none({"width": width, "height": height})
    return g or None


def parent_of(frame_id: str | None) -> dict[str, Any] | None:
    return {"id": frame_id} if frame_id else None


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce a Miro item JSON to the fields that matter for a listing."""
    data = item.get("data") or {}
    pos = item.get("position") or {}
    geo = item.get("geometry") or {}
    parent = item.get("parent") or {}
    text = data.get("title") or strip_html(data.get("content") or "")
    out: dict[str, Any] = {
        "id": item.get("id"),
        "type": item.get("type"),
        "x": pos.get("x"),
        "y": pos.get("y"),
        "width": geo.get("width"),
        "height": geo.get("height"),
        "parent_id": parent.get("id"),
    }
    if text:
        out["text"] = text[:120]
    return out


def item_path(board_id: str, item_type: str, item_id: str | None = None) -> str:
    """Typed item path, e.g. /v2/boards/{b}/sticky_notes/{i}."""
    segment = ITEM_PATHS.get(item_type)
    if not segment:
        raise ValueError(f"unsupported item type for typed path: {item_type}")
    path = f"/v2/boards/{board_id}/{segment}"
    return f"{path}/{item_id}" if item_id else path


def require_confirm(confirm: bool, action: str) -> dict[str, Any] | None:
    """Return an error payload when a destructive op lacks confirm=true."""
    if confirm:
        return None
    return {
        "error": "confirmation_required",
        "message": (
            f"{action} is destructive and was not executed. "
            "Call again with confirm=true to proceed."
        ),
    }


def cursor_result(page: dict[str, Any], *, compact: bool = True) -> dict[str, Any]:
    """Normalize a cursor-paginated response for tool output."""
    data = page.get("data") or []
    items = [compact_item(i) if compact else i for i in data]
    out: dict[str, Any] = {"items": items, "count": len(items)}
    cursor = page.get("cursor")
    if cursor:
        out["cursor"] = cursor
    return out


def offset_result(page: dict[str, Any], *, compact: bool = True) -> dict[str, Any]:
    """Normalize an offset-paginated response for tool output."""
    data = page.get("data") or []
    items = [compact_item(i) if compact else i for i in data]
    out: dict[str, Any] = {"items": items, "count": len(items)}
    total = page.get("total")
    if total is not None:
        out["total"] = total
        out["offset"] = page.get("offset", 0)
    return out
