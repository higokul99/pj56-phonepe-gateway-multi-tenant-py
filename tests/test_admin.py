import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decrypt_secret
from app.models.tenant import Tenant

ADMIN_HEADERS = {"X-Admin-API-Key": "test_admin_secret_key"}


@pytest.mark.asyncio
async def test_admin_authentication(async_client: AsyncClient):
    # Without admin key -> 401 / 422
    res = await async_client.get("/admin/tenants")
    assert res.status_code in (401, 422)

    # With wrong admin key -> 401
    res = await async_client.get("/admin/tenants", headers={"X-Admin-API-Key": "wrong_key"})
    assert res.status_code == 401
    data = res.json()
    assert data["error"]["code"] == "UNAUTHORIZED_ADMIN"

    # With valid admin key -> 200
    res = await async_client.get("/admin/tenants", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    assert res.json()["success"] is True


@pytest.mark.asyncio
async def test_create_tenant_and_verify_encryption(
    async_client: AsyncClient, db_session: AsyncSession
):
    raw_secret = "super_confidential_phonepe_secret_12345"
    payload = {
        "name": "Acme Brand Store",
        "phonepe_client_id": "ACME_CLIENT_ID_999",
        "phonepe_client_secret": raw_secret,
        "phonepe_merchant_id": "ACMEMERCHANT123",
        "phonepe_env": "sandbox",
        "webhook_url": "https://acme.example.com/webhook",
    }

    res = await async_client.post("/admin/tenants", json=payload, headers=ADMIN_HEADERS)
    assert res.status_code == 201
    res_data = res.json()["data"]
    tenant_id = res_data["id"]

    assert res_data["name"] == "Acme Brand Store"
    assert res_data["webhook_secret"].startswith("whsec_")

    # Verify that in the DB the secret is NOT stored in plain text
    db_tenant = await db_session.get(Tenant, tenant_id)
    assert db_tenant is not None
    assert db_tenant.phonepe_client_secret != raw_secret
    assert len(db_tenant.phonepe_client_secret) > 30

    # Verify decrypted value matches original
    decrypted = decrypt_secret(db_tenant.phonepe_client_secret)
    assert decrypted == raw_secret


@pytest.mark.asyncio
async def test_api_key_lifecycle(
    async_client: AsyncClient, sample_tenant_and_key: dict
):
    tenant = sample_tenant_and_key["tenant"]

    # 1. Issue new API key
    res = await async_client.post(
        f"/admin/tenants/{tenant.id}/keys",
        json={"environment": "live"},
        headers=ADMIN_HEADERS,
    )
    assert res.status_code == 201
    key_data = res.json()["data"]
    key_id = key_data["id"]
    raw_key = key_data["raw_api_key"]

    assert raw_key.startswith("pg_live_")
    assert key_data["key_prefix"] == raw_key[:12]

    # 2. List keys
    list_res = await async_client.get(
        f"/admin/tenants/{tenant.id}/keys",
        headers=ADMIN_HEADERS,
    )
    assert list_res.status_code == 200
    keys = list_res.json()["data"]
    assert any(k["id"] == key_id for k in keys)

    # 3. Revoke key
    revoke_res = await async_client.post(
        f"/admin/keys/{key_id}/revoke",
        headers=ADMIN_HEADERS,
    )
    assert revoke_res.status_code == 200

    # 4. Attempting to use revoked key should fail
    auth_res = await async_client.post(
        "/v1/orders",
        json={
            "merchant_order_id": "TEST-REVOKED-1",
            "amount": 5000,
            "redirect_url": "https://example.com/return",
        },
        headers={"X-API-Key": raw_key},
    )
    assert auth_res.status_code == 401
    assert auth_res.json()["error"]["code"] == "INVALID_API_KEY"
