import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import OrderNotFoundException, RefundException
from app.core.logging import logger
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.transaction import Transaction
from app.schemas.refund import RefundCreate, RefundResponse
from app.services.phonepe_client import PhonePeClient


class RefundService:
    @staticmethod
    async def process_refund(
        session: AsyncSession,
        tenant: Tenant,
        merchant_order_id: str,
        data: RefundCreate,
    ) -> Transaction:
        """
        Initiates a refund for an existing order with PhonePe and logs the refund transaction.
        """
        query = select(Order).where(
            Order.tenant_id == tenant.id,
            Order.merchant_order_id == merchant_order_id,
        )
        result = await session.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise OrderNotFoundException(f"Order '{merchant_order_id}' not found for refund")

        if order.status not in ("COMPLETED", "SUCCESS"):
            raise RefundException(
                f"Cannot refund order in '{order.status}' status. Only COMPLETED orders can be refunded."
            )

        refund_amount = data.amount or order.amount
        if refund_amount > order.amount:
            raise RefundException(f"Refund amount ({refund_amount}) cannot exceed order amount ({order.amount})")

        merchant_refund_id = data.merchant_refund_id or f"ref_{uuid.uuid4().hex[:16]}"

        phonepe_client = PhonePeClient(tenant)
        try:
            pp_res = await phonepe_client.initiate_refund(
                merchant_order_id=order.merchant_order_id,
                merchant_refund_id=merchant_refund_id,
                amount_paise=refund_amount,
                phonepe_transaction_id=order.phonepe_order_id,
                reason=data.reason or "Customer Refund",
            )

            refund_status = pp_res.get("status", "PENDING")
            refund_tx = Transaction(
                id=str(uuid.uuid4()),
                order_id=order.id,
                phonepe_transaction_id=pp_res.get("refund_id") or merchant_refund_id,
                transaction_type="REFUND",
                amount=refund_amount,
                status=refund_status,
                state=pp_res.get("state"),
                response_payload=pp_res.get("raw_response"),
            )
            session.add(refund_tx)
            await session.flush()

            logger.info(
                f"Refund processed for order={order.id} amount={refund_amount} status={refund_status}"
            )
            return refund_tx

        except Exception as exc:
            logger.error(f"Refund initiation failed for order={order.id}: {exc}")
            raise RefundException(f"Failed to process refund with PhonePe: {exc}")
