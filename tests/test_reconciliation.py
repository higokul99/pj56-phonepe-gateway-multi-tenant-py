from datetime import datetime, timedelta, timezone
import pytest
import respx
from httpx import Response
from app.config import get_settings
from app.models.order import Order
from app.services.reconciliation import ReconciliationService

settings = get_settings()


@pytest.mark.asyncio
@respx.mock
async def test_reconciliation_pending_order_sync(sample_tenant_and_key: dict, db_session):
    tenant = sample_tenant_and_key["tenant"]

    # 1. Create a stuck pending order created 10 minutes ago
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    stuck_order = Order(
        tenant_id=tenant.id,
        merchant_order_id="ORD-STUCK-001",
        phonepe_order_id="PP_STUCK_123",
        amount=10000,
        currency="INR",
        status="PENDING",
        created_at=old_time,
        updated_at=old_time,
    )
    db_session.add(stuck_order)
    await db_session.commit()

    # 2. Mock PhonePe OAuth & Order Status returning COMPLETED
    respx.post(settings.PHONEPE_SANDBOX_AUTH_URL).mock(
        return_value=Response(200, json={"access_token": "mock_token", "expires_in": 3600})
    )
    status_url = f"{settings.PHONEPE_SANDBOX_BASE_URL}/v1/orders/{tenant.phonepe_merchant_id}/ORD-STUCK-001/status"
    respx.get(status_url).mock(
        return_value=Response(
            200,
            json={
                "code": "PAYMENT_SUCCESS",
                "data": {
                    "transactionId": "PP_STUCK_123",
                    "amount": 10000,
                    "state": "COMPLETED",
                },
            },
        )
    )

    # 3. Trigger reconciliation
    reconciled_count = await ReconciliationService.reconcile_pending_orders(session=db_session)
    assert reconciled_count == 1

    # 4. Check DB status is updated to COMPLETED
    await db_session.refresh(stuck_order)
    assert stuck_order.status == "COMPLETED"
