from __future__ import annotations

import pytest
import asyncio

from app.core.firewall import FirewallHTTPClient, OutboundBlocked


@pytest.mark.asyncio
async def test_firewall_blocks_disallowed_port() -> None:
    async with FirewallHTTPClient(["example.com"], ports=[80]) as fw:
        with pytest.raises(OutboundBlocked):
            await fw.get("https://example.com:443")

