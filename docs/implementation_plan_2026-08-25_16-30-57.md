# PhonePe Payment Gateway Microservice — Implementation Plan

**Generated:** 2026-08-25 16:30:57 IST  
**Specification Reference:** [docs/requirement.md](requirement.md)

---

Build a multi-tenant Python microservice (`paymentgateway.gecnoguru.com`) wrapping PhonePe's Standard Checkout API (OAuth-based), providing an API-key authenticated gateway for merchant websites to initiate payments, track statuses, handle refunds, and receive signed webhooks.

## Proposed Architecture & Directory Structure

```
5-new-phone-pg/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entrypoint, lifespan, middlewares
│   ├── config.py                # Pydantic v2 BaseSettings with env vars
│   ├── database.py              # Async SQLAlchemy engine, session maker, base model
│   ├── redis.py                 # Redis client manager (connection pool, caching, rate limiting)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py          # API key hashing, master key auth, Fernet encryption/decryption
│   │   ├── rate_limit.py        # Redis token-bucket / sliding-window rate limiter
│   │   ├── exceptions.py        # Custom exceptions and consistent JSON error response handlers
│   │   └── logging.py           # Structured logging with secret redaction
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py            # Tenant model (encrypted credentials, webhook url/secret)
│   │   ├── api_key.py           # API Key model (hash, prefix, status, last_used)
│   │   ├── order.py             # Order model (merchant_order_id, phonepe_order_id, status, etc.)
│   │   ├── transaction.py       # Transaction model (PAYMENT, REFUND, status, response payload)
│   │   └── webhook_log.py       # Webhook logs (inbound/outbound audit & delivery status)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py            # Generic response wrappers & error models
│   │   ├── tenant.py            # Tenant create/update/response schemas
│   │   ├── api_key.py           # API key generation/revoke schemas
│   │   ├── order.py             # Order create, status, redirect schemas
│   │   ├── refund.py            # Refund request/response schemas
│   │   └── webhook.py           # PhonePe webhook payload & tenant outgoing webhook schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── tenant_service.py    # Tenant & API key management
│   │   ├── phonepe_client.py    # Async HTTP client for PhonePe (OAuth token caching, checkout, status, refund, webhook verification)
│   │   ├── order_service.py     # Order orchestration, idempotency handling, status synchronization
│   │   ├── refund_service.py    # Refund initiation & status tracking
│   │   ├── webhook_service.py   # Inbound PhonePe webhook verification, state update, signed outbound forwarding
│   │   └── reconciliation.py    # Reconciliation background task for pending orders
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py              # FastAPI dependencies (get_db, get_redis, get_current_tenant, get_admin)
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── orders.py        # POST /v1/orders, GET /v1/orders/{merchant_order_id}, POST .../refund
│   │   │   └── webhooks.py      # POST /v1/webhooks/phonepe
│   │   └── admin/
│   │       ├── __init__.py
│   │       ├── tenants.py       # Admin CRUD for tenants, credentials rotation
│   │       └── keys.py          # Admin API key generation & revocation
│   └── jobs/
│       ├── __init__.py
│       └── scheduler.py         # Scheduled reconciliation worker
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                # Initial migration with all models
├── docker/
│   ├── Dockerfile
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── conf.d/paymentgateway.conf
├── tests/
│   ├── conftest.py              # Test database fixtures, mock redis, test client
│   ├── test_security.py         # Fernet encryption & API key hashing tests
│   ├── test_tenants_admin.py    # Admin tenant & API key management tests
│   ├── test_orders.py           # Order creation, idempotency, and status tests
│   ├── test_webhooks.py         # Webhook verification and outbound dispatching tests
│   └── test_refunds.py          # Refund handling tests
├── docs/
│   ├── requirement.md
│   └── architecture.md
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml / requirements.txt
└── README.md
```

## Detailed Component Plan

### 1. Security & Cryptography (`app/core/security.py`)
- **Fernet Symmetric Encryption:** Encrypt tenant PhonePe client secret at rest using a master encryption key (`MASTER_ENCRYPTION_KEY`). Decrypt on-demand when communicating with PhonePe OAuth endpoint.
- **API Key Security:** Generate secure random hex keys (`pg_live_...` or `pg_test_...`), store SHA-256 hash in Postgres, store `key_prefix` (e.g. `pg_live_ab1234`) for identification. Raw key returned once upon creation.
- **Admin Auth:** Master admin key via header `X-Admin-API-Key` with constant-time comparison (`secrets.compare_digest`).
- **Webhook Signatures:**
  - Inbound PhonePe webhooks: verify checksum/signature header against PhonePe signing algorithms.
  - Outbound tenant webhooks: calculate `X-PG-Signature` using `HMAC-SHA256(webhook_secret, payload_json_bytes)` for tenant backends to verify authenticity.

