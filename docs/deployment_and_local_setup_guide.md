# Local Setup and Hostinger KVM 2 VPS Deployment Guide

This guide provides step-by-step instructions for running the **PhonePe Payment Gateway Microservice** in local development and deploying it to a **Hostinger KVM 2 VPS** (Ubuntu 22.04/24.04 LTS) using Docker, Docker Compose, and Nginx with SSL for domain `paymentgateway.gecnoguru.com`.

---

## 💻 Part 1: Running in Local Development

You have two options for running locally:
1. **Native Python Virtual Environment** (fastest for development & debugging).
2. **Local Docker Compose** (mirrors production environment).

---

### Option A: Native Python (Fastest for Development)

#### 1. Clone and Navigate to Directory
```bash
cd /Applications/XAMPP/xamppfiles/htdocs/github/5-gecnoguru/5-new-phone-pg
```

#### 2. Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Configure Local Environment (`.env`)
```bash
cp .env.example .env
```
Generate your Fernet Master Key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Edit `.env` and set:
```ini
APP_ENV=development
DEBUG=true
PORT=8000
PUBLIC_BASE_URL=http://localhost:8000

# For local development without PostgreSQL, you can use SQLite:
DATABASE_URL=sqlite+aiosqlite:///./dev_payment_gateway.db

# Redis URL (if Redis is not running locally, the service automatically falls back to in-memory caching)
REDIS_URL=redis://localhost:6379/0

MASTER_ENCRYPTION_KEY=<YOUR_GENERATED_FERNET_KEY>
ADMIN_API_KEY=local_admin_dev_secret_12345
ENABLE_BACKGROUND_RECONCILIATION=false
```

#### 5. Run Database Migrations
```bash
alembic upgrade head
```

#### 6. Start Local FastAPI Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc UI**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check Probe**: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

#### 7. Run Test Suite
```bash
python3 -m pytest -v
```

---

### Option B: Local Docker Compose

If you have Docker Desktop installed locally and want to test the full PostgreSQL + Redis + App stack:

```bash
cp .env.example .env
docker compose up --build
```
The application will be accessible at `http://localhost:8000` (or `http://localhost` if port 80/443 are mapped).

---

## 🌐 Part 2: Production Deployment on Hostinger KVM 2 VPS

### VPS Specifications (Hostinger KVM 2):
- **CPU:** 2 vCPU cores
- **RAM:** 8 GB RAM
- **Storage:** 100 GB NVMe Disk
- **OS:** Ubuntu 22.04 LTS / 24.04 LTS (recommended)
- **Target Domain:** `paymentgateway.gecnoguru.com`

---

### Step 1: Configure DNS Record

Before configuring SSL, point your domain's DNS `A` record to your Hostinger VPS IP:

| Type | Name / Host | Value / Points to | TTL |
|---|---|---|---|
| **A** | `paymentgateway` | `<YOUR_HOSTINGER_VPS_IP>` | 300 / Auto |

*Verify DNS propagation:*
```bash
dig paymentgateway.gecnoguru.com +short
# or
ping paymentgateway.gecnoguru.com
```

---

### Step 2: Connect and Harden Hostinger VPS

Connect via SSH:
```bash
ssh root@<YOUR_HOSTINGER_VPS_IP>
```

Update system packages:
```bash
apt update && apt upgrade -y
apt install -y curl git ufw fail2ban certbot
```

Configure Firewall (UFW):
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP for ACME challenges / redirects
ufw allow 443/tcp   # HTTPS for Payment Gateway API
ufw --force enable
```

---

### Step 3: Install Docker and Docker Compose on Hostinger VPS

```bash
# Remove any conflicting packages
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do apt-get remove -y $pkg; done

# Install official Docker repository
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify Docker installation
docker --version
docker compose version
```

---

### Step 4: Obtain Let's Encrypt SSL Certificate

Stop any service using port 80 and generate your certificate:

```bash
certbot certonly --standalone \
  -d paymentgateway.gecnoguru.com \
  --email support@gecnoguru.com \
  --agree-tos \
  --no-eff-email
```

*Certificates will be saved to:*  
`/etc/letsencrypt/live/paymentgateway.gecnoguru.com/fullchain.pem`  
`/etc/letsencrypt/live/paymentgateway.gecnoguru.com/privkey.pem`

---

### Step 5: Clone Application Repository

```bash
mkdir -p /opt/gecnoguru
cd /opt/gecnoguru
git clone https://github.com/gecnoguru/phonepe-payment-gateway.git payment-gateway
cd payment-gateway
```

---

### Step 6: Configure Production `.env`

```bash
cp .env.example .env
nano .env
```

Set the production parameters:
```ini
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=https://paymentgateway.gecnoguru.com

# PostgreSQL container connection
DATABASE_URL=postgresql+asyncpg://pguser:SuperSecureDbPass_2026!@postgres:5432/payment_gateway
DB_POOL_SIZE=25
DB_MAX_OVERFLOW=10
DB_ECHO=false

# Redis container connection
REDIS_URL=redis://redis:6379/0

# Generate master encryption key on the VPS:
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MASTER_ENCRYPTION_KEY=YOUR_GENERATED_PRODUCTION_FERNET_KEY

