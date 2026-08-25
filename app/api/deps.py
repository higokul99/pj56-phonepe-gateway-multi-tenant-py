from typing import AsyncGenerator, Tuple
from fastapi import Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    InvalidApiKeyException,
    PaymentGatewayException,
    UnauthorizedAdminException,
)
from app.core.rate_limit import check_api_key_rate_limit
from app.core.security import verify_admin_key
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.services.tenant_service import TenantService


async def get_current_tenant_and_key(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key", description="Tenant API Key"),
    session: AsyncSession = Depends(get_db),
) -> Tuple[Tenant, ApiKey]:
    """
    FastAPI dependency that validates the X-API-Key header, resolves the active tenant,
    and enforces the per-key rate limit.
    """
    if not x_api_key:
        raise InvalidApiKeyException("Missing X-API-Key header")

    tenant, api_key = await TenantService.authenticate_api_key(session=session, raw_key=x_api_key)

    # Check and enforce rate limiting per API key prefix
    await check_api_key_rate_limit(key_prefix=api_key.key_prefix)

    # Attach tenant info to request state for access logging
    request.state.tenant_id = tenant.id
    request.state.key_prefix = api_key.key_prefix

    return tenant, api_key


async def get_current_tenant(
    tenant_and_key: Tuple[Tenant, ApiKey] = Depends(get_current_tenant_and_key),
) -> Tenant:
    tenant, _ = tenant_and_key
    return tenant


async def require_admin(
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key", description="Master Admin API Key"),
) -> bool:
    """
    Dependency that enforces master admin authentication.
    """
    if not verify_admin_key(x_admin_api_key):
        raise UnauthorizedAdminException("Invalid or missing X-Admin-API-Key header")
    return True
