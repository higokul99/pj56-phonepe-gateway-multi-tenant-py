# PhonePe Payment Gateway Microservice

A high-performance, multi-tenant Python microservice (`paymentgateway.gecnoguru.com`) built with **FastAPI**, **SQLAlchemy 2.0 (asyncio)**, **PostgreSQL**, and **Redis** that wraps PhonePe's OAuth-based Standard Checkout API.

Calling websites and merchants communicate exclusively with this microservice via API keys (`X-API-Key`) and never directly touch or store PhonePe credentials.

---

## 🏛 Architecture

```
Merchant Website A ──┐
Merchant Website B ──┼──> [X-API-Key] ──> paymentgateway.gecnoguru.com (FastAPI)
Merchant Website C ──┘                                 │
                                                       ├── Fernet Encrypted Tenant Store (Postgres)
                                                       ├── PhonePe OAuth Token Cache per Tenant (Redis)
                                                       ├── PhonePe Standard Checkout API (pay / status / refund)
                                                       ├── Background Order Reconciliation Worker
                                                       └── Webhook Receiver ──> Outbound Signed Webhook (HMAC-SHA256)
```

---

## 🚀 Key Features

1. **Multi-Tenancy & Key Separation:**
   - Multi-tenant architecture with separate PhonePe credentials per site/merchant.
   - Separate API keys with key rotation and revocation. API keys are hashed with **SHA-256** at rest.
2. **Secrets Encryption at Rest:**
   - PhonePe client secrets and sensitive IDs are encrypted with **Fernet (AES-128-CBC + HMAC-SHA256)** using `MASTER_ENCRYPTION_KEY`.
   - Key rotation script provided (`scripts/rotate_master_key.py`).
3. **PhonePe OAuth Token Cache:**
   - Auto-fetches and caches Bearer tokens per tenant in Redis with safety buffer TTL and automatic retry on 401.
4. **Idempotent Order Creation:**
   - Calling `POST /v1/orders` with the same `merchant_order_id` safely returns the existing order session without duplicate transactions.
5. **Webhook Ingestion & Outbound Signing:**
   - Verifies incoming PhonePe callback signatures.
   - Dispatches signed webhook notifications to tenant `webhook_url` with `X-PG-Signature: HMAC-SHA256(webhook_secret, payload)`.
   - Exponential backoff retry mechanism.
6. **Automatic Reconciliation Worker:**
   - Background worker checks pending/stuck orders against PhonePe Order Status API and reconciles database state.
7. **Production Ready:**
   - Docker Compose stack (FastAPI/Uvicorn, PostgreSQL 16, Redis 7, Nginx TLS proxy).
   - Structured logging with automatic secret redaction (keys, tokens, client secrets).

---

## 📦 Project Structure

```
.
├── app/
│   ├── api/
│   │   ├── admin/            # Admin endpoints (/admin/tenants, /admin/keys)
│   │   ├── v1/               # Public endpoints (/v1/orders, /v1/webhooks)
│   │   ├── deps.py           # Auth, API key resolution & rate limiting
│   │   └── health.py         # /healthz liveness/readiness probe
│   ├── core/
│   │   ├── exceptions.py     # Custom exceptions & structured error responses
│   │   ├── logging.py        # Structured logging with secret redaction
│   │   ├── rate_limit.py     # Per-API-key rate limiter
│   │   └── security.py       # Fernet encryption, SHA-256 hashing, HMAC signatures
│   ├── models/               # SQLAlchemy 2.0 async models
│   ├── schemas/              # Pydantic v2 schemas
│   ├── services/             # PhonePe client, Order, Refund, Webhook, Reconciliation
│   ├── config.py             # BaseSettings configuration
│   ├── database.py           # Async DB engine & session
│   ├── main.py               # FastAPI application entrypoint
│   └── redis.py              # Redis manager with in-memory fallback
├── alembic/                  # Database migration scripts
├── docker/
│   ├── Dockerfile            # Production Python 3.12 container
│   └── nginx/                # Nginx TLS reverse proxy configuration
├── scripts/
│   └── rotate_master_key.py  # Master Fernet key rotation utility
├── tests/                    # Pytest test suite (unit, contract, integration)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🛠 Local Development & VPS Deployment Guides

> 📖 **Full step-by-step guide available:** [docs/deployment_and_local_setup_guide.md](docs/deployment_and_local_setup_guide.md) covers both local running (virtualenv / Docker) and deploying to **Hostinger KVM 2 VPS** with Docker, Nginx, Let's Encrypt SSL, and automated backups.

### 1. Prerequisites
- Python 3.12+
- PostgreSQL and Redis (or Docker)

### 2. Installation
```bash
# Clone and enter directory
cd 5-new-phone-pg

