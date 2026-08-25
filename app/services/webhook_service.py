import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.core.logging import logger
from app.core.security import sign_payload
from app.database import AsyncSessionLocal
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.transaction import Transaction
from app.models.webhook_log import WebhookLog
from app.schemas.webhook import OutboundTenantWebhookPayload
from app.services.phonepe_client import PhonePeClient

settings = get_settings()


class WebhookService:
    @staticmethod
    async def process_inbound_phonepe_webhook(
        session: AsyncSession,
        raw_body: bytes,
        headers: Dict[str, str],
        parsed_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Processes inbound webhook callback from PhonePe.
        Verifies signature, updates order/transaction status, and queues outbound tenant dispatch.
        """
        # Step 1: Decode response if PhonePe sent base64 encoded "response" string
        event_data = parsed_payload
        if "response" in parsed_payload and isinstance(parsed_payload["response"], str):
            try:
                decoded_bytes = base64.b64decode(parsed_payload["response"])
                event_data = json.loads(decoded_bytes.decode("utf-8"))
            except Exception as e:
                logger.warning(f"Could not base64 decode PhonePe response: {e}")

        # Extract identifiers from event data
        data_obj = event_data.get("data", event_data)
        merchant_id = data_obj.get("merchantId") or parsed_payload.get("merchantId")
        merchant_order_id = (
            data_obj.get("merchantTransactionId")
            or data_obj.get("merchantOrderId")
            or parsed_payload.get("merchantTransactionId")
        )
        phonepe_tx_id = data_obj.get("transactionId")
        event_code = event_data.get("code") or data_obj.get("state") or parsed_payload.get("event")

        logger.info(
            f"Received PhonePe webhook: merchant_id={merchant_id} merchant_order_id={merchant_order_id} code={event_code}"
        )

        # Log the inbound webhook receipt
        inbound_log = WebhookLog(
            id=str(uuid.uuid4()),
            source="PHONEPE",
            event_type=str(event_code),
            payload=event_data,
            signature=headers.get("x-verify") or headers.get("authorization"),
            status="RECEIVED",
        )
        session.add(inbound_log)
        await session.flush()

        # Step 2: Resolve tenant and order
        tenant: Optional[Tenant] = None
        order: Optional[Order] = None

        if merchant_order_id:
            # Query order by merchant_order_id
            order_query = select(Order).where(Order.merchant_order_id == merchant_order_id)
            res = await session.execute(order_query)
            order = res.scalar_one_or_none()

            if order:
                tenant = await session.get(Tenant, order.tenant_id)
                inbound_log.order_id = order.id
                inbound_log.tenant_id = order.tenant_id

        if not tenant and merchant_id:
            # Fallback query tenant by merchant_id
            t_query = select(Tenant).where(Tenant.phonepe_merchant_id == merchant_id)
            res = await session.execute(t_query)
            tenant = res.scalar_one_or_none()
            if tenant:
                inbound_log.tenant_id = tenant.id

        # Step 3: Verify PhonePe Signature if signature header present & tenant found
        signature_header = headers.get("x-verify") or headers.get("authorization")
        if tenant and signature_header:
            pp_client = PhonePeClient(tenant)
            is_valid = pp_client.verify_webhook_signature(raw_body, signature_header)
            if not is_valid:
                logger.warning(f"Inbound PhonePe webhook signature verification failed for tenant={tenant.id}")
                inbound_log.status = "FAILED"
                inbound_log.error = "Invalid webhook signature"
                await session.flush()
                return {"success": False, "message": "Signature verification failed"}

        # Step 4: Map status & update order
        status_map = {
            "PAYMENT_SUCCESS": "COMPLETED",
            "COMPLETED": "COMPLETED",
            "SUCCESS": "COMPLETED",
            "PAYMENT_ERROR": "FAILED",
            "PAYMENT_DECLINED": "FAILED",
            "FAILED": "FAILED",
            "TIMED_OUT": "FAILED",
            "EXPIRED": "EXPIRED",
            "PAYMENT_PENDING": "PENDING",
            "PENDING": "PENDING",
        }
        canonical_status = status_map.get(str(event_code).upper(), "PENDING")

        if order:
            order.status = canonical_status
            if phonepe_tx_id:
                order.phonepe_order_id = phonepe_tx_id
            order.updated_at = datetime.now(timezone.utc)

            # Record / update transaction
            tx = Transaction(
                id=str(uuid.uuid4()),
                order_id=order.id,
                phonepe_transaction_id=phonepe_tx_id or order.phonepe_order_id,
                transaction_type="PAYMENT",
                amount=data_obj.get("amount") or order.amount,
                status="SUCCESS" if canonical_status == "COMPLETED" else canonical_status,
                state=str(event_code),
                response_payload=event_data,
            )
            session.add(tx)

        inbound_log.status = "PROCESSED"
        await session.flush()

        # Step 5: Trigger asynchronous outbound webhook forwarding to calling website
        if tenant and tenant.webhook_url and order:
            event_name = f"payment.{canonical_status.lower()}"
            outbound_data = {
                "event": event_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "merchant_order_id": order.merchant_order_id,
                    "phonepe_order_id": order.phonepe_order_id,
                    "amount": order.amount,
                    "currency": order.currency,
                    "status": canonical_status,
                    "state": str(event_code),
                    "metadata": order.order_metadata,
                    "updated_at": order.updated_at.isoformat(),
                },
            }

            # Spawn background task to deliver webhook to tenant site
            asyncio.create_task(
                WebhookService.dispatch_outbound_webhook(
                    tenant_id=tenant.id,
                    order_id=order.id,
                    webhook_url=tenant.webhook_url,
                    webhook_secret=tenant.webhook_secret,
                    payload=outbound_data,
                )
            )

        return {"success": True, "message": "Webhook processed"}

    @staticmethod
    async def dispatch_outbound_webhook(
        tenant_id: str,
        order_id: str,
        webhook_url: str,
        webhook_secret: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Delivers signed webhook notification to tenant's webhook_url with retries.
        Signature is included in 'X-PG-Signature' header.
        """
        signature = sign_payload(payload, webhook_secret)
        headers = {
            "Content-Type": "application/json",
            "X-PG-Signature": signature,
            "User-Agent": "PhonePe-Gateway-Webhook/1.0",
        }

        async with AsyncSessionLocal() as session:
            outbound_log = WebhookLog(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                order_id=order_id,
                source="OUTBOUND_TENANT",
                event_type=payload.get("event", "payment.update"),
                payload=payload,
                signature=signature,
                status="FORWARDED",
                delivery_attempts=0,
            )
            session.add(outbound_log)
            await session.commit()

            max_retries = settings.WEBHOOK_MAX_RETRIES
            for attempt in range(1, max_retries + 1):
                outbound_log.delivery_attempts = attempt
                try:
                    async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
                        response = await client.post(webhook_url, json=payload, headers=headers)
                        outbound_log.response_code = response.status_code

                        if 200 <= response.status_code < 300:
                            logger.info(
                                f"Successfully delivered outbound webhook to tenant={tenant_id} url={webhook_url} status={response.status_code}"
                            )
                            outbound_log.status = "FORWARDED"
                            outbound_log.error = None
                            await session.commit()
                            return True
                        else:
                            logger.warning(
                                f"Tenant webhook endpoint returned {response.status_code} on attempt {attempt}/{max_retries}"
                            )
                            outbound_log.error = f"HTTP {response.status_code}: {response.text[:200]}"
                except Exception as exc:
                    logger.warning(f"Error dispatching outbound webhook (attempt {attempt}/{max_retries}): {exc}")
                    outbound_log.error = str(exc)

                # Exponential backoff before retry (e.g. 1s, 2s, 4s...)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

            outbound_log.status = "FAILED"
            await session.commit()
            return False
