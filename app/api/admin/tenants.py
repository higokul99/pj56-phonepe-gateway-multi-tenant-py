from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_admin
from app.core.security import decrypt_secret
from app.database import get_db
from app.models.tenant import Tenant
from app.schemas.common import ApiResponse
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/admin/tenants",
    tags=["Admin - Tenants"],
    dependencies=[Depends(require_admin)],
)


def format_tenant_response(tenant: Tenant) -> TenantResponse:
    # Safely mask client ID
    try:
        raw_cid = decrypt_secret(tenant.phonepe_client_id)
    except Exception:
        raw_cid = tenant.phonepe_client_id
    masked_cid = f"{raw_cid[:6]}...{raw_cid[-4:]}" if len(raw_cid) > 10 else "***"

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        phonepe_client_id_masked=masked_cid,
        phonepe_merchant_id=tenant.phonepe_merchant_id,
        phonepe_env=tenant.phonepe_env,
        webhook_url=tenant.webhook_url,
        webhook_secret=tenant.webhook_secret,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.post(
    "",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant",
    description="Registers a tenant with PhonePe credentials (encrypted at rest) and generates a unique webhook secret.",
)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_db),
):
    tenant = await TenantService.create_tenant(session=session, data=payload)
    return ApiResponse(success=True, data=format_tenant_response(tenant))


@router.get(
    "",
    response_model=ApiResponse[List[TenantResponse]],
    summary="List all tenants",
)
async def list_tenants(
    session: AsyncSession = Depends(get_db),
):
    tenants = await TenantService.list_tenants(session=session)
    return ApiResponse(
        success=True,
        data=[format_tenant_response(t) for t in tenants],
    )


@router.get(
    "/{tenant_id}",
    response_model=ApiResponse[TenantResponse],
    summary="Get tenant details",
)
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(get_db),
):
    tenant = await TenantService.get_tenant_by_id(session=session, tenant_id=tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return ApiResponse(success=True, data=format_tenant_response(tenant))


@router.put(
    "/{tenant_id}",
    response_model=ApiResponse[TenantResponse],
    summary="Update tenant details or rotate PhonePe credentials",
)
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    session: AsyncSession = Depends(get_db),
):
    tenant = await TenantService.update_tenant(session=session, tenant_id=tenant_id, data=payload)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return ApiResponse(success=True, data=format_tenant_response(tenant))
