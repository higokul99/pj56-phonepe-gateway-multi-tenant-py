import base64
import json
import pytest
import respx
from httpx import AsyncClient, Response
from app.config import get_settings
from app.core.security import verify_signature
from app.models.order import Order
from app.services.order_service import OrderService

settings = get_settings()


@pytest.mark.asyncio
@respx.mock
async def test_inbound_phonepe_webhook_processing(
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
                    "orderId": "PP_WEBHOOK_TXN_1",
                    "redirectUrl": "https://mercury-tst.phonepe.com/pay",
                    "state": "PENDING",
                }
            },
        )
    )

    # Mock outbound tenant webhook endpoint
    outbound_mock = respx.post(tenant.webhook_url).mock(return_value=Response(200, json={"received": True}))

    # 2. Create Order
    create_res = await async_client.post(
        "/v1/orders",
        json={
            "merchant_order_id": "ORD-WH-001",
            "amount": 15000,
            "redirect_url": "https://site.example.com/return",
        },
        headers={"X-API-Key": raw_api_key},
    )
    assert create_res.status_code == 201

    # 3. Simulate PhonePe Callback (Base64 encoded event)
    event_payload = {
        "success": True,
        "code": "PAYMENT_SUCCESS",
        "message": "Payment Successful",
        "data": {
            "merchantId": tenant.phonepe_merchant_id,
            "merchantTransactionId": "ORD-WH-001",
            "transactionId": "PP_WEBHOOK_TXN_1",
            "amount": 15000,
            "state": "COMPLETED",
            "responseCode": "SUCCESS",
        },
    }
    encoded_event = base64.b64encode(json.dumps(event_payload).encode("utf-8")).decode("utf-8")

    # Send Webhook to /v1/webhooks/phonepe
    webhook_res = await async_client.post(
        "/v1/webhooks/phonepe",
        json={"response": encoded_event},
    )
    assert webhook_res.status_code == 200

    # 4. Check Order status in DB is now COMPLETED
    order = await OrderService.get_order_by_merchant_id(
        session=db_session,
        tenant_id=tenant.id,
        merchant_order_id="ORD-WH-001",
    )
    assert order is not None
    assert order.status == "COMPLETED"
    assert order.phonepe_order_id == "PP_WEBHOOK_TXN_1"
