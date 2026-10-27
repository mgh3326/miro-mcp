from __future__ import annotations

import json

import httpx
import pytest
import respx

from miro_mcp.client import MiroClient
from miro_mcp.tools import export

BASE = "https://api.miro.com"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


def body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


@respx.mock
async def test_get_board_thumbnail(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "b1",
                "picture": {"imageUrl": "https://cdn.miro.com/thumb.png"},
            },
        )
    )
    out = await export.get_board_thumbnail(client, "b1")
    assert out["image_url"] == "https://cdn.miro.com/thumb.png"


@respx.mock
async def test_create_export_job(client: MiroClient) -> None:
    route = respx.post(f"{BASE}/v2/orgs/o1/boards/export/jobs").mock(
        return_value=httpx.Response(200, json={"jobId": "j1"})
    )
    out = await export.create_board_export_job(client, "o1", ["b1", "b2"], format="PDF")
    assert out["jobId"] == "j1"
    assert body(route) == {"boardIds": ["b1", "b2"], "boardFormat": "PDF"}


@respx.mock
async def test_export_job_status_and_results(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/orgs/o1/boards/export/jobs/j1").mock(
        return_value=httpx.Response(200, json={"status": "finished"})
    )
    assert (await export.get_board_export_job_status(client, "o1", "j1"))[
        "status"
    ] == "finished"
    respx.get(f"{BASE}/v2/orgs/o1/boards/export/jobs/j1/results").mock(
        return_value=httpx.Response(
            200, json={"results": [{"url": "https://dl/1.zip"}]}
        )
    )
    out = await export.get_board_export_job_results(client, "o1", "j1")
    assert out["results"][0]["url"] == "https://dl/1.zip"


@respx.mock
async def test_list_export_jobs(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/orgs/o1/boards/export/jobs").mock(
        return_value=httpx.Response(200, json={"data": [{"jobId": "j1"}], "total": 1})
    )
    out = await export.list_board_export_jobs(client, "o1")
    assert out["items"][0]["jobId"] == "j1"
