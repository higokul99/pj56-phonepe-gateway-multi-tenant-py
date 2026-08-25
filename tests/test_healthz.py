import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_endpoint(async_client: AsyncClient):
    res = await async_client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert "version" in data["data"]
