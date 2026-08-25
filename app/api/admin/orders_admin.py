from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import require_admin
from app.database import get_db
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.transaction import Transaction
from app.schemas.common import ApiResponse
from app.schemas.refund import RefundCreate, RefundResponse
from app.services.refund_service import RefundService

router = APIRouter(
    prefix="/admin/orders",
    tags=["Admin - Orders"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=ApiResponse[List[Dict[str, Any]]])
async def list_admin_orders(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    query = (
        select(Order)
        .options(selectinload(Order.tenant), selectinload(Order.transactions))
        .order_by(desc(Order.created_at))
    )

    if tenant_id:
        query = query.where(Order.tenant_id == tenant_id)
    if status:
        query = query.where(Order.status == status)
    if search:
        query = query.where(Order.merchant_order_id.ilike(f"%{search}%"))

    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    orders = result.scalars().all()

    items = []
    for o in orders:
        items.append({
            "id": o.id,
            "tenant_id": o.tenant_id,
            "tenant_name": o.tenant.name if o.tenant else "Unknown",
            "merchant_order_id": o.merchant_order_id,
            "phonepe_order_id": o.phonepe_order_id,
            "amount": o.amount,
            "amount_rupees": round(o.amount / 100.0, 2),
            "currency": o.currency,
            "status": o.status,
            "redirect_url": o.redirect_url,
            "checkout_url": o.checkout_url,
            "metadata": o.order_metadata,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            "transactions": [
                {
                    "id": tx.id,
                    "type": tx.transaction_type,
                    "amount": tx.amount,
                    "amount_rupees": round(tx.amount / 100.0, 2),
                    "status": tx.status,
                    "state": tx.state,
                    "created_at": tx.created_at.isoformat() if tx.created_at else None,
                }
                for tx in (o.transactions or [])
            ],
        })

    return ApiResponse(success=True, data=items)


@router.post("/{merchant_order_id}/refund", response_model=ApiResponse[RefundResponse])
async def admin_trigger_refund(
    merchant_order_id: str,
    payload: RefundCreate,
    tenant_id: str = Query(..., description="Target tenant ID for the order"),
    session: AsyncSession = Depends(get_db),
):
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    refund_tx = await RefundService.process_refund(
        session=session,
        tenant=tenant,
        merchant_order_id=merchant_order_id,
        data=payload,
    )

    return ApiResponse(
        success=True,
        data=RefundResponse(
            id=refund_tx.id,
            order_id=refund_tx.order_id,
            merchant_order_id=merchant_order_id,
            phonepe_transaction_id=refund_tx.phonepe_transaction_id,
            amount=refund_tx.amount,
            status=refund_tx.status,
            state=refund_tx.state,
            created_at=refund_tx.created_at,
        ),
    )
