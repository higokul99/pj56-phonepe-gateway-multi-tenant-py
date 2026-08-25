# PhonePe Payment Gateway Microservice — Build Specification

Use this as the brief for a developer or an AI coding assistant. It's written to be handed off directly.

---

## 1. Objective

Build a standalone, multi-tenant Python microservice — deployed at `paymentgateway.gecnoguru.com` — that wraps PhonePe's Standard Checkout API (OAuth-based, current version). Any of Gokul's websites, and eventually third-party merchants, initiate and track PhonePe payments by calling this service with a per-site API key, instead of integrating PhonePe directly.

---

## 2. Architecture Overview

```
Website A ─┐
Website B ─┼──> [API key in header] ──> paymentgateway.gecnoguru.com (FastAPI)
Merchant C─┘                                     │
                                                  ├── merchant/tenant store (each with own PhonePe creds)
                                                  ├── PhonePe OAuth token cache (per tenant, auto-refresh)
                                                  ├── PhonePe Standard Checkout API (pay / status / refund)
                                                  └── webhook receiver ──> updates order state ──> notifies calling site
```

Key principle: **calling websites never see PhonePe credentials or talk to PhonePe directly.** They only ever talk to this microservice.

---

## 3. Tech Stack

- **Framework:** FastAPI (async), Pydantic v2 for schema validation
- **Server:** Uvicorn behind Gunicorn (multi-worker) or Uvicorn workers directly
- **DB:** PostgreSQL (tenants, orders, transactions, webhook logs, API keys)
- **Cache:** Redis — OAuth token cache per tenant, idempotency keys, rate limiting
- **Reverse proxy / TLS:** Nginx + Let's Encrypt (Certbot) on the VPS, terminating TLS for `paymentgateway.gecnoguru.com`
- **Process manager:** systemd or Docker Compose (Docker Compose recommended for reproducibility on the VPS)
- **Migrations:** Alembic

---

## 4. Multi-Tenant Model

Since this needs to support multiple merchants later, design the tenant model from day one — retrofitting multi-tenancy is expensive.

**`tenants` table:**
| Field | Notes |
|---|---|
| `id` | UUID, primary key |
| `name` | Merchant/site display name |
| `phonepe_client_id` | Encrypted at rest |
| `phonepe_client_secret` | Encrypted at rest (see §6 for encryption approach) |
| `phonepe_merchant_id` | |
| `phonepe_env` | `sandbox` \| `production` |
| `webhook_url` | Where this microservice notifies the tenant's site of payment status changes |
| `webhook_secret` | Used to sign outgoing webhooks to the tenant, so they can verify authenticity |
| `is_active` | boolean |
| `created_at` | |

**`api_keys` table** (separate from tenant secrets — a tenant can have multiple keys, rotate them, revoke them):
| Field | Notes |
|---|---|
| `id` | |
| `tenant_id` | FK |
| `key_hash` | Store a hash (e.g. SHA-256) of the API key, never the raw key |
| `key_prefix` | First 6–8 chars, shown in dashboards/logs for identification without exposing the key |
| `is_active` | |
| `last_used_at` | |
| `created_at` | |

Gokul's own sites are just tenant rows like any other merchant — no special-casing needed.

---

## 5. Authentication (calling websites → this microservice)

- Each website sends `X-API-Key: <key>` on every request.
- Microservice hashes the incoming key and looks it up in `api_keys` → resolves `tenant_id`. Reject with 401 if not found/inactive.
- **Never** log the raw API key. Log `key_prefix` only.
- Rate-limit per API key (Redis token bucket) to blunt abuse if a key leaks.
- Provide an internal endpoint (protected separately, e.g. by a master admin key or basic auth + IP allowlist) to create/rotate/revoke tenant API keys — this is your own admin surface, not exposed to merchant sites.
- Serve everything over HTTPS only; reject plain HTTP at the Nginx layer.

---

## 6. Secrets Management

- Each tenant's `phonepe_client_secret` must be **encrypted at rest**, not stored plaintext in Postgres.
  - Use `cryptography`'s Fernet (symmetric) with a master key held outside the DB — in an environment variable or a secrets manager, never committed to the repo.
  - Alternative if you want less custom code: keep tenant secrets in a dedicated secrets store (e.g. HashiCorp Vault, or even AWS Secrets Manager if you later move off a plain VPS) and store only a reference/ID in Postgres.
- The master encryption key itself lives in the server's environment (`.env`, loaded via `python-dotenv` or systemd `EnvironmentFile`), with file permissions locked to the service user only.
- Rotate the master key procedure should exist even if you don't need it on day one — document it.

---

## 7. PhonePe Integration Flow (current, OAuth-based Standard Checkout)

1. **Auth token (per tenant, per environment):**
   - Exchange `phonepe_client_id` + `phonepe_client_secret` for an OAuth access token via PhonePe's auth endpoint.
   - Cache the token in Redis, keyed by `tenant_id:env`, with TTL slightly shorter than PhonePe's stated expiry. Auto-refresh on expiry or 401 from PhonePe.

