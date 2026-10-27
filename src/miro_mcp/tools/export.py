"""Export: board thumbnail plus Enterprise board export jobs.

The board export job endpoints are part of Miro's Discovery APIs and are
only available on the **Enterprise plan** with a Discovery access token
(created in Settings > Enterprise Integrations). On other plans they
return 403 — that is expected, not a bug.
"""

from __future__ import annotations

from typing import Any, Literal

from ..client import MiroClient
from ..registry import tool
from .common import drop_none, offset_result

ExportFormat = Literal["SVG", "HTML", "PDF"]


@tool()
async def get_board_thumbnail(client: MiroClient, board_id: str) -> dict[str, Any]:
    """Get the board's thumbnail image URL.

    Reads the board's ``picture`` field — a small rendered preview, not a
    full-fidelity export. For PDF/SVG use the Enterprise export job tools.
    """
    board = await client.get(f"/v2/boards/{board_id}")
    picture = board.get("picture") or {}
    return {
        "board_id": board_id,
        "image_url": picture.get("imageUrl"),
        "moderation_label": picture.get("moderationLabel"),
    }


@tool()
async def list_board_export_jobs(
    client: MiroClient,
    org_id: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List board export jobs for an organization.

    ENTERPRISE PLAN ONLY — requires a Discovery access token.
    """
    page = await client.get(
        f"/v2/orgs/{org_id}/boards/export/jobs",
        params={"limit": str(limit), "offset": str(offset)},
    )
    return offset_result(page, compact=False)


@tool()
async def create_board_export_job(
    client: MiroClient,
    org_id: str,
    board_ids: list[str],
    format: ExportFormat = "SVG",
) -> dict[str, Any]:
    """Start a board export job (up to 1000 boards).

    ENTERPRISE PLAN ONLY — requires a Discovery access token. ``format``
    is SVG (default), HTML, or PDF. Returns the job id; poll
    ``get_board_export_job_status`` then download via
    ``get_board_export_job_results`` (results live for 14 days).
    """
    body = drop_none({"boardIds": board_ids, "boardFormat": format})
    return await client.post(f"/v2/orgs/{org_id}/boards/export/jobs", json_body=body)


@tool()
async def get_board_export_job_status(
    client: MiroClient, org_id: str, job_id: str
) -> dict[str, Any]:
    """Get the status of a board export job.

    ENTERPRISE PLAN ONLY — requires a Discovery access token.
    """
    return await client.get(f"/v2/orgs/{org_id}/boards/export/jobs/{job_id}")


@tool()
async def get_board_export_job_results(
    client: MiroClient, org_id: str, job_id: str
) -> dict[str, Any]:
    """Get the download links of a finished board export job.

    ENTERPRISE PLAN ONLY — requires a Discovery access token.
    """
    return await client.get(f"/v2/orgs/{org_id}/boards/export/jobs/{job_id}/results")
