from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service & Environment
    APP_NAME: str = "PhonePe Payment Gateway Microservice"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PUBLIC_BASE_URL: str = "https://paymentgateway.gecnoguru.com"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payment_gateway"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TOKEN_CACHE_PREFIX: str = "phonepe:token"
    REDIS_IDEMPOTENCY_PREFIX: str = "phonepe:idempotency"
    REDIS_RATE_LIMIT_PREFIX: str = "phonepe:ratelimit"

    # Security & Encryption
    # Master Fernet key used to encrypt/decrypt tenant PhonePe client secrets at rest
    # Generate with: cryptography.fernet.Fernet.generate_key().decode()
    MASTER_ENCRYPTION_KEY: str = "8vXQ9c4lC6h3TzWzL9hJ7f3rK1mP5sQ8wY2uI0vE4aM="

    # Master Admin API Key for managing tenants and API keys
    ADMIN_API_KEY: str = "admin_secret_super_secure_key_change_in_production"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 120

    # PhonePe Endpoints Configuration
    PHONEPE_SANDBOX_AUTH_URL: str = "https://api-preprod.phonepe.com/apis/pg-sandbox/v1/oauth/token"
    PHONEPE_SANDBOX_BASE_URL: str = "https://api-preprod.phonepe.com/apis/pg-sandbox"

    PHONEPE_PROD_AUTH_URL: str = "https://api.phonepe.com/apis/hermes/v1/oauth/token"
    PHONEPE_PROD_BASE_URL: str = "https://api.phonepe.com/apis/hermes"

    # Reconciliation
    RECONCILIATION_INTERVAL_SECONDS: int = 300
    RECONCILIATION_ORDER_AGE_THRESHOLD_MINUTES: int = 5
    ENABLE_BACKGROUND_RECONCILIATION: bool = True

    # Outbound Webhook Retries
    WEBHOOK_MAX_RETRIES: int = 5
    WEBHOOK_TIMEOUT_SECONDS: float = 10.0


@lru_cache()
def get_settings() -> Settings:
    return Settings()
