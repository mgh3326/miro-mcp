from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry tests must not actually wait on backoff."""

    async def _sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)
