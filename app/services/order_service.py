import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import OrderNotFoundException
from app.core.logging import logger
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.transaction import Transaction
from app.schemas.order import OrderCreate
from app.services.phonepe_client import PhonePeClient


class OrderService:
    @staticmethod
    async def get_order_by_merchant_id(
        session: AsyncSession,
        tenant_id: str,
        merchant_order_id: str,
    ) -> Optional[Order]:
        query = select(Order).where(
            Order.tenant_id == tenant_id,
            Order.merchant_order_id == merchant_order_id,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_or_get_order(
        session: AsyncSession,
        tenant: Tenant,
        data: OrderCreate,
    ) -> tuple[Order, bool]:
        """
        Creates an order with PhonePe or returns existing one if idempotent retry.
        Returns: (Order, is_created)
        """
        existing_order = await OrderService.get_order_by_merchant_id(
            session=session,
            tenant_id=tenant.id,
            merchant_order_id=data.merchant_order_id,
        )

        if existing_order:
            logger.info(
                f"Idempotent order hit: tenant={tenant.id} merchant_order_id={data.merchant_order_id} status={existing_order.status}"
            )
            return existing_order, False

        # Create new order record in DB
        order = Order(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            merchant_order_id=data.merchant_order_id,
            amount=data.amount,
            currency=data.currency,
            status="CREATED",
            redirect_url=data.redirect_url,
            order_metadata=data.metadata,
        )
        session.add(order)
        await session.flush()

        # Call PhonePe to initiate checkout session
        phonepe_client = PhonePeClient(tenant)
        try:
            pp_res = await phonepe_client.initiate_payment(
                merchant_order_id=data.merchant_order_id,
                amount_paise=data.amount,
                redirect_url=data.redirect_url,
                metadata=data.metadata,
                customer_phone=data.customer_phone,
                customer_email=data.customer_email,
            )

            order.phonepe_order_id = pp_res.get("phonepe_order_id")
            order.checkout_url = pp_res.get("checkout_url")
            order.status = "PENDING"

            # Create initial payment transaction record
            transaction = Transaction(
                id=str(uuid.uuid4()),
                order_id=order.id,
                phonepe_transaction_id=pp_res.get("phonepe_order_id"),
                transaction_type="PAYMENT",
                amount=data.amount,
                status="PENDING",
                state=pp_res.get("state"),
                response_payload=pp_res.get("raw_response"),
            )
            session.add(transaction)
            await session.flush()

            return order, True

        except Exception as exc:
            order.status = "FAILED"
            order.error_code = "PHONEPE_INIT_FAILED"
            order.error_message = str(exc)
            await session.flush()
            raise

    @staticmethod
    async def get_and_sync_order_status(
        session: AsyncSession,
        tenant: Tenant,
        merchant_order_id: str,
        force_sync: bool = False,
    ) -> Order:
        """
        Retrieves order status. If pending or force_sync requested, checks PhonePe API.
        """
        order = await OrderService.get_order_by_merchant_id(
            session=session,
            tenant_id=tenant.id,
            merchant_order_id=merchant_order_id,
        )
        if not order:
            raise OrderNotFoundException(f"Order '{merchant_order_id}' not found for this tenant")

        # If order is still pending/created or sync is explicitly requested, poll PhonePe API
        if force_sync or order.status in ("CREATED", "PENDING"):
            try:
                phonepe_client = PhonePeClient(tenant)
                pp_status = await phonepe_client.check_order_status(
                    merchant_order_id=order.merchant_order_id,
                    phonepe_order_id=order.phonepe_order_id,
                )

                canonical_status = pp_status.get("status")
                if canonical_status and canonical_status != order.status:
                    logger.info(
                        f"Order status synced for order_id={order.id} from {order.status} -> {canonical_status}"
                    )
                    order.status = canonical_status
                    order.updated_at = datetime.now(timezone.utc)

                    # Update/create transaction
                    transaction = Transaction(
                        id=str(uuid.uuid4()),
                        order_id=order.id,
                        phonepe_transaction_id=pp_status.get("phonepe_transaction_id") or order.phonepe_order_id,
                        transaction_type="PAYMENT",
                        amount=order.amount,
                        status="SUCCESS" if canonical_status == "COMPLETED" else canonical_status,
                        state=pp_status.get("state"),
                        response_payload=pp_status.get("raw_response"),
                    )
                    session.add(transaction)
                    await session.flush()

            except Exception as e:
                logger.warning(f"Failed to sync order status from PhonePe for order_id={order.id}: {e}")

        return order
