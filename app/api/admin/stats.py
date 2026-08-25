from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import require_admin
from app.core.security import decrypt_secret
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.transaction import Transaction
from app.models.webhook_log import WebhookLog
from app.schemas.common import ApiResponse

router = APIRouter(
    prefix="/admin/stats",
    tags=["Admin - Dashboard Stats"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=ApiResponse[Dict[str, Any]])
async def get_dashboard_stats(session: AsyncSession = Depends(get_db)):
    """
    Returns aggregated metrics and 7-day trend data for the admin dashboard.
    """
    # 1. Total & active tenants
    tenants_count_query = select(func.count(Tenant.id))
    total_tenants = (await session.execute(tenants_count_query)).scalar() or 0

    active_tenants_query = select(func.count(Tenant.id)).where(Tenant.is_active == True)  # noqa: E712
    active_tenants = (await session.execute(active_tenants_query)).scalar() or 0

    # 2. Total active API keys
    active_keys_query = select(func.count(ApiKey.id)).where(ApiKey.is_active == True)  # noqa: E712
    active_keys = (await session.execute(active_keys_query)).scalar() or 0

    # 3. Orders breakdown & volume
    total_orders_query = select(func.count(Order.id))
    total_orders = (await session.execute(total_orders_query)).scalar() or 0

    completed_orders_query = select(func.count(Order.id)).where(Order.status == "COMPLETED")
    completed_orders = (await session.execute(completed_orders_query)).scalar() or 0

    pending_orders_query = select(func.count(Order.id)).where(Order.status.in_(["CREATED", "PENDING"]))
    pending_orders = (await session.execute(pending_orders_query)).scalar() or 0

    failed_orders_query = select(func.count(Order.id)).where(Order.status.in_(["FAILED", "EXPIRED"]))
    failed_orders = (await session.execute(failed_orders_query)).scalar() or 0

    # Total volume processed in paise
    volume_query = select(func.sum(Order.amount)).where(Order.status == "COMPLETED")
    total_volume_paise = (await session.execute(volume_query)).scalar() or 0
    total_volume_rupees = round(total_volume_paise / 100.0, 2)

    success_rate = round((completed_orders / total_orders * 100.0), 1) if total_orders > 0 else 100.0

    # 4. Last 7 days trend
    days_data = []
    now = datetime.now(timezone.utc)
    for i in range(6, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        start_of_day = datetime(day_date.year, day_date.month, day_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        day_vol_query = select(func.sum(Order.amount)).where(
            Order.status == "COMPLETED",
            Order.created_at >= start_of_day,
            Order.created_at < end_of_day,
        )
        day_vol_paise = (await session.execute(day_vol_query)).scalar() or 0

        day_orders_query = select(func.count(Order.id)).where(
            Order.created_at >= start_of_day,
            Order.created_at < end_of_day,
        )
        day_orders = (await session.execute(day_orders_query)).scalar() or 0

        days_data.append({
            "date": day_date.strftime("%b %d"),
            "volume_rupees": round(day_vol_paise / 100.0, 2),
            "orders": day_orders,
        })

    return ApiResponse(
        success=True,
        data={
            "metrics": {
                "total_tenants": total_tenants,
                "active_tenants": active_tenants,
                "active_keys": active_keys,
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "pending_orders": pending_orders,
                "failed_orders": failed_orders,
                "total_volume_rupees": total_volume_rupees,
                "success_rate_percentage": success_rate,
            },
            "chart_data": days_data,
        },
    )
