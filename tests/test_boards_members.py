from __future__ import annotations

import httpx
import pytest
import respx

from miro_mcp.client import MiroClient
from miro_mcp.tools import boards, members

BASE = "https://api.miro.com"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


@respx.mock
async def test_list_boards_compact(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "b1",
                        "name": "Roadmap",
                        "viewLink": "https://miro.com/app/board/b1",
                        "owner": {"id": "u1"},
                        "team": {"id": "t1"},
                    }
                ],
                "total": 1,
                "offset": 0,
            },
        )
    )
    out = await boards.list_boards(client)
    assert out["count"] == 1
    assert out["items"][0]["id"] == "b1"
    assert out["items"][0]["owner_id"] == "u1"
    assert respx.calls.last.request.url.params["limit"] == "20"


@respx.mock
async def test_list_boards_filters(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0})
    )
    await boards.list_boards(client, query="beta", owner="me", sort="alphabetically")
    params = respx.calls.last.request.url.params
    assert params["query"] == "beta"
    assert params["owner"] == "me"
    assert params["sort"] == "alphabetically"


@respx.mock
async def test_list_boards_fetch_all(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"id": "a"}], "total": 2, "offset": 0}),
            httpx.Response(200, json={"data": [{"id": "b"}], "total": 2, "offset": 1}),
        ]
    )
    out = await boards.list_boards(client, fetch_all=True, limit=1)
    assert out["count"] == 2


@respx.mock
async def test_get_board(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(200, json={"id": "b1", "name": "B"})
    )
    out = await boards.get_board(client, "b1")
    assert out["name"] == "B"


@respx.mock
async def test_create_board(client: MiroClient) -> None:
    route = respx.post(f"{BASE}/v2/boards").mock(
        return_value=httpx.Response(201, json={"id": "b2"})
    )
    out = await boards.create_board(client, "New", team_id="t1")
    assert out["id"] == "b2"
    import json

    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "New", "teamId": "t1"}


@respx.mock
async def test_copy_board(client: MiroClient) -> None:
    route = respx.put(f"{BASE}/v2/boards").mock(
        return_value=httpx.Response(201, json={"id": "b3"})
    )
    out = await boards.copy_board(client, "b1", name="Copy")
    assert out["id"] == "b3"
    assert route.calls.last.request.url.params["copy_from"] == "b1"


@respx.mock
async def test_update_board(client: MiroClient) -> None:
    route = respx.patch(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(200, json={"id": "b1"})
    )
    import json

    await boards.update_board(client, "b1", name="Renamed")
    assert json.loads(route.calls.last.request.content) == {"name": "Renamed"}


@respx.mock
async def test_delete_board_requires_confirm(client: MiroClient) -> None:
    route = respx.delete(f"{BASE}/v2/boards/b1")
    out = await boards.delete_board(client, "b1")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


@respx.mock
async def test_delete_board_confirmed(client: MiroClient) -> None:
    respx.delete(f"{BASE}/v2/boards/b1").mock(return_value=httpx.Response(204))
    out = await boards.delete_board(client, "b1", confirm=True)
    assert out == {"deleted": "b1"}


@respx.mock
async def test_list_board_members(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1/members").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": "m1", "role": "editor"}],
                "total": 1,
                "offset": 0,
            },
        )
    )
    out = await members.list_board_members(client, "b1")
    assert out["items"][0]["role"] == "editor"


@respx.mock
async def test_get_board_member(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1/members/m1").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    out = await members.get_board_member(client, "b1", "m1")
    assert out["id"] == "m1"


@respx.mock
async def test_share_board_requires_confirm(client: MiroClient) -> None:
    route = respx.post(f"{BASE}/v2/boards/b1/members")
    out = await members.share_board(client, "b1", ["a@b.c"])
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


@respx.mock
async def test_share_board_confirmed(client: MiroClient) -> None:
    import json

    route = respx.post(f"{BASE}/v2/boards/b1/members").mock(
        return_value=httpx.Response(201, json={"successful": ["a@b.c"], "failed": []})
    )
    out = await members.share_board(
        client, "b1", ["a@b.c"], role="editor", confirm=True
    )
    assert out["successful"] == ["a@b.c"]
    body = json.loads(route.calls.last.request.content)
    assert body["role"] == "editor"
    assert body["emails"] == ["a@b.c"]


@respx.mock
async def test_update_board_member_requires_confirm(
    client: MiroClient,
) -> None:
    route = respx.patch(f"{BASE}/v2/boards/b1/members/m1")
    out = await members.update_board_member(client, "b1", "m1", "viewer")
    assert out["error"] == "confirmation_required"
    assert route.call_count == 0


@respx.mock
async def test_remove_board_member_confirmed(client: MiroClient) -> None:
    respx.delete(f"{BASE}/v2/boards/b1/members/m1").mock(
        return_value=httpx.Response(204)
    )
    out = await members.remove_board_member(client, "b1", "m1", confirm=True)
    assert out == {"removed": "m1"}
