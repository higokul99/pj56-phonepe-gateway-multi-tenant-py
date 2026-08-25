import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import InvalidApiKeyException, TenantInactiveException
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    generate_webhook_secret,
    hash_api_key,
)
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.schemas.api_key import ApiKeyCreatedResponse
from app.schemas.tenant import TenantCreate, TenantUpdate


class TenantService:
    @staticmethod
    async def create_tenant(session: AsyncSession, data: TenantCreate) -> Tenant:
        """Registers a new tenant with encrypted credentials and an auto-generated webhook secret."""
        # Encrypt the PhonePe client secret at rest using Fernet
        encrypted_client_secret = encrypt_secret(data.phonepe_client_secret)
        # Client ID can also be stored or encrypted; requirement states client_id & client_secret encrypted at rest
        encrypted_client_id = encrypt_secret(data.phonepe_client_id)

        webhook_secret = generate_webhook_secret()

        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=data.name,
            phonepe_client_id=encrypted_client_id,
            phonepe_client_secret=encrypted_client_secret,
            phonepe_merchant_id=data.phonepe_merchant_id,
            phonepe_env=data.phonepe_env,
            webhook_url=data.webhook_url,
            webhook_secret=webhook_secret,
            is_active=True,
        )
        session.add(tenant)
        await session.flush()
        return tenant

    @staticmethod
    async def update_tenant(session: AsyncSession, tenant_id: str, data: TenantUpdate) -> Optional[Tenant]:
        tenant = await session.get(Tenant, tenant_id)
        if not tenant:
            return None

        if data.name is not None:
            tenant.name = data.name
        if data.phonepe_client_id is not None:
            tenant.phonepe_client_id = encrypt_secret(data.phonepe_client_id)
        if data.phonepe_client_secret is not None:
            tenant.phonepe_client_secret = encrypt_secret(data.phonepe_client_secret)
        if data.phonepe_merchant_id is not None:
            tenant.phonepe_merchant_id = data.phonepe_merchant_id
        if data.phonepe_env is not None:
            tenant.phonepe_env = data.phonepe_env
        if data.webhook_url is not None:
            tenant.webhook_url = data.webhook_url
        if data.is_active is not None:
            tenant.is_active = data.is_active

        tenant.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return tenant

    @staticmethod
    async def get_tenant_by_id(session: AsyncSession, tenant_id: str) -> Optional[Tenant]:
        return await session.get(Tenant, tenant_id)

    @staticmethod
    async def list_tenants(session: AsyncSession) -> List[Tenant]:
        query = select(Tenant).order_by(Tenant.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create_api_key(session: AsyncSession, tenant_id: str, environment: str = "live") -> tuple[ApiKey, str]:
        """
        Creates a new API key for the tenant.
        Returns the ApiKey entity and the RAW unhashed API key (to display once).
        """
        raw_key, key_hash, key_prefix = generate_api_key(environment=environment)

        api_key = ApiKey(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            is_active=True,
        )
        session.add(api_key)
        await session.flush()
        return api_key, raw_key

    @staticmethod
    async def revoke_api_key(session: AsyncSession, key_id: str) -> bool:
        api_key = await session.get(ApiKey, key_id)
        if not api_key:
            return False
        api_key.is_active = False
        api_key.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return True

    @staticmethod
    async def list_api_keys_for_tenant(session: AsyncSession, tenant_id: str) -> List[ApiKey]:
        query = select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def authenticate_api_key(session: AsyncSession, raw_key: str) -> tuple[Tenant, ApiKey]:
        """
        Hashes the incoming raw key and resolves the active Tenant and ApiKey.
        Updates last_used_at timestamp.
        """
        if not raw_key or not raw_key.strip():
            raise InvalidApiKeyException("Missing X-API-Key header")

        key_hash = hash_api_key(raw_key.strip())
        query = (
            select(ApiKey)
            .options(selectinload(ApiKey.tenant))
            .where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
        )
        result = await session.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise InvalidApiKeyException("Invalid or revoked API key")

        tenant = api_key.tenant
        if not tenant or not tenant.is_active:
            raise TenantInactiveException("Tenant account is inactive")

        # Update last_used_at
        api_key.last_used_at = datetime.now(timezone.utc)
        await session.flush()

        return tenant, api_key

    @staticmethod
    def get_decrypted_phonepe_credentials(tenant: Tenant) -> tuple[str, str]:
        """Decrypts and returns (client_id, client_secret) for PhonePe communication."""
        try:
            client_id = decrypt_secret(tenant.phonepe_client_id)
        except Exception:
            client_id = tenant.phonepe_client_id

        client_secret = decrypt_secret(tenant.phonepe_client_secret)
        return client_id, client_secret