2. **Initiate payment** — `POST /v1/orders` (your microservice's public endpoint):
   - Input: `tenant` (resolved from API key), `amount`, `merchant_order_id` (your own idempotency key, unique per tenant), `redirect_url`, optional `metadata`.
   - Microservice creates an `orders` row (status `CREATED`), calls PhonePe's pay/checkout endpoint with the tenant's token, stores PhonePe's `order_id`/transaction reference, and returns the PhonePe checkout redirect URL to the caller.
   - **Idempotency:** if the same `tenant_id + merchant_order_id` is retried, return the existing order rather than creating a duplicate PhonePe transaction.

3. **Webhook receiver** — `POST /v1/webhooks/phonepe` (PhonePe → your microservice):
   - Verify the webhook's authenticity per PhonePe's documented scheme (signature/checksum header) before trusting the payload — do not process unverified webhooks.
   - Update the `orders`/`transactions` row status.
   - Forward a signed notification to the tenant's own `webhook_url` (signed with that tenant's `webhook_secret`, so their backend can verify it came from you).
   - Respond `200` quickly; do slow work (forwarding, notifications) asynchronously (background task / queue) so PhonePe doesn't retry unnecessarily.

4. **Status check (fallback)** — `GET /v1/orders/{merchant_order_id}/status`:
   - Calls PhonePe's Order Status API if local state is stale or webhook was missed. Used as a reconciliation path, not the primary flow.

5. **Refunds** — `POST /v1/orders/{merchant_order_id}/refund`:
   - Same tenant-scoped, idempotent pattern. Track refund status separately from the original order.

6. **Reconciliation job:** a scheduled task (cron / Celery beat) that checks any orders stuck in `CREATED`/`PENDING` beyond a threshold against PhonePe's Status API, in case a webhook was lost.

---

## 8. Public API Surface (what calling websites use)

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/orders` | POST | Create a payment order, get PhonePe checkout URL |
| `/v1/orders/{merchant_order_id}` | GET | Get current status of an order |
| `/v1/orders/{merchant_order_id}/refund` | POST | Initiate a refund |
| `/v1/webhooks/phonepe` | POST | PhonePe → microservice (not called by tenant sites) |
| `/healthz` | GET | Liveness/readiness probe, no auth |

All tenant-facing responses should be consistent JSON with clear error codes (`INVALID_API_KEY`, `TENANT_INACTIVE`, `DUPLICATE_ORDER`, `PHONEPE_ERROR`, etc.) so integrating sites can handle failures predictably.

---

## 9. Security Checklist

- [ ] HTTPS-only (Nginx + Let's Encrypt, auto-renew)
- [ ] API keys hashed at rest, raw key shown to tenant once at creation only
- [ ] PhonePe client secrets encrypted at rest, master key outside the DB
- [ ] Webhook signature verification on inbound PhonePe callbacks
- [ ] Outbound webhooks to tenants signed, so they can verify authenticity
- [ ] Rate limiting per API key
- [ ] Idempotency keys on order creation and refunds
- [ ] No secrets in logs (redact API keys, tokens, PhonePe credentials)
- [ ] Input validation via Pydantic on every endpoint
- [ ] Least-privilege DB user for the app (no superuser)
- [ ] Automated dependency vulnerability scanning (`pip-audit` or Dependabot)
- [ ] Separate sandbox and production tenant credentials, never mixed
- [ ] Structured audit log of every order state transition

---

## 10. Deployment (VPS)

- Docker Compose stack: `app` (FastAPI/Uvicorn), `nginx`, `postgres`, `redis` — keeps the environment reproducible and makes moving VPS providers later trivial.
- Nginx reverse-proxies `paymentgateway.gecnoguru.com` → the app container, handles TLS termination via Certbot.
- Environment-specific config (`.env`) never committed to git — use `.env.example` in the repo instead.
- Basic monitoring: uptime check on `/healthz`, and alerting (even a simple cron + email/Telegram ping) if the webhook receiver stops responding.
- Backups: scheduled Postgres dumps, stored off-VPS.

---

## 11. Testing

- Use PhonePe's sandbox/UAT credentials and environment for all development and CI testing — never test against production credentials.
- Contract tests against a mocked PhonePe API (so CI doesn't depend on PhonePe's sandbox uptime).
- End-to-end test against PhonePe sandbox before go-live for at least: successful payment, failed payment, webhook delivery, manual status reconciliation, and refund.

---

## 12. Deliverables Checklist for the Build

- [ ] FastAPI project scaffold with the endpoints in §8
- [ ] Postgres schema + Alembic migrations for tenants, api_keys, orders, transactions, webhook_logs
- [ ] PhonePe OAuth token manager with Redis caching per tenant
- [ ] Order creation + PhonePe checkout call, with idempotency
- [ ] Webhook receiver with signature verification + async forwarding to tenant
- [ ] Status check and refund endpoints
- [ ] Reconciliation scheduled job
- [ ] Admin endpoint(s) for tenant/API-key management
- [ ] Docker Compose setup + Nginx config for `paymentgateway.gecnoguru.com`
- [ ] `.env.example` with every required variable documented
- [ ] README covering local setup, sandbox testing, and go-live steps