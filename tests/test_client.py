from __future__ import annotations

import httpx
import pytest
import respx

from miro_mcp.client import (
    MAX_RETRIES,
    MiroApiError,
    MiroAuthError,
    MiroClient,
    MiroRateLimitError,
    load_token,
)

BASE = "https://api.miro.com"


@pytest.fixture
def client() -> MiroClient:
    return MiroClient("test-token")


def test_token_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "env-token")
    assert load_token() == "env-token"


def test_token_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("MIRO_ACCESS_TOKEN", raising=False)
    env_file = tmp_path / "miro.env"
    env_file.write_text("# comment\nexport MIRO_ACCESS_TOKEN='file-token'\nOTHER=1\n")
    monkeypatch.setenv("MIRO_ENV_FILE", str(env_file))
    assert load_token() == "file-token"


def test_token_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("MIRO_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("MIRO_ENV_FILE", str(tmp_path / "nope.env"))
    with pytest.raises(MiroAuthError):
        load_token()


def test_token_missing_key_in_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("MIRO_ACCESS_TOKEN", raising=False)
    env_file = tmp_path / "miro.env"
    env_file.write_text("SOMETHING_ELSE=1\n")
    monkeypatch.setenv("MIRO_ENV_FILE", str(env_file))
    with pytest.raises(MiroAuthError):
        load_token()


@respx.mock
async def test_get_json(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(200, json={"id": "b1"})
    )
    assert await client.get("/v2/boards/b1") == {"id": "b1"}


@respx.mock
async def test_auth_header_sent(client: MiroClient) -> None:
    route = respx.get(f"{BASE}/v1/oauth-token").mock(
        return_value=httpx.Response(200, json={"type": "access_token"})
    )
    await client.get("/v1/oauth-token")
    assert route.calls.last.request.headers["authorization"] == "Bearer test-token"


@respx.mock
async def test_429_retries_with_retry_after(client: MiroClient) -> None:
    route = respx.get(f"{BASE}/v2/boards/b1").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"id": "b1"}),
        ]
    )
    assert await client.get("/v2/boards/b1") == {"id": "b1"}
    assert route.call_count == 2


@respx.mock
async def test_retry_after_header_sets_delay(client: MiroClient) -> None:
    resp = httpx.Response(429, headers={"retry-after": "7"})
    assert client._throttle_delay(resp) == 7.0
    resp_no_header = httpx.Response(429)
    client._rl_strikes = 3
    assert client._throttle_delay(resp_no_header) == 8.0


@respx.mock
async def test_429_exhaustion_raises(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after": "0"},
            json={"message": "rate limited"},
        )
    )
    with pytest.raises(MiroRateLimitError):
        await client.get("/v2/boards/b1")


@respx.mock
@pytest.mark.parametrize("status", [502, 503, 504])
async def test_5xx_retry_then_success(client: MiroClient, status: int) -> None:
    route = respx.get(f"{BASE}/v2/boards/b1").mock(
        side_effect=[
            httpx.Response(status),
            httpx.Response(200, json={"id": "b1"}),
        ]
    )
    assert await client.get("/v2/boards/b1") == {"id": "b1"}
    assert route.call_count == 2


@respx.mock
async def test_5xx_exhaustion(client: MiroClient) -> None:
    route = respx.get(f"{BASE}/v2/boards/b1").mock(return_value=httpx.Response(503))
    with pytest.raises(MiroApiError) as exc:
        await client.get("/v2/boards/b1")
    assert exc.value.status == 503
    assert route.call_count == MAX_RETRIES + 1


@respx.mock
async def test_400_raises_api_error(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/bad").mock(
        return_value=httpx.Response(404, json={"message": "board not found"})
    )
    with pytest.raises(MiroApiError) as exc:
        await client.get("/v2/boards/bad")
    assert exc.value.status == 404
    assert "board not found" in str(exc.value)


@respx.mock
async def test_rate_limit_headers_captured(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "b1"},
            headers={
                "x-ratelimit-limit": "100000",
                "x-ratelimit-remaining": "99900",
            },
        )
    )
    await client.get("/v2/boards/b1")
    assert client.rate_limit["x-ratelimit-remaining"] == "99900"


@respx.mock
async def test_204_returns_empty_dict(client: MiroClient) -> None:
    respx.delete(f"{BASE}/v2/boards/b1/items/i1").mock(return_value=httpx.Response(204))
    assert await client.delete("/v2/boards/b1/items/i1") == {}


@respx.mock
async def test_iter_cursor_pages(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1/items").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"data": [{"id": "a"}, {"id": "b"}], "cursor": "next1"},
            ),
            httpx.Response(200, json={"data": [{"id": "c"}]}),
        ]
    )
    items = [i async for i in client.iter_cursor("/v2/boards/b1/items")]
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert respx.calls.last.request.url.params["cursor"] == "next1"


@respx.mock
async def test_iter_cursor_max_pages(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards/b1/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "a"}], "cursor": "more"})
    )
    items = [i async for i in client.iter_cursor("/v2/boards/b1/items", max_pages=1)]
    assert len(items) == 1


@respx.mock
async def test_iter_offset_pages(client: MiroClient) -> None:
    respx.get(f"{BASE}/v2/boards").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": [{"id": "a"}],
                    "total": 2,
                    "offset": 0,
                    "limit": 1,
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [{"id": "b"}],
                    "total": 2,
                    "offset": 1,
                    "limit": 1,
                },
            ),
        ]
    )
    items = [i async for i in client.iter_offset("/v2/boards", limit=1)]
    assert [i["id"] for i in items] == ["a", "b"]
    assert respx.calls.last.request.url.params["offset"] == "1"


@respx.mock
async def test_multipart_files_post(client: MiroClient) -> None:
    route = respx.post(f"{BASE}/v2/boards/b1/images").mock(
        return_value=httpx.Response(201, json={"id": "img1"})
    )
    await client.post(
        "/v2/boards/b1/images",
        files={
            "data": (None, '{"position":{"x":1,"y":2}}', "application/json"),
            "resource": ("a.png", b"\x89PNG", "image/png"),
        },
    )
    body = route.calls.last.request.content
    assert b'name="resource"; filename="a.png"' in body
    assert b"Content-Type: image/png" in body
    assert b'name="data"' in body
    assert b'{"position":{"x":1,"y":2}}' in body
