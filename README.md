# miro-mcp

An open-source MCP server for the [Miro REST API v2](https://developers.miro.com),
built with Python 3.12, the official `mcp` SDK (FastMCP), and `httpx`.

> **Status:** v1 under construction. This README documents the planned surface;
> the tool table below is updated as each PR lands.

## Why

The hosted Miro MCP connector can hit daily call caps on free plans. Talking to
the REST API directly uses per-minute rate-limit credits instead, and this
server covers the full public REST surface — including local image upload.

## Auth

Set `MIRO_ACCESS_TOKEN`, or create a dotenv file at
`~/.config/miro-mcp/miro.env` (override with `MIRO_ENV_FILE`):

```dotenv
MIRO_ACCESS_TOKEN=your_token_here
```

The token is never printed or logged.

## Install

```bash
uvx --from git+https://github.com/mgh3326/miro-mcp miro-mcp --help
```

(Full install, Claude Code/Desktop registration, and the tool reference land
with the feature PRs.)

## License

MIT — see [LICENSE](LICENSE).
