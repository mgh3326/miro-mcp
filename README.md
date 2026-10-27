# miro-mcp

An open-source MCP server for the [Miro REST API v2](https://developers.miro.com/docs/miro-rest-api-introduction).
Python 3.12+, the official `mcp` SDK (FastMCP), `httpx`, stdio transport.

## Why

The hosted Miro MCP connector can hit daily call caps on free plans. The REST
API instead rate-limits per minute (our token showed `x-ratelimit-limit:
100000` credits/min), and this server covers the full public REST surface —
including **local image file upload**, which the hosted connector lacks.

## Install

```bash
# run straight from git (uvx caches it)
uvx --from git+https://github.com/mgh3326/miro-mcp miro-mcp

# or from PyPI (placeholder — not published yet)
uvx miro-mcp
```

Requires Python 3.12+ (uv handles this).

### Claude Code

```bash
claude mcp add miro -- uvx --from git+https://github.com/mgh3326/miro-mcp miro-mcp
```

### Claude Desktop / `.mcp.json`

```json
{
  "mcpServers": {
    "miro": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mgh3326/miro-mcp", "miro-mcp"]
    }
  }
}
```

## Setup: the Miro app and token

1. Go to https://miro.com/app/settings/ → **Your apps** → **Create new app**.
2. In the app settings, pick the OAuth scopes you need (see the table below).
3. Click **Install app and get OAuth token** for your team → copy the token.
4. Either export it or put it in the env file:

```bash
export MIRO_ACCESS_TOKEN=...
# or, persisted:
mkdir -p ~/.config/miro-mcp
echo 'MIRO_ACCESS_TOKEN=...' > ~/.config/miro-mcp/miro.env
```

`MIRO_ENV_FILE` overrides the env file location. The token is never printed
or logged.

### Scopes per tool group

| Tool group | Required scope |
|---|---|
| boards: get/list, items: get/list/search, tags: get, members: get, token context | `boards:read` |
| boards: create/copy/update/delete, items: create/update/delete/upload, tags: attach/detach/create, members: share/update/remove, connectors, groups, docs | `boards:write` |
| export jobs | Enterprise Discovery token (separate, see below) |

`identity:read`/`team:*`/admin scopes are **not** used — this server only
needs board scopes, plus the Enterprise Discovery token for export jobs.

## Tool profiles

Set `MIRO_MCP_PROFILE`:

- `full` (default) — all 77 tools.
- `essential` — a ~15-tool subset for cheaper prompts:
  `whoami`, `list_boards`, `get_board`, `list_items`, `get_item`,
  `search_items`, `create_sticky_note`, `create_shape`, `create_text`,
  `create_card`, `create_frame`, `create_connector`, `upload_image`,
  `attach_tag`, `delete_item`.

## Tools

### Boards & members
`list_boards`, `get_board`, `create_board`, `copy_board`, `update_board`,
`delete_board`† · `list_board_members`, `get_board_member`, `share_board`†,
`update_board_member`†, `remove_board_member`†

### Items
`list_items` (type/parent/cursor/fetch_all), `get_item`, `search_items`,
`get_items_by_tag`, `update_item_position`, `delete_item`†,
`bulk_create_items` (≤20 via `POST /items/bulk`), `bulk_update_items`,
`bulk_delete_items`†

Create + update per type: `create_/update_` × `sticky_note`, `shape`,
`text`, `card`, `app_card`, `frame`, `embed`, `document` (URL + file
upload), `image` (URL + **local file upload**), `code_widget` *(experimental)*

### Connectors, groups, tags
`list/get/create/update/delete_connector`† · `create_group`, `list_groups`,
`get_group`, `get_group_items`, `update_group`, `ungroup`† ·
`list_tags`, `create_tag`, `get_tag`, `update_tag`, `delete_tag`†,
`attach_tag`, `detach_tag`†, `get_item_tags`

### Mindmap *(experimental)*
`list/get/create/delete_mindmap_node` — uses `/v2-experimental` endpoints.

### Docs (doc format)
`create_doc` (markdown/html), `get_doc`, `delete_doc`†,
`replace_doc`† — docs are create/read/delete-only in REST; `replace_doc`
is a labeled delete+recreate (new item id).

### Export
`get_board_thumbnail` (any plan) · `list_board_export_jobs`,
`create_board_export_job` (SVG/PDF/HTML), `get_board_export_job_status`,
`get_board_export_job_results` — **Enterprise plan only**, using the
Discovery access token from Settings → Enterprise Integrations.

### Misc
`whoami` — token context (user, team, scopes).

† destructive or sharing-changing tools require `confirm=true`; without it
they return a `confirmation_required` error and make no HTTP call. Confirmed
deletes are logged (item ids, never the token).

## Not in the REST API (gaps)

The hosted Miro MCP has capabilities that the public REST API does not, so
this server honestly reports them as unavailable instead of faking:

- **Comments, tables, kanban, timeline** — no REST endpoints
- **Doc update** — REST is create/read/delete only (`replace_doc` bridges)
- **Webhooks** — the `/v2-experimental/webhooks/*` endpoints were
  [retired 2025-12](https://developers.miro.com/changelog) despite the API
  introduction still listing them
- **Mermaid/DSL diagram creation, canvas SVG read/write** — not in REST;
  see the roadmap

## Resilience

- 429 → honors `Retry-After`, else adaptive exponential backoff (consecutive
  throttles back off harder, reset on success)
- 502/503/504 → retried with exponential backoff (max 5 retries total)
- `x-ratelimit-*` headers are surfaced in tool results when Miro sends them
- Cursor and offset pagination handled transparently (`fetch_all` on list tools)

## Comparison

| Project | Lang | Tools | Notes |
|---|---|---|---|
| **miro-mcp** (this) | Python | 77 | full REST surface, profiles, confirm guards, local image/doc upload |
| [olgasafonova/miro-mcp-server](https://github.com/olgasafonova/miro-mcp-server) (MIT) | Go | ~110 | the coverage reference — incl. Mermaid→diagram, audit, tool search |
| [k-jarzyna/mcp-miro](https://github.com/k-jarzyna/mcp-miro) (Apache-2.0) | TS | ~40 | endpoint shapes reference |
| Official Miro MCP (hosted) | — | ~15 | comments/tables/kanban via private APIs; daily caps on free plan |

## Roadmap (v2, planned)

- Mermaid / DSL → native diagram with local layout
- Canvas SVG read & write
- HTTP transport (currently stdio only)
- Short response caching, circuit breaker

## Development

```bash
uv sync --group dev
uv run ruff check . && uv run ruff format .
uv run mypy src
uv run pytest -q        # mocked HTTP (respx), no token needed
```

Live smoke test once you have a token:

```bash
uv run scripts/smoke.py --board-id <BOARD_ID> [--image shot.png]
```

## License

MIT — see [LICENSE](LICENSE). All code is original; no third-party code was
ported (the referenced projects were used for endpoint coverage and design
research only).
