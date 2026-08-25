import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set environment before loading app
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENABLE_BACKGROUND_RECONCILIATION"] = "false"
os.environ["ADMIN_API_KEY"] = "test_admin_secret_key"
os.environ["MASTER_ENCRYPTION_KEY"] = "8vXQ9c4lC6h3TzWzL9hJ7f3rK1mP5sQ8wY2uI0vE4aM="

from app.database import Base, get_db
from app.main import app
from app.models import ApiKey, Order, Tenant, Transaction, WebhookLog
from app.services.tenant_service import TenantService

# In-memory SQLite engine for tests
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Provides a clean in-memory database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession):
    """FastAPI async test client with overridden get_db dependency."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def sample_tenant_and_key(db_session: AsyncSession):
    """Creates a sample test tenant and API key."""
    from app.schemas.tenant import TenantCreate

    tenant_data = TenantCreate(
        name="Metora Jewelry Store",
        phonepe_client_id="UAT_TEST_CLIENT_ID_12345",
        phonepe_client_secret="UAT_TEST_CLIENT_SECRET_9876543210",
        phonepe_merchant_id="PGTESTPAYUAT",
        phonepe_env="sandbox",
        webhook_url="https://site.example.com/api/payment-webhook",
    )
    tenant = await TenantService.create_tenant(session=db_session, data=tenant_data)
    api_key_obj, raw_key = await TenantService.create_api_key(
        session=db_session,
        tenant_id=tenant.id,
        environment="test",
    )
    await db_session.commit()

    return {
        "tenant": tenant,
        "api_key_obj": api_key_obj,
        "raw_api_key": raw_key,
        "webhook_secret": tenant.webhook_secret,
    }
