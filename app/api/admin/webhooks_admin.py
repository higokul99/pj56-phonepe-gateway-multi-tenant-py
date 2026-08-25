from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_admin
from app.database import get_db
from app.models.webhook_log import WebhookLog
from app.schemas.common import ApiResponse

router = APIRouter(
    prefix="/admin/webhooks",
    tags=["Admin - Webhook Logs"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=ApiResponse[List[Dict[str, Any]]])
async def list_admin_webhook_logs(
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    query = select(WebhookLog).order_by(desc(WebhookLog.created_at))

    if source:
        query = query.where(WebhookLog.source == source)
    if status:
        query = query.where(WebhookLog.status == status)

    query = query.limit(limit)
    result = await session.execute(query)
    logs = result.scalars().all()

    items = []
    for l in logs:
        items.append({
            "id": l.id,
            "tenant_id": l.tenant_id,
            "order_id": l.order_id,
            "source": l.source,
            "event_type": l.event_type,
            "payload": l.payload,
            "signature": l.signature,
            "status": l.status,
            "delivery_attempts": l.delivery_attempts,
            "response_code": l.response_code,
            "error": l.error,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        })

    return ApiResponse(success=True, data=items)