### 2. PhonePe OAuth & Client Integration (`app/services/phonepe_client.py`)
- Token Cache: Exchange `client_id` + decrypted `client_secret` at PhonePe auth endpoint (`/v1/oauth/token`). Cache access token in Redis with key `phonepe_token:{tenant_id}:{env}` and TTL = token expiry minus buffer (60s). Auto-refresh on expiry or 401.
- Checkout API: Call PhonePe Standard Checkout (`/v1/checkout/init` or `/v1/orders`) passing amount in paise, merchant_order_id, callback/redirect URLs.
- Order Status API: Call PhonePe `/v1/orders/{phonepe_order_id}/status`.
- Refund API: Call PhonePe `/v1/refunds`.

### 3. Order Management & Idempotency (`app/services/order_service.py`)
- Unique constraint on `(tenant_id, merchant_order_id)`.
- When `POST /v1/orders` is called:
  - If existing order with identical `(tenant_id, merchant_order_id)` exists:
    - If status is `CREATED` or `PENDING`, return existing checkout URL and order data (idempotent replay).
    - If already `COMPLETED` or `FAILED`, return existing order with appropriate status.
  - If new order: create row, call PhonePe, update `phonepe_order_id` & `checkout_url`, return response.

### 4. Webhooks & Outbound Dispatcher (`app/services/webhook_service.py`)
- `POST /v1/webhooks/phonepe`:
  - Validate PhonePe signature. Log raw payload into `webhook_logs`.
  - Locate order by PhonePe reference / merchant order ID.
  - Update order & transaction statuses (`COMPLETED`, `FAILED`, etc.).
  - Schedule background outbound webhook delivery to tenant's `webhook_url` signed with `X-PG-Signature`.
  - Outbound dispatcher sends payload with exponential backoff / retry logging.
  - Returns HTTP 200 immediately to PhonePe.

### 5. Background Reconciliation Worker (`app/services/reconciliation.py`)
- Periodic job (FastAPI lifespan task or standalone worker) scanning orders in `CREATED` or `PENDING` status older than configured threshold (e.g. 5 minutes).
- Checks PhonePe status endpoint and reconciles DB order state, triggering tenant webhook notification if status changed.

### 6. Admin API & Tenant Onboarding
- `POST /admin/tenants`: Register new merchant/site with PhonePe credentials (sandbox/production).
- `GET /admin/tenants`: List registered tenants (secrets redacted).
- `POST /admin/tenants/{tenant_id}/keys`: Issue new API key for calling websites.
- `POST /admin/keys/{key_id}/revoke`: Revoke API key.
- `PUT /admin/tenants/{tenant_id}`: Update tenant configuration / rotate credentials.

### 7. Docker, Nginx & Deployment
- `Dockerfile`: Multi-stage Python 3.12 slim image with non-root user.
- `docker-compose.yml`: PostgreSQL 16, Redis 7, FastAPI App (Uvicorn), and Nginx reverse proxy.
- Nginx configuration with rate limiting, secure SSL headers, and proxy pass.
- `.env.example` detailing all required environment variables.

## Verification Plan

### Automated Tests
- Setup `pytest` environment with in-memory SQLite / async SQLite and mock Redis.
- **Unit & Security Tests:**
  - `test_security.py`: Verify Fernet encryption/decryption, API key hashing, constant-time comparison, HMAC signature generation & verification.
- **Admin & Tenant Tests:**
  - `test_tenants_admin.py`: Tenant creation, encrypted credential storage, API key generation, revocation, auth validation.
- **Order & Idempotency Tests:**
  - `test_orders.py`: Mock PhonePe OAuth & Checkout APIs; test order creation, duplicate order idempotency replay, status fetching.
- **Webhook & Notification Tests:**
  - `test_webhooks.py`: Valid and invalid PhonePe webhook signatures, order state transition, signed outbound webhook dispatch to tenant webhook endpoint.
- **Refund Tests:**
  - `test_refunds.py`: Refund creation, idempotency, transaction logging.

### Manual / Integration Verification
- Run test suite with `pytest -v`.
- Test running the FastAPI application locally and validating `/healthz`, `/docs` (OpenAPI Swagger), and sample API calls.
