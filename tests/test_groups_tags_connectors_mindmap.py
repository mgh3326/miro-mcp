from __future__ import annotations

import json

import httpx
import pytest
import respx

from miro_mcp.client import MiroClient
from miro_mcp.tools import connectors, groups, mindmap, tags

BASE = "https://api.miro.com"
B = "/v2/boards/b1"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


def body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


# --- connectors -----------------------------------------------------------


@respx.mock
async def test_list_connectors(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/connectors").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "c1"}], "cursor": "c9"})
    )
    out = await connectors.list_connectors(client, "b1")
    assert out["items"][0]["id"] == "c1"
    assert out["cursor"] == "c9"


@respx.mock
async def test_create_connector(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/connectors").mock(
        return_value=httpx.Response(201, json={"id": "cn1"})
    )
    await connectors.create_connector(
        client, "b1", "i1", "i2", caption="link", end_stroke_cap="arrow"
    )
    b = body(route)
    assert b["startItem"] == {"id": "i1"}
    assert b["endItem"] == {"id": "i2"}
    assert b["captions"] == [{"content": "link"}]
    assert b["style"]["endStrokeCap"] == "arrow"


@respx.mock
async def test_update_connector(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}{B}/connectors/cn1").mock(
        return_value=httpx.Response(200, json={"id": "cn1"})
    )
    await connectors.update_connector(client, "b1", "cn1", stroke_style="dashed")
    assert body(route) == {"style": {"strokeStyle": "dashed"}}


@respx.mock
async def test_delete_connector_guard(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/connectors/cn1").mock(
        return_value=httpx.Response(204)
    )
    out = await connectors.delete_connector(client, "b1", "cn1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0
    out = await connectors.delete_connector(client, "b1", "cn1", confirm=True)
    assert out == {"deleted": "cn1"}


# --- groups ---------------------------------------------------------------


@respx.mock
async def test_create_group(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/groups").mock(
        return_value=httpx.Response(201, json={"id": "g1", "type": "group"})
    )
    out = await groups.create_group(client, "b1", ["i1", "i2"])
    assert out["id"] == "g1"
    assert body(route) == {"data": {"items": ["i1", "i2"]}}


@respx.mock
async def test_get_group_items(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/groups/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "i1"}]})
    )
    out = await groups.get_group_items(client, "b1", "g1")
    assert out["items"][0]["id"] == "i1"
    assert respx.calls.last.request.url.params["group_item_id"] == "g1"


@respx.mock
async def test_update_group(client: MiroClient) -> None:
    route = respx.put(f"{BASE}{B}/groups/g1").mock(
        return_value=httpx.Response(200, json={"id": "g2"})
    )
    await groups.update_group(client, "b1", "g1", ["i3"])
    assert body(route) == {"data": {"items": ["i3"]}}


@respx.mock
async def test_ungroup_guard(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/groups/g1").mock(return_value=httpx.Response(204))
    out = await groups.ungroup(client, "b1", "g1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


# --- tags -----------------------------------------------------------------


@respx.mock
async def test_list_and_create_tag(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/tags").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "t1"}]})
    )
    assert (await tags.list_tags(client, "b1"))["items"][0]["id"] == "t1"
    route = respx.post(f"{BASE}{B}/tags").mock(
        return_value=httpx.Response(201, json={"id": "t2"})
    )
    await tags.create_tag(client, "b1", "urgent", fill_color="red")
    assert body(route) == {"title": "urgent", "fillColor": "red"}


@respx.mock
async def test_attach_detach_tag(client: MiroClient) -> None:
    attach = respx.post(f"{BASE}{B}/items/i1").mock(return_value=httpx.Response(204))
    out = await tags.attach_tag(client, "b1", "i1", "t1")
    assert out["attached"] == "t1"
    assert attach.calls.last.request.url.params["tag_id"] == "t1"

    detach = respx.delete(f"{BASE}{B}/items/i1").mock(return_value=httpx.Response(204))
    out = await tags.detach_tag(client, "b1", "i1", "t1")
    assert out["error"] == "confirmation_required"
    assert detach.call_count == 0
    out = await tags.detach_tag(client, "b1", "i1", "t1", confirm=True)
    assert out["detached"] == "t1"
    assert detach.calls.last.request.url.params["tag_id"] == "t1"


@respx.mock
async def test_get_item_tags(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items/i1/tags").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "t1"}]})
    )
    assert (await tags.get_item_tags(client, "b1", "i1"))["count"] == 1


@respx.mock
async def test_delete_tag_guard(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/tags/t1").mock(return_value=httpx.Response(204))
    out = await tags.delete_tag(client, "b1", "t1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


# --- mindmap --------------------------------------------------------------


@respx.mock
async def test_mindmap_crud(client: MiroClient) -> None:
    exp = f"{BASE}/v2-experimental/boards/b1/mindmap_nodes"
    respx.get(exp).mock(return_value=httpx.Response(200, json={"data": [{"id": "n1"}]}))
    assert (await mindmap.list_mindmap_nodes(client, "b1"))["items"]
    route = respx.post(exp).mock(return_value=httpx.Response(201, json={"id": "n2"}))
    await mindmap.create_mindmap_node(
        client, "b1", "idea", x=0, y=0, parent_node_id="n1"
    )
    b = body(route)
    assert b["data"]["nodeView"]["data"]["content"] == "idea"
    assert b["parent"] == {"id": "n1"}
    respx.delete(f"{exp}/n2").mock(return_value=httpx.Response(204))
    out = await mindmap.delete_mindmap_node(client, "b1", "n2")
    assert out["error"] == "confirmation_required"
    out = await mindmap.delete_mindmap_node(client, "b1", "n2", confirm=True)
    assert out == {"deleted": "n2"}
