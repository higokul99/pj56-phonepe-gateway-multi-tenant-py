from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_tenant
from app.database import get_db
from app.models.tenant import Tenant
from app.schemas.common import ApiResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusResponse
from app.schemas.refund import RefundCreate, RefundResponse
from app.services.order_service import OrderService
from app.services.refund_service import RefundService

router = APIRouter(prefix="/v1/orders", tags=["Orders"])


@router.post(
    "",
    response_model=ApiResponse[OrderResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment order",
    description="Initiates a PhonePe Standard Checkout session and returns the checkout URL. Idempotent on tenant + merchant_order_id.",
)
async def create_order(
    payload: OrderCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    order, is_created = await OrderService.create_or_get_order(
        session=session,
        tenant=tenant,
        data=payload,
    )
    return ApiResponse(
        success=True,
        data=OrderResponse(
            id=order.id,
            merchant_order_id=order.merchant_order_id,
            phonepe_order_id=order.phonepe_order_id,
            amount=order.amount,
            currency=order.currency,
            status=order.status,
            checkout_url=order.checkout_url,
            redirect_url=order.redirect_url,
            metadata=order.order_metadata,
            created_at=order.created_at,
            updated_at=order.updated_at,
        ),
    )


@router.get(
    "/{merchant_order_id}",
    response_model=ApiResponse[OrderStatusResponse],
    summary="Get order status",
    description="Returns current status of an order. Set force_sync=true to poll PhonePe API directly.",
)
async def get_order_status(
    merchant_order_id: str,
    force_sync: bool = Query(False, description="Whether to actively query PhonePe API for live status"),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    order = await OrderService.get_and_sync_order_status(
        session=session,
        tenant=tenant,
        merchant_order_id=merchant_order_id,
        force_sync=force_sync,
    )
    return ApiResponse(
        success=True,
        data=OrderStatusResponse(
            id=order.id,
            merchant_order_id=order.merchant_order_id,
            phonepe_order_id=order.phonepe_order_id,
            amount=order.amount,
            currency=order.currency,
            status=order.status,
            error_code=order.error_code,
            error_message=order.error_message,
            created_at=order.created_at,
            updated_at=order.updated_at,
        ),
    )


@router.post(
    "/{merchant_order_id}/refund",
    response_model=ApiResponse[RefundResponse],
    summary="Initiate a refund",
    description="Refunds a completed payment order with PhonePe.",
)
async def refund_order(
    merchant_order_id: str,
    payload: RefundCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
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
