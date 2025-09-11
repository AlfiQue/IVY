import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.firewall import FirewallHTTPClient, OutboundBlocked  # noqa: E402


@pytest.mark.asyncio
async def test_firewall_block() -> None:
    async with FirewallHTTPClient([]) as fw:
        with pytest.raises(OutboundBlocked):
            await fw.get("https://example.com")


@pytest.mark.asyncio
async def test_firewall_close() -> None:
    fw = FirewallHTTPClient([])
    assert not fw.client.is_closed
    await fw.close()
    assert fw.client.is_closed
