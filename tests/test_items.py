from __future__ import annotations

import json

import httpx
import pytest
import respx

from miro_mcp.client import MiroClient
from miro_mcp.tools import items

BASE = "https://api.miro.com"
B = "/v2/boards/b1"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


def body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


@respx.mock
async def test_list_items_compact(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "i1",
                        "type": "sticky_note",
                        "position": {"x": 1, "y": 2},
                        "data": {"content": "<p>hello</p>"},
                    }
                ],
                "cursor": "c2",
            },
        )
    )
    out = await items.list_items(client, "b1", type="sticky_note", limit=10)
    assert out["items"][0]["text"] == "hello"
    assert out["cursor"] == "c2"
    p = respx.calls.last.request.url.params
    assert p["type"] == "sticky_note"
    assert p["limit"] == "10"


@respx.mock
async def test_list_items_in_frame(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    await items.list_items(client, "b1", parent_item_id="f1")
    assert respx.calls.last.request.url.params["parent_item_id"] == "f1"


@respx.mock
async def test_list_items_fetch_all(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"id": "a"}], "cursor": "n1"}),
            httpx.Response(200, json={"data": [{"id": "b"}]}),
        ]
    )
    out = await items.list_items(client, "b1", fetch_all=True)
    assert out["count"] == 2


@respx.mock
async def test_get_item(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1"})
    )
    assert (await items.get_item(client, "b1", "i1"))["id"] == "i1"


@respx.mock
async def test_search_items(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "1", "data": {"content": "<p>Alpha</p>"}},
                    {"id": "2", "data": {"title": "Beta"}},
                ]
            },
        )
    )
    out = await items.search_items(client, "b1", "alpha")
    assert out["count"] == 1
    assert out["items"][0]["id"] == "1"


@respx.mock
async def test_update_item_position(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}{B}/items/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1"})
    )
    await items.update_item_position(client, "b1", "i1", x=5, y=6)
    assert body(route)["position"] == {
        "x": 5,
        "y": 6,
        "origin": "center",
        "relativeTo": "canvas_center",
    }


@respx.mock
async def test_update_item_position_empty(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}{B}/items/i1")
    out = await items.update_item_position(client, "b1", "i1")
    assert out["error"] == "nothing_to_update"
    assert route.call_count == 0


@respx.mock
async def test_delete_item_guard(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/items/i1")
    out = await items.delete_item(client, "b1", "i1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


@respx.mock
async def test_delete_item_confirmed(client: MiroClient) -> None:
    respx.delete(f"{BASE}{B}/items/i1").mock(return_value=httpx.Response(204))
    assert await items.delete_item(client, "b1", "i1", confirm=True) == {
        "deleted": "i1"
    }


@respx.mock
async def test_get_items_by_tag(client: MiroClient) -> None:
    respx.get(f"{BASE}{B}/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "i1"}], "total": 1})
    )
    await items.get_items_by_tag(client, "b1", "t1")
    assert respx.calls.last.request.url.params["tag_id"] == "t1"


@respx.mock
async def test_bulk_create(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/items/bulk").mock(
        return_value=httpx.Response(201, json={"data": [{"id": "i1"}]})
    )
    payload = [{"type": "sticky_note", "data": {"content": "x"}}]
    out = await items.bulk_create_items(client, "b1", payload)
    assert out["data"][0]["id"] == "i1"
    assert body(route) == payload


async def test_bulk_create_too_many(client: MiroClient) -> None:
    out = await items.bulk_create_items(client, "b1", [{}] * 21)
    assert out["error"] == "too_many_items"


@respx.mock
async def test_bulk_update_typed_and_generic(client: MiroClient) -> None:
    respx.patch(f"{BASE}{B}/sticky_notes/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1"})
    )
    respx.patch(f"{BASE}{B}/items/i2").mock(
        return_value=httpx.Response(200, json={"id": "i2"})
    )
    out = await items.bulk_update_items(
        client,
        "b1",
        [
            {
                "item_id": "i1",
                "item_type": "sticky_note",
                "data": {"content": "new"},
            },
            {"item_id": "i2", "position": {"x": 1, "y": 1}},
        ],
    )
    assert out["updated"] == 2
    assert out["failed"] == 0


@respx.mock
async def test_bulk_update_partial_failure(client: MiroClient) -> None:
    respx.patch(f"{BASE}{B}/items/bad").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    out = await items.bulk_update_items(
        client, "b1", [{"item_id": "bad", "position": {"x": 0, "y": 0}}]
    )
    assert out["failed"] == 1
    assert out["results"][0]["ok"] is False


@respx.mock
async def test_bulk_delete_guard_and_confirmed(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}{B}/items/i1").mock(return_value=httpx.Response(204))
    out = await items.bulk_delete_items(client, "b1", ["i1"])
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0
    out = await items.bulk_delete_items(client, "b1", ["i1"], confirm=True)
    assert out["deleted"] == 1


@respx.mock
async def test_create_sticky_note(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/sticky_notes").mock(
        return_value=httpx.Response(201, json={"id": "s1"})
    )
    await items.create_sticky_note(
        client, "b1", "hi", x=1, y=2, fill_color="yellow", width=300
    )
    b = body(route)
    assert b["data"] == {"content": "hi", "shape": "square"}
    assert b["style"]["fillColor"] == "yellow"
    assert b["geometry"] == {"width": 300}
    assert b["position"]["x"] == 1