# Master Admin Key for /admin APIs (Keep this highly confidential)
ADMIN_API_KEY=YOUR_SUPER_STRONG_ADMIN_KEY_128_BITS

RATE_LIMIT_PER_MINUTE=150

# Upstream PhonePe Credentials / URLs
PHONEPE_SANDBOX_AUTH_URL=https://api-preprod.phonepe.com/apis/pg-sandbox/v1/oauth/token
PHONEPE_SANDBOX_BASE_URL=https://api-preprod.phonepe.com/apis/pg-sandbox

PHONEPE_PROD_AUTH_URL=https://api.phonepe.com/apis/hermes/v1/oauth/token
PHONEPE_PROD_BASE_URL=https://api.phonepe.com/apis/hermes

# Reconciliation & Webhook Retries
ENABLE_BACKGROUND_RECONCILIATION=true
RECONCILIATION_INTERVAL_SECONDS=300
RECONCILIATION_ORDER_AGE_THRESHOLD_MINUTES=5
WEBHOOK_MAX_RETRIES=5
WEBHOOK_TIMEOUT_SECONDS=10.0
```

Update `docker-compose.yml` to match the PostgreSQL password (`SuperSecureDbPass_2026!`).

---

### Step 7: Build and Launch Production Stack

```bash
docker compose up -d --build
```

Verify all containers are up and healthy:
```bash
docker compose ps
```

You should see:
- `payment_gateway_app` (healthy/running)
- `payment_gateway_db` (healthy)
- `payment_gateway_redis` (healthy)
- `payment_gateway_nginx` (running on ports 80, 443)

---

### Step 8: Verify Health & TLS

Run a test healthcheck from the terminal:
```bash
curl -i https://paymentgateway.gecnoguru.com/healthz
```

**Expected 200 OK Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "environment": "production",
    "database": "ok",
    "redis": "ok"
  },
  "error": null
}
```

---

### Step 9: Onboard Your First Merchant Site (Tenant)

Using `curl`, register your website and generate its API key:

#### 1. Create Tenant (e.g. Metora Jewelry Store)
```bash
curl -X POST https://paymentgateway.gecnoguru.com/admin/tenants \
  -H "X-Admin-API-Key: YOUR_SUPER_STRONG_ADMIN_KEY_128_BITS" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Metora Jewelry",
    "phonepe_client_id": "YOUR_PHONEPE_CLIENT_ID",
    "phonepe_client_secret": "YOUR_PHONEPE_CLIENT_SECRET",
    "phonepe_merchant_id": "YOUR_PHONEPE_MID",
    "phonepe_env": "production",
    "webhook_url": "https://jewelry.metora.com/api/payment/webhook"
  }'
```

*Copy the `id` from the returned JSON response (e.g. `tenant_id: "8c35a123-..."` and `webhook_secret: "whsec_..."`).*

#### 2. Issue API Key for the Tenant
```bash
curl -X POST https://paymentgateway.gecnoguru.com/admin/tenants/8c35a123-.../keys \
  -H "X-Admin-API-Key: YOUR_SUPER_STRONG_ADMIN_KEY_128_BITS" \
  -H "Content-Type: application/json" \
  -d '{
    "environment": "live"
  }'
```

*The response will output `raw_api_key` (e.g. `pg_live_638fa90...`). Copy this key into your Metora Jewelry website backend `.env`:*
```ini
PHONEPE_GATEWAY_URL=https://paymentgateway.gecnoguru.com
PHONEPE_GATEWAY_API_KEY=pg_live_638fa90...
PHONEPE_GATEWAY_WEBHOOK_SECRET=whsec_...
```

---

## 🛡 Part 3: Operations & Maintenance

### 1. SSL Auto-Renewal Cron Job
Let's Encrypt certificates expire in 90 days. Setup a renewal cron job:
```bash
crontab -e
```
Add:
```bash
0 3 * * 1 certbot renew --quiet && docker restart payment_gateway_nginx
```

### 2. Automated Daily Database Backups
Create a backup directory and script:
```bash
mkdir -p /opt/backups/pg_dumps
nano /opt/gecnoguru/backup_database.sh
```

Add:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/pg_dumps"
docker exec payment_gateway_db pg_dump -U pguser payment_gateway | gzip > "$BACKUP_DIR/backup_$DATE.sql.gz"
# Keep only last 14 days of backups
find "$BACKUP_DIR" -type f -mtime +14 -name "*.sql.gz" -exec rm {} \;
```
Make executable:
```bash
chmod +x /opt/gecnoguru/backup_database.sh
```
Add to crontab:
```bash
0 2 * * * /opt/gecnoguru/backup_database.sh
```

### 3. Viewing Application Logs in Production
```bash
# View app logs (real-time stream)
docker compose logs -f app

# View nginx access & error logs
docker compose logs -f nginx

# View database logs
docker compose logs -f postgres
```
*(All sensitive tokens, secrets, and raw API keys are automatically redacted in the log output).*

### 4. Updating Application Version / Deploying Changes
```bash
cd /opt/gecnoguru/payment-gateway
git pull origin main
docker compose up -d --build
```
*(Alembic migrations run automatically inside the container during startup).*
