#!/usr/bin/env python3
"""Live smoke test for miro-mcp against a real Miro account.

Reads the token from MIRO_ACCESS_TOKEN or MIRO_ENV_FILE
(~/.config/miro-mcp/miro.env). Creates throwaway items on a board and
cleans them up afterwards.

    uv run scripts/smoke.py --board-id <BOARD_ID> [--image path.png]

Everything it creates is deleted again with confirm=True.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from miro_mcp.client import MiroClient, MiroError, load_token
from miro_mcp.tools import boards, docs, items, tags


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-id", required=True)
    parser.add_argument("--image", help="optional PNG/JPG path to upload")
    args = parser.parse_args()

    client = MiroClient(load_token())
    created: list[str] = []
    try:
        me = await client.get("/v1/oauth-token")
        team = (me.get("team") or {}).get("name", "?")
        print(f"token ok (team: {team})")

        board = await boards.get_board(client, args.board_id)
        print(f"board ok: {board.get('name')}")

        listing = await items.list_items(client, args.board_id, limit=10)
        print(f"items on board: {listing['count']} (sampled)")

        frame = await items.create_frame(
            client,
            args.board_id,
            "miro-mcp smoke",
            x=0,
            y=0,
            width=900,
            height=600,
        )
        created.append(frame["id"])
        print(f"frame created: {frame['id']}")

        sticky = await items.create_sticky_note(
            client,
            args.board_id,
            "smoke test — safe to delete",
            x=0,
            y=0,
            parent_frame_id=frame["id"],
        )
        created.append(sticky["id"])
        print(f"sticky created: {sticky['id']}")

        image_path = args.image
        if not image_path:
            import base64

            # 1x1 transparent PNG
            tmp = Path(tempfile.gettempdir()) / "miro-mcp-smoke.png"
            tmp.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlE"
                    "QVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                )
            )
            image_path = str(tmp)
        image = await items.upload_image(
            client,
            args.board_id,
            image_path,
            x=300,
            y=0,
            title="smoke",
            parent_frame_id=frame["id"],
        )
        created.append(image["id"])
        print(f"image uploaded: {image['id']}")

        doc = await docs.create_doc(
            client,
            args.board_id,
            "# smoke\n\nsafe to delete",
            x=0,
            y=300,
            parent_frame_id=frame["id"],
        )
        created.append(doc["id"])
        print(f"doc created: {doc['id']}")

        tag = await tags.create_tag(client, args.board_id, "smoke")
        await tags.attach_tag(client, args.board_id, sticky["id"], tag["id"])
        print(f"tag attached: {tag['id']}")

        print("cleaning up...")
        out = await items.bulk_delete_items(
            client, args.board_id, created, confirm=True
        )
        print(f"deleted {out['deleted']}/{len(created)} items")
        await tags.delete_tag(client, args.board_id, tag["id"], confirm=True)
        print("smoke OK")
        return 0
    except MiroError as exc:
        print(f"smoke FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
