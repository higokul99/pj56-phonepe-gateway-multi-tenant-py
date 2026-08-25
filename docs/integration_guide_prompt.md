# PhonePe Payment Gateway Integration Guide & AI Developer Prompt

Use this document as an **implementation brief / AI prompt** for any website (e.g., `careerportal.gecnoguru.com`, `jewelry.metora.com`, or any client app) that needs to accept payments via the centralized PhonePe Payment Gateway (`paymentgateway.gecnoguru.com`).

---

## 🎯 Objective for the Calling Website

Integrate PhonePe Standard Checkout payments into this website by communicating with the central microservice at `https://paymentgateway.gecnoguru.com`.

**Key Principle:** This website does **not** store PhonePe credentials or talk to PhonePe directly. It only interacts with `https://paymentgateway.gecnoguru.com` using a per-site `X-API-Key`.

---

## 🔑 Environment Variables Needed on This Website

Add these keys to your project's `.env` file:

```ini
# Central Payment Gateway URL
PAYMENT_GATEWAY_URL=https://paymentgateway.gecnoguru.com

# API Key issued for this website by the Payment Gateway Admin
PAYMENT_GATEWAY_API_KEY=pg_live_your_site_api_key_here

# Webhook secret for verifying incoming status updates from the Gateway
PAYMENT_GATEWAY_WEBHOOK_SECRET=whsec_your_webhook_secret_here
```

---

## 🔄 The 3-Step Payment Lifecycle

```
[User on Website]
       │
       ▼ (Clicks "Pay Now")
[Website Backend] ── POST /v1/orders ──> [paymentgateway.gecnoguru.com] ──> [PhonePe]
       │                                            │                             │
       │ <── Returns { checkout_url } ──────────────┘                             │
       │                                                                          │
       ▼ (Redirects User)                                                         │
[User PhonePe Checkout UI] ───────────────────────────────────────────────────────┘
       │
       ├──> 1. User completes payment ──> Redirects to Website `redirect_url`
       │
       └──> 2. Async Webhook ───────────> Gateway notifies Website `webhook_url` (Signed)
```

---

## 📡 API Reference & Implementation Steps

### Step 1: Initiate Payment Order (`POST /v1/orders`)

When a user clicks "Pay Now" or "Checkout", call the gateway from your backend:

- **Endpoint:** `POST https://paymentgateway.gecnoguru.com/v1/orders`
- **Headers:**
  - `Content-Type: application/json`
  - `X-API-Key: <PAYMENT_GATEWAY_API_KEY>`
- **Request Body:**
  ```json
  {
    "merchant_order_id": "CAREER-ORDER-100234",
    "amount": 49900,
    "currency": "INR",
    "redirect_url": "https://careerportal.gecnoguru.com/payment/callback?order_id=CAREER-ORDER-100234",
    "metadata": {
      "user_id": "usr_9981",
      "course_id": "course_fullstack_01",
      "user_email": "student@example.com"
    }
  }
  ```
  > ⚠️ **Note:** `amount` must be in **paise** (integer). For example, `₹499.00` = `49900` paise (`₹1.00 = 100 paise`).  
  > `merchant_order_id` is your own unique order ID (used for idempotency).

- **Gateway Response:**
  ```json
  {
    "success": true,
    "data": {
      "id": "e4f8d9b2-3c11-4fa3-91b5-829d4791a82f",
      "merchant_order_id": "CAREER-ORDER-100234",
      "phonepe_order_id": "PP_TXN_998877",
      "amount": 49900,
      "currency": "INR",
      "status": "PENDING",
      "checkout_url": "https://mercury.phonepe.com/transact/pay?token=...",
      "redirect_url": "https://careerportal.gecnoguru.com/payment/callback?order_id=CAREER-ORDER-100234"
    }
  }
  ```

- **Action:** Redirect the user's browser to `checkout_url`.

---

### Step 2: Handle Browser Return (`redirect_url`)

After payment, PhonePe redirects the user back to your specified `redirect_url` (e.g. `/payment/callback?order_id=CAREER-ORDER-100234`).

On this page:
1. Query your own database for the order status.
2. If still pending, call the gateway status check endpoint as a fallback:
   - **Endpoint:** `GET https://paymentgateway.gecnoguru.com/v1/orders/{merchant_order_id}`
   - **Header:** `X-API-Key: <PAYMENT_GATEWAY_API_KEY>`
3. Display a "Payment Successful! 🎉" or "Payment Failed / Pending" screen to the user.

---

### Step 3: Handle Asynchronous Webhook (`webhook_url`)

The Payment Gateway notifies your backend server directly when payment state changes.

- **Your Webhook Endpoint:** e.g., `POST https://careerportal.gecnoguru.com/api/payment/webhook`
- **Incoming Header:** `X-PG-Signature: <HMAC-SHA256-HEX-SIGNATURE>`
- **Incoming JSON Body:**
  ```json
  {
    "event": "payment.completed",
    "timestamp": "2026-08-25T16:30:00Z",
    "data": {
      "merchant_order_id": "CAREER-ORDER-100234",
      "phonepe_order_id": "PP_TXN_998877",
      "amount": 49900,
      "currency": "INR",
      "status": "COMPLETED",
      "metadata": {
        "user_id": "usr_9981",
        "course_id": "course_fullstack_01"
      },
      "updated_at": "2026-08-25T16:30:00Z"
    }
  }
  ```

