from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_admin
from app.database import get_db
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse
from app.schemas.common import ApiResponse
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/admin",
    tags=["Admin - API Keys"],
    dependencies=[Depends(require_admin)],
)


@router.post(
    "/tenants/{tenant_id}/keys",
    response_model=ApiResponse[ApiKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API key for a tenant",
    description="Generates an API key. The raw_api_key is returned ONCE and never stored raw.",
)
async def generate_tenant_api_key(
    tenant_id: str,
    payload: ApiKeyCreate,
    session: AsyncSession = Depends(get_db),
):
    tenant = await TenantService.get_tenant_by_id(session=session, tenant_id=tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    api_key, raw_key = await TenantService.create_api_key(
        session=session,
        tenant_id=tenant_id,
        environment=payload.environment,
    )

    return ApiResponse(
        success=True,
        data=ApiKeyCreatedResponse(
            id=api_key.id,
            tenant_id=api_key.tenant_id,
            key_prefix=api_key.key_prefix,
            raw_api_key=raw_key,
            is_active=api_key.is_active,
            created_at=api_key.created_at,
        ),
    )


@router.get(
    "/tenants/{tenant_id}/keys",
    response_model=ApiResponse[List[ApiKeyResponse]],
    summary="List all API keys for a tenant",
)
async def list_tenant_api_keys(
    tenant_id: str,
    session: AsyncSession = Depends(get_db),
):
    tenant = await TenantService.get_tenant_by_id(session=session, tenant_id=tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    keys = await TenantService.list_api_keys_for_tenant(session=session, tenant_id=tenant_id)
    return ApiResponse(
        success=True,
        data=[
            ApiKeyResponse(
                id=k.id,
                tenant_id=k.tenant_id,
                key_prefix=k.key_prefix,
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                created_at=k.created_at,
            )
            for k in keys
        ],
    )


@router.post(
    "/keys/{key_id}/revoke",
    response_model=ApiResponse[dict],
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    session: AsyncSession = Depends(get_db),
):
    revoked = await TenantService.revoke_api_key(session=session, key_id=key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return ApiResponse(success=True, data={"message": f"API key {key_id} revoked successfully"})
