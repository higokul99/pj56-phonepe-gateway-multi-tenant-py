import pytest
import respx
from httpx import AsyncClient, Response
from app.config import get_settings
from app.models.order import Order
from app.services.order_service import OrderService

settings = get_settings()


@pytest.mark.asyncio
@respx.mock
async def test_order_refund_lifecycle(
    async_client: AsyncClient, sample_tenant_and_key: dict, db_session
):
    raw_api_key = sample_tenant_and_key["raw_api_key"]
    tenant = sample_tenant_and_key["tenant"]

    # 1. Setup mock PhonePe OAuth & Checkout
    respx.post(settings.PHONEPE_SANDBOX_AUTH_URL).mock(
        return_value=Response(200, json={"access_token": "mock_token", "expires_in": 3600})
    )
    respx.post(f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/checkout/init").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "orderId": "PP_REFUND_ORDER_1",
                    "redirectUrl": "https://mercury-tst.phonepe.com/pay",
                    "state": "PENDING",
                }
            },
        )
    )

    # 2. Create Order
    await async_client.post(
        "/v1/orders",
        json={
            "merchant_order_id": "ORD-REF-001",
            "amount": 50000,
            "redirect_url": "https://site.example.com/return",
        },
        headers={"X-API-Key": raw_api_key},
    )

    # Cannot refund while status is PENDING
    pending_refund = await async_client.post(
        "/v1/orders/ORD-REF-001/refund",
        json={"amount": 50000},
        headers={"X-API-Key": raw_api_key},
    )
    assert pending_refund.status_code == 400
    assert pending_refund.json()["error"]["code"] == "REFUND_ERROR"

    # Mark order as COMPLETED in DB
    order = await OrderService.get_order_by_merchant_id(
        session=db_session,
        tenant_id=tenant.id,
        merchant_order_id="ORD-REF-001",
    )
    order.status = "COMPLETED"
    await db_session.commit()

    # Mock PhonePe Refund API
    respx.post(f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/refunds").mock(
        return_value=Response(
            200,
            json={
                "code": "PAYMENT_SUCCESS",
                "data": {
                    "transactionId": "PP_REFUND_TXN_999",
                    "amount": 50000,
                    "state": "COMPLETED",
                },
            },
        )
    )

    # Now trigger refund
    refund_res = await async_client.post(
        "/v1/orders/ORD-REF-001/refund",
        json={"amount": 50000, "reason": "Customer cancellation"},
        headers={"X-API-Key": raw_api_key},
    )
    assert refund_res.status_code == 200
    refund_data = refund_res.json()["data"]

    assert refund_data["merchant_order_id"] == "ORD-REF-001"
    assert refund_data["status"] == "SUCCESS"
    assert refund_data["phonepe_transaction_id"] == "PP_REFUND_TXN_999"
