import json
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


@router.post(
    "/phonepe",
    status_code=status.HTTP_200_OK,
    summary="Inbound PhonePe Webhook Receiver",
    description="Receives asynchronous transaction status callbacks from PhonePe, updates order state, and notifies tenant site.",
)
async def receive_phonepe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    headers = dict(request.headers)

    try:
        parsed_payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        parsed_payload = {}

    result = await WebhookService.process_inbound_phonepe_webhook(
        session=session,
        raw_body=raw_body,
        headers=headers,
        parsed_payload=parsed_payload,
    )

    return result