@respx.mock
async def test_update_sticky_note_partial(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}{B}/sticky_notes/s1").mock(
        return_value=httpx.Response(200, json={"id": "s1"})
    )
    await items.update_sticky_note(client, "b1", "s1", content="new")
    b = body(route)
    assert b == {"data": {"content": "new"}}


@respx.mock
async def test_create_shape(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/shapes").mock(
        return_value=httpx.Response(201, json={"id": "sh1"})
    )
    await items.create_shape(
        client, "b1", x=0, y=0, shape="circle", fill_color="#ff0000"
    )
    b = body(route)
    assert b["data"]["shape"] == "circle"
    assert b["style"]["fillColor"] == "#ff0000"


@respx.mock
async def test_create_text_with_rotation(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/texts").mock(
        return_value=httpx.Response(201, json={"id": "t1"})
    )
    await items.create_text(client, "b1", "txt", x=0, y=0, rotation=90)
    b = body(route)
    assert b["rotation"] == 90


@respx.mock
async def test_create_card(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/cards").mock(
        return_value=httpx.Response(201, json={"id": "c1"})
    )
    await items.create_card(client, "b1", "T", x=0, y=0, due_date="2026-12-31")
    assert body(route)["data"]["dueDate"] == "2026-12-31"


@respx.mock
async def test_create_app_card(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/app_cards").mock(
        return_value=httpx.Response(201, json={"id": "ac1"})
    )
    await items.create_app_card(
        client, "b1", "T", x=0, y=0, status="connected", fields=["a", "b"]
    )
    b = body(route)
    assert b["data"]["status"] == "connected"
    assert b["data"]["fields"] == [{"value": "a"}, {"value": "b"}]


@respx.mock
async def test_create_frame(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/frames").mock(
        return_value=httpx.Response(201, json={"id": "f1"})
    )
    await items.create_frame(client, "b1", "F", x=0, y=0, width=800, height=600)
    b = body(route)
    assert b["data"]["title"] == "F"
    assert b["geometry"] == {"width": 800, "height": 600}


@respx.mock
async def test_create_embed(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/embeds").mock(
        return_value=httpx.Response(201, json={"id": "e1"})
    )
    await items.create_embed(client, "b1", "https://ex.com", x=0, y=0, mode="inline")
    assert body(route)["data"]["mode"] == "inline"


@respx.mock
async def test_create_document_from_url(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/documents").mock(
        return_value=httpx.Response(201, json={"id": "d1"})
    )
    await items.create_document_from_url(
        client, "b1", "https://ex.com/a.pdf", x=1, y=1, title="Doc"
    )
    b = body(route)
    assert b["data"] == {"documentUrl": "https://ex.com/a.pdf", "title": "Doc"}


@respx.mock
async def test_upload_document(client: MiroClient, tmp_path) -> None:
    f = tmp_path / "spec.pdf"
    f.write_bytes(b"%PDF-1.4")
    route = respx.post(f"{BASE}{B}/documents").mock(
        return_value=httpx.Response(201, json={"id": "d1"})
    )
    out = await items.upload_document(client, "b1", str(f), x=5, y=5, title="S")
    assert out["id"] == "d1"
    content = route.calls.last.request.content
    assert b'name="resource"; filename="spec.pdf"' in content
    assert b'"title": "S"' in content


async def test_upload_document_missing_file(client: MiroClient) -> None:
    with pytest.raises(FileNotFoundError):
        await items.upload_document(client, "b1", "/no/such.pdf", x=0, y=0)


@respx.mock
async def test_upload_image(client: MiroClient, tmp_path) -> None:
    f = tmp_path / "shot.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    route = respx.post(f"{BASE}{B}/images").mock(
        return_value=httpx.Response(201, json={"id": "img1"})
    )
    out = await items.upload_image(
        client,
        "b1",
        str(f),
        x=100,
        y=200,
        width=400,
        title="Shot",
        parent_frame_id="f1",
    )
    assert out["id"] == "img1"
    content = route.calls.last.request.content
    assert b'name="resource"; filename="shot.png"' in content
    assert b"Content-Type: image/png" in content
    meta = json.loads(
        content.split(b'name="data"')[-1]
        .split(b"\r\n\r\n", 1)[1]
        .rsplit(b"\r\n--", 1)[0]
    )
    assert meta["position"]["x"] == 100
    assert meta["geometry"] == {"width": 400}
    assert meta["parent"] == {"id": "f1"}


@respx.mock
async def test_create_image_from_url(client: MiroClient) -> None:
    route = respx.post(f"{BASE}{B}/images").mock(
        return_value=httpx.Response(201, json={"id": "img2"})
    )
    await items.create_image_from_url(client, "b1", "https://ex.com/i.png", x=0, y=0)
    assert body(route)["data"]["url"] == "https://ex.com/i.png"


@respx.mock
async def test_update_image(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}{B}/images/img1").mock(
        return_value=httpx.Response(200, json={"id": "img1"})
    )
    await items.update_image(client, "b1", "img1", title="New")
    assert body(route) == {"data": {"title": "New"}}


@respx.mock
async def test_code_widget_crud(client: MiroClient) -> None:
    exp = f"{BASE}/v2-experimental/boards/b1/code_widgets"
    respx.get(exp).mock(return_value=httpx.Response(200, json={"data": [{"id": "w1"}]}))
    out = await items.list_code_widgets(client, "b1")
    assert out["items"][0]["id"] == "w1"
    route = respx.post(exp).mock(return_value=httpx.Response(201, json={"id": "w2"}))
    await items.create_code_widget(
        client, "b1", "print(1)", x=0, y=0, language="python"
    )
    assert body(route)["data"]["language"] == "python"