# Install dependencies
pip3 install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
```
Generate a new `MASTER_ENCRYPTION_KEY`:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste it into your `.env` file along with your `ADMIN_API_KEY` and database credentials.

### 4. Database Migrations
```bash
alembic upgrade head
```

### 5. Start Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI Swagger docs will be available at: **`http://localhost:8000/docs`**

---

## 🧪 Running Tests

Execute the comprehensive test suite with `pytest`:
```bash
python3 -m pytest -v
```

---

## 📖 API Documentation

### 1. Admin Management (Protected by `X-Admin-API-Key`)

#### Create a Tenant
`POST /admin/tenants`
```json
{
  "name": "Metora Jewelry Store",
  "phonepe_client_id": "UAT_CLIENT_ID_123",
  "phonepe_client_secret": "UAT_CLIENT_SECRET_XYZ",
  "phonepe_merchant_id": "PGTESTPAYUAT",
  "phonepe_env": "sandbox",
  "webhook_url": "https://jewelry.example.com/api/payment/webhook"
}
```

#### Issue an API Key for Tenant
`POST /admin/tenants/{tenant_id}/keys`
```json
{
  "environment": "live"
}
```
*Response returns `raw_api_key` (e.g. `pg_live_...`) **once**. Store it in the calling website's `.env`!*

---

### 2. Tenant Public API (Protected by `X-API-Key`)

#### Create Payment Order
`POST /v1/orders`
```json
{
  "merchant_order_id": "ORDER-987654",
  "amount": 250000,
  "currency": "INR",
  "redirect_url": "https://jewelry.example.com/checkout/callback",
  "metadata": {
    "cart_id": "cart_123"
  }
}
```
**Response:**
```json
{
  "success": true,
  "data": {
    "id": "c138f654-7546-444a-9ef8-e04e12e75eef",
    "merchant_order_id": "ORDER-987654",
    "phonepe_order_id": "PP_TXN_8765",
    "amount": 250000,
    "currency": "INR",
    "status": "PENDING",
    "checkout_url": "https://mercury-tst.phonepe.com/transact/pay?token=...",
    "redirect_url": "https://jewelry.example.com/checkout/callback"
  }
}
```

#### Check Order Status
`GET /v1/orders/{merchant_order_id}?force_sync=false`

#### Initiate Refund
`POST /v1/orders/{merchant_order_id}/refund`
```json
{
  "amount": 250000,
  "reason": "Customer cancellation"
}
```

---

## 🔒 Webhook Verification for Tenant Websites

When a payment succeeds or fails, this microservice sends an HTTP POST request to your tenant's `webhook_url` with the header:
```
X-PG-Signature: <HMAC-SHA256 hex signature>
```

### Verification Example (Python / FastAPI / Django):
```python
import hashlib
import hmac
import json

def verify_payment_webhook(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    expected_sig = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature_header)
```

### Verification Example (Node.js / Express):
```javascript
const crypto = require('crypto');

function verifyPaymentWebhook(rawBodyBuffer, signatureHeader, webhookSecret) {
  const expectedSignature = crypto
    .createHmac('sha256', webhookSecret)
    .update(rawBodyBuffer)
    .digest('hex');
  return crypto.timingSafeEqual(Buffer.from(expectedSignature), Buffer.from(signatureHeader));
}
```

---

## 🔄 Master Key Rotation

To rotate the `MASTER_ENCRYPTION_KEY`:
```bash
python scripts/rotate_master_key.py \
  --old-key "<OLD_FERNET_KEY>" \
  --new-key "<NEW_FERNET_KEY>"
```
Then update `MASTER_ENCRYPTION_KEY` in `.env` and restart the service.

---

## 🚢 Production Deployment with Docker Compose

```bash
# 1. Clone repository on VPS
git clone <repo-url> /opt/payment-gateway
cd /opt/payment-gateway

# 2. Configure .env
cp .env.example .env
nano .env

# 3. Setup SSL with Certbot for paymentgateway.gecnoguru.com
certbot certonly --standalone -d paymentgateway.gecnoguru.com

# 4. Launch full stack
docker compose up -d --build
```