#### Signature Verification Rule:
Calculate `HMAC-SHA256` of the **raw request body string** using your `PAYMENT_GATEWAY_WEBHOOK_SECRET`. If it matches `X-PG-Signature`, the webhook is authentic.

---

## 💻 Ready-to-Use Code Examples

### 1. Next.js / TypeScript / Node.js Implementation

#### A. Order Creation (`app/api/checkout/route.ts`)
```typescript
import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  const { courseId, userId, amountInRupees } = await req.json();
  const orderId = `ORDER-${Date.now()}`;

  // 1. Save pending order in your database
  // await db.order.create({ id: orderId, userId, status: 'PENDING', amount: amountInRupees });

  // 2. Call Payment Gateway
  const response = await fetch(`${process.env.PAYMENT_GATEWAY_URL}/v1/orders`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.PAYMENT_GATEWAY_API_KEY!,
    },
    body: JSON.stringify({
      merchant_order_id: orderId,
      amount: Math.round(amountInRupees * 100), // convert to paise
      currency: 'INR',
      redirect_url: `${process.env.NEXT_PUBLIC_SITE_URL}/payment/callback?order_id=${orderId}`,
      metadata: { userId, courseId },
    }),
  });

  const data = await response.json();
  if (!data.success) {
    return NextResponse.json({ error: data.error?.message || 'Failed to initialize payment' }, { status: 400 });
  }

  // 3. Return checkout URL to frontend
  return NextResponse.json({ checkoutUrl: data.data.checkout_url });
}
```

#### B. Webhook Receiver (`app/api/payment/webhook/route.ts`)
```typescript
import { NextResponse } from 'next/server';
import crypto from 'crypto';

export async function POST(req: Request) {
  const rawBody = await req.text();
  const signature = req.headers.get('x-pg-signature');
  const webhookSecret = process.env.PAYMENT_GATEWAY_WEBHOOK_SECRET!;

  // 1. Verify HMAC-SHA256 signature
  const expectedSig = crypto
    .createHmac('sha256', webhookSecret)
    .update(rawBody)
    .digest('hex');

  if (!signature || !crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSig))) {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 401 });
  }

  const payload = JSON.parse(rawBody);
  const { event, data } = payload;

  if (event === 'payment.completed' || data.status === 'COMPLETED') {
    const orderId = data.merchant_order_id;
    // 2. Mark order as COMPLETED in your database and grant course access
    // await db.order.update({ where: { id: orderId }, data: { status: 'COMPLETED' } });
    console.log(`Payment confirmed for ${orderId}`);
  }

  return NextResponse.json({ received: true });
}
```

---

### 2. Python (FastAPI / Django) Implementation

#### A. Order Creation
```python
import httpx
import os

PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL")
PAYMENT_GATEWAY_API_KEY = os.getenv("PAYMENT_GATEWAY_API_KEY")

async def create_payment_session(order_id: str, amount_in_rupees: float, user_email: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{PAYMENT_GATEWAY_URL}/v1/orders",
            json={
                "merchant_order_id": order_id,
                "amount": int(amount_in_rupees * 100), # in paise
                "currency": "INR",
                "redirect_url": f"https://careerportal.gecnoguru.com/payment/callback?order_id={order_id}",
                "metadata": {"user_email": user_email}
            },
            headers={
                "X-API-Key": PAYMENT_GATEWAY_API_KEY,
                "Content-Type": "application/json"
            }
        )
        data = res.json()
        if not data.get("success"):
            raise Exception(data.get("error", {}).get("message", "Payment error"))
        
        return data["data"]["checkout_url"]
```

#### B. Webhook Verification
```python
import hmac
import hashlib
import json
from fastapi import APIRouter, Request, Header, HTTPException

router = APIRouter()
WEBHOOK_SECRET = os.getenv("PAYMENT_GATEWAY_WEBHOOK_SECRET")

@router.post("/api/payment/webhook")
async def payment_webhook(request: Request, x_pg_signature: str = Header(None)):
    raw_body = await request.body()
    
    # Verify signature
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_pg_signature or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    payload = json.loads(raw_body.decode("utf-8"))
    order_id = payload["data"]["merchant_order_id"]
    status = payload["data"]["status"]
    
    if status == "COMPLETED":
        # Fulfill order in database
        pass
        
    return {"received": True}
```

---

## ⚡ Summary Checklist for Integrating Sites

- [ ] Add `PAYMENT_GATEWAY_URL`, `PAYMENT_GATEWAY_API_KEY`, and `PAYMENT_GATEWAY_WEBHOOK_SECRET` to `.env`.
- [ ] Implement backend endpoint to call `POST /v1/orders` and redirect user to `checkout_url`.
- [ ] Implement browser return page (`redirect_url`) showing confirmation.
- [ ] Implement webhook endpoint (`/api/payment/webhook`) with HMAC-SHA256 verification to safely fulfill orders.
