import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.config import get_settings
from app.core.logging import logger
from app.database import AsyncSessionLocal
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_service import OrderService
from app.services.webhook_service import WebhookService

settings = get_settings()


class ReconciliationService:
    @staticmethod
    async def reconcile_pending_orders(session: Optional[AsyncSession] = None) -> int:
        """
        Scans for orders stuck in CREATED or PENDING status older than the threshold
        and synchronizes their state against PhonePe's Order Status API.
        """
        threshold_time = datetime.now(timezone.utc) - timedelta(
            minutes=settings.RECONCILIATION_ORDER_AGE_THRESHOLD_MINUTES
        )

        if session is not None:
            return await ReconciliationService._run_reconciliation_on_session(session, threshold_time)

        async with AsyncSessionLocal() as db_session:
            return await ReconciliationService._run_reconciliation_on_session(db_session, threshold_time)

    @staticmethod
    async def _run_reconciliation_on_session(session: AsyncSession, threshold_time: datetime) -> int:
        query = (
            select(Order)
            .options(selectinload(Order.tenant))
            .where(
                Order.status.in_(["CREATED", "PENDING"]),
                Order.created_at <= threshold_time,
            )
            .limit(100)
        )
        result = await session.execute(query)
        stuck_orders = result.scalars().all()

        if not stuck_orders:
            return 0

        logger.info(f"Reconciliation job found {len(stuck_orders)} pending orders to check")
        reconciled_count = 0

        for order in stuck_orders:
            tenant = order.tenant
            if not tenant or not tenant.is_active:
                continue

            prev_status = order.status
            try:
                updated_order = await OrderService.get_and_sync_order_status(
                    session=session,
                    tenant=tenant,
                    merchant_order_id=order.merchant_order_id,
                    force_sync=True,
                )
                await session.flush()

                if updated_order.status != prev_status:
                    reconciled_count += 1
                    logger.info(
                        f"Reconciled order {order.id}: {prev_status} -> {updated_order.status}"
                    )
                    # Dispatch webhook to tenant if status transitioned
                    if tenant.webhook_url:
                        outbound_payload = {
                            "event": f"payment.{updated_order.status.lower()}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": {
                                "merchant_order_id": updated_order.merchant_order_id,
                                "phonepe_order_id": updated_order.phonepe_order_id,
                                "amount": updated_order.amount,
                                "currency": updated_order.currency,
                                "status": updated_order.status,
                                "source": "reconciliation",
                                "metadata": updated_order.order_metadata,
                            },
                        }
                        asyncio.create_task(
                            WebhookService.dispatch_outbound_webhook(
                                tenant_id=tenant.id,
                                order_id=updated_order.id,
                                webhook_url=tenant.webhook_url,
                                webhook_secret=tenant.webhook_secret,
                                payload=outbound_payload,
                            )
                        )

            except Exception as e:
                logger.error(f"Error reconciling order {order.id}: {e}")

        return reconciled_count


async def run_reconciliation_loop():
    """Background task running continuously at configured intervals."""
    logger.info("Starting background order reconciliation worker loop...")
    while True:
        try:
            await ReconciliationService.reconcile_pending_orders()
        except asyncio.CancelledError:
            logger.info("Reconciliation loop cancelled. Shutting down worker.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in reconciliation worker: {e}")

        await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)
