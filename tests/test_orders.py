import pytest
import respx
import httpx
from httpx import AsyncClient, Response
from app.config import get_settings

settings = get_settings()


@pytest.mark.asyncio
@respx.mock
async def test_create_order_and_idempotency(
    async_client: AsyncClient, sample_tenant_and_key: dict
):
    raw_api_key = sample_tenant_and_key["raw_api_key"]

    # Mock PhonePe OAuth Token Endpoint
    respx.post(settings.PHONEPE_SANDBOX_AUTH_URL).mock(
        return_value=Response(
            200,
            json={
                "access_token": "mock_phonepe_access_token_abc123",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )

    # Mock PhonePe Standard Checkout / Pay Endpoint
    checkout_endpoint = f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/checkout/init"
    checkout_route = respx.post(checkout_endpoint).mock(
        return_value=Response(
            200,
            json={
                "success": True,
                "code": "PAYMENT_INITIATED",
                "data": {
                    "orderId": "PP_TXN_998877",
                    "redirectUrl": "https://mercury-tst.phonepe.com/transact/pay?token=xyz",
                    "state": "PENDING",
                },
            },
        )
    )

    order_payload = {
        "merchant_order_id": "ORD-METORA-001",
        "amount": 250000,  # ₹2500.00 in paise
        "currency": "INR",
        "redirect_url": "https://site.example.com/checkout/complete",
        "metadata": {"customer_name": "Alice", "item_count": 2},
    }

    # 1. Create order for the first time
    res = await async_client.post(
        "/v1/orders",
        json=order_payload,
        headers={"X-API-Key": raw_api_key},
    )
    assert res.status_code == 201
    data = res.json()["data"]

    assert data["merchant_order_id"] == "ORD-METORA-001"
    assert data["phonepe_order_id"] == "PP_TXN_998877"
    assert data["amount"] == 250000
    assert data["status"] == "PENDING"
    assert "mercury-tst.phonepe.com" in data["checkout_url"]
    assert checkout_route.call_count == 1

    # 2. Idempotency test: Call POST /v1/orders with the EXACT same merchant_order_id
    res_idempotent = await async_client.post(
        "/v1/orders",
        json=order_payload,
        headers={"X-API-Key": raw_api_key},
    )
    assert res_idempotent.status_code == 201
    data_idempotent = res_idempotent.json()["data"]

    # Should return the exact same order and NOT call PhonePe checkout again
    assert data_idempotent["id"] == data["id"]
    assert data_idempotent["phonepe_order_id"] == "PP_TXN_998877"
    assert checkout_route.call_count == 1  # No duplicate upstream request


@pytest.mark.asyncio
@respx.mock
async def test_get_order_status_with_sync(
    async_client: AsyncClient, sample_tenant_and_key: dict
):
    raw_api_key = sample_tenant_and_key["raw_api_key"]
    tenant = sample_tenant_and_key["tenant"]

    # Mock OAuth
    respx.post(settings.PHONEPE_SANDBOX_AUTH_URL).mock(
        return_value=Response(200, json={"access_token": "mock_token", "expires_in": 3600})
    )

    # Mock Checkout
    respx.post(f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/checkout/init").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "orderId": "PP_TXN_STATUS_TEST",
                    "redirectUrl": "https://mercury-tst.phonepe.com/pay",
                    "state": "PENDING",
                }
            },
        )
    )

    # Create Order
    await async_client.post(
        "/v1/orders",
        json={
            "merchant_order_id": "ORD-STATUS-002",
            "amount": 10000,
            "redirect_url": "https://site.example.com/return",
        },
        headers={"X-API-Key": raw_api_key},
    )

    # Mock PhonePe Order Status API returning PAYMENT_SUCCESS (COMPLETED)
    status_url = f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/orders/{tenant.phonepe_merchant_id}/ORD-STATUS-002/status"
    respx.get(status_url).mock(
        return_value=Response(
            200,
            json={
                "code": "PAYMENT_SUCCESS",
                "data": {
                    "transactionId": "PP_TXN_STATUS_TEST",
                    "amount": 10000,
                    "state": "COMPLETED",
                },
            },
        )
    )

    # Call GET /v1/orders/ORD-STATUS-002?force_sync=true
    status_res = await async_client.get(
        "/v1/orders/ORD-STATUS-002?force_sync=true",
        headers={"X-API-Key": raw_api_key},
    )
    assert status_res.status_code == 200
    status_data = status_res.json()["data"]

    assert status_data["merchant_order_id"] == "ORD-STATUS-002"
    assert status_data["status"] == "COMPLETED"
