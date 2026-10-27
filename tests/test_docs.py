from __future__ import annotations

import json

import httpx
import pytest
import respx

from miro_mcp.client import MiroClient
from miro_mcp.tools import docs

BASE = "https://api.miro.com"
B = "/v2/boards/b1"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


def body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


@respx.mock
async def test_create_doc_markdown(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/docs").mock(
        return_value=httpx.Response(201, json={"id": "d1"})
    )
    await docs.create_doc(client, "b1", "# Hello", x=10, y=20)
    b = body(route)
    assert b["data"] == {"contentType": "markdown", "content": "# Hello"}
    assert b["position"]["x"] == 10


@respx.mock
async def test_get_doc(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/docs/d1").mock(
        return_value=httpx.Response(200, json={"id": "d1", "data": {"content": "# H"}})
    )
    out = await docs.get_doc(client, "b1", "d1")
    assert out["data"]["content"] == "# H"


@respx.mock
async def test_delete_doc_guard(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/docs/d1").mock(return_value=httpx.Response(204))
    out = await docs.delete_doc(client, "b1", "d1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0
    out = await docs.delete_doc(client, "b1", "d1", confirm=True)
    assert out == {"deleted": "d1"}


@respx.mock
async def test_replace_doc_recreates(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/docs/d1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "d1",
                "data": {"contentType": "markdown", "content": "old"},
                "position": {"x": 5, "y": 6},
                "parent": {"id": "f1"},
            },
        )
    )
    respx.delete(f"{BASE}{B}/docs/d1").mock(return_value=httpx.Response(204))
    create = respx.post(f"{BASE}{B}/docs").mock(
        return_value=httpx.Response(201, json={"id": "d2"})
    )
    out = await docs.replace_doc(client, "b1", "d1", "new content", confirm=True)
    assert out["replaced"] == "d1"
    assert out["new_item"]["id"] == "d2"
    b = body(create)
    assert b["data"]["content"] == "new content"
    assert b["position"] == {"x": 5, "y": 6}
    assert b["parent"] == {"id": "f1"}


@respx.mock
async def test_replace_doc_guard(client: MiroClient) -> None:
    out = await docs.replace_doc(client, "b1", "d1", "x")
    assert out["error"] == "confirmation_required"
    assert "new id" in out["message"]
