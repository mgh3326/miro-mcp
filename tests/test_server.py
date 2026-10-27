from __future__ import annotations

import httpx
import pytest
import respx

import miro_mcp.server as server
from miro_mcp import tools as _tools  # noqa: F401 — registers tools
from miro_mcp.registry import TOOLS
from miro_mcp.tools.common import (
    compact_item,
    cursor_result,
    require_confirm,
    strip_html,
)


def test_registry_has_whoami() -> None:
    assert "whoami" in TOOLS


def test_install_tools_full_profile() -> None:
    count = server.install_tools("full")
    assert count == len(TOOLS)


def test_install_tools_essential_profile() -> None:
    count = server.install_tools("essential")
    essentials = sum(1 for s in TOOLS.values() if s.profile == "essential")
    assert count == essentials


def test_install_tools_bad_profile() -> None:
    with pytest.raises(ValueError, match="unknown MIRO_MCP_PROFILE"):
        server.install_tools("nope")


async def test_tool_schema_hides_client_param() -> None:
    server.install_tools("full")
    tools = await server.mcp.list_tools()
    whoami = next(t for t in tools if t.name == "whoami")
    assert "client" not in whoami.inputSchema.get("properties", {})


def test_strip_html() -> None:
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_compact_item() -> None:
    item = {
        "id": "i1",
        "type": "sticky_note",
        "position": {"x": 10, "y": 20},
        "geometry": {"width": 300},
        "parent": {"id": "f1"},
        "data": {"content": "<p>note</p>"},
    }
    out = compact_item(item)
    assert out == {
        "id": "i1",
        "type": "sticky_note",
        "x": 10,
        "y": 20,
        "width": 300,
        "height": None,
        "parent_id": "f1",
        "text": "note",
    }


def test_require_confirm_blocks() -> None:
    out = require_confirm(False, "delete item i1")
    assert out is not None
    assert out["error"] == "confirmation_required"
    assert require_confirm(True, "delete item i1") is None


def test_cursor_result_compact() -> None:
    page = {
        "data": [
            {
                "id": "i1",
                "type": "text",
                "position": {"x": 1, "y": 2},
                "data": {"content": "hi"},
            }
        ],
        "cursor": "c2",
    }
    out = cursor_result(page)
    assert out["count"] == 1
    assert out["cursor"] == "c2"
    assert out["items"][0]["id"] == "i1"


@respx.mock
async def test_whoami_impl(monkeypatch: pytest.MonkeyPatch) -> None:
    from miro_mcp.client import MiroClient
    from miro_mcp.tools.misc import whoami

    respx.get("https://api.miro.com/v1/oauth-token").mock(
        return_value=httpx.Response(
            200, json={"type": "access_token", "user": {"id": "u1"}}
        )
    )
    out = await whoami(MiroClient("t"))
    assert out["user"]["id"] == "u1"


@respx.mock
async def test_wrapper_injects_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respx.get("https://api.miro.com/v1/oauth-token").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True},
            headers={"x-ratelimit-remaining": "42"},
        )
    )
    server._client = None
    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok")
    spec = TOOLS["whoami"]
    wrapper = server._make_wrapper(spec)
    out = await wrapper()
    assert out["rate_limit"]["x-ratelimit-remaining"] == "42"
    server._client = None
