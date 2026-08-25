import pytest
from httpx import AsyncClient

ADMIN_HEADERS = {"X-Admin-API-Key": "test_admin_secret_key"}


@pytest.mark.asyncio
async def test_admin_auth_verify(async_client: AsyncClient):
    # Valid key
    res = await async_client.post(
        "/admin/auth/verify",
        json={"admin_api_key": "test_admin_secret_key"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["authenticated"] is True

    # Invalid key
    res_invalid = await async_client.post(
        "/admin/auth/verify",
        json={"admin_api_key": "wrong_key"},
    )
    assert res_invalid.status_code == 401


@pytest.mark.asyncio
async def test_admin_dashboard_stats(async_client: AsyncClient, sample_tenant_and_key: dict):
    res = await async_client.get("/admin/stats", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()["data"]

    assert "metrics" in data
    assert "chart_data" in data
    assert data["metrics"]["total_tenants"] >= 1
    assert data["metrics"]["active_keys"] >= 1


@pytest.mark.asyncio
async def test_admin_orders_and_webhooks_listing(async_client: AsyncClient, sample_tenant_and_key: dict):
    # List orders
    orders_res = await async_client.get("/admin/orders", headers=ADMIN_HEADERS)
    assert orders_res.status_code == 200
    assert isinstance(orders_res.json()["data"], list)

    # List webhooks
    wh_res = await async_client.get("/admin/webhooks", headers=ADMIN_HEADERS)
    assert wh_res.status_code == 200
    assert isinstance(wh_res.json()["data"], list)
