import base64
import hashlib
import json
from typing import Any, Dict, Optional, Tuple
import httpx
from app.config import get_settings
from app.core.exceptions import PhonePeApiException
from app.core.logging import logger
from app.models.tenant import Tenant
from app.redis import get_redis
from app.services.tenant_service import TenantService

settings = get_settings()


class PhonePeClient:
    """
    HTTP Client for PhonePe's OAuth-based Standard Checkout Gateway API.
    Handles token acquisition with Redis caching, order initialization, status check, refund, and webhook verification.
    """

    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.is_sandbox = tenant.phonepe_env.lower() == "sandbox"
        self.auth_url = settings.PHONEPE_SANDBOX_AUTH_URL if self.is_sandbox else settings.PHONEPE_PROD_AUTH_URL
        self.base_url = settings.PHONEPE_SANDBOX_BASE_URL if self.is_sandbox else settings.PHONEPE_PROD_BASE_URL
        self.client_id, self.client_secret = TenantService.get_decrypted_phonepe_credentials(tenant)
        self.merchant_id = tenant.phonepe_merchant_id

    def _get_token_cache_key(self) -> str:
        return f"{settings.REDIS_TOKEN_CACHE_PREFIX}:{self.tenant.id}:{self.tenant.phonepe_env}"

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves OAuth access token from Redis cache or exchanges credentials with PhonePe OAuth endpoint.
        """
        redis_mgr = await get_redis()
        cache_key = self._get_token_cache_key()

        if not force_refresh:
            cached_token = await redis_mgr.get(cache_key)
            if cached_token:
                return cached_token

        # Acquire new token from PhonePe OAuth endpoint
        logger.info(f"Requesting new PhonePe OAuth token for tenant={self.tenant.id} env={self.tenant.phonepe_env}")
        auth_payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "client_version": 1,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    self.auth_url,
                    json=auth_payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code != 200:
                    logger.error(
                        f"PhonePe OAuth failed for tenant={self.tenant.id} status={response.status_code} body={response.text}"
                    )
                    raise PhonePeApiException(
                        message=f"PhonePe authentication failed ({response.status_code})",
                        details={"response": response.text},
                    )

                data = response.json()
                access_token = data.get("access_token") or data.get("data", {}).get("access_token")
                expires_in = int(data.get("expires_in") or data.get("data", {}).get("expires_in") or 3600)

                if not access_token:
                    raise PhonePeApiException(
                        message="PhonePe OAuth response did not contain access_token",
                        details=data,
                    )

                # Cache in Redis with 60 seconds safety buffer before expiry
                cache_ttl = max(60, expires_in - 60)
                await redis_mgr.set(cache_key, access_token, ex=cache_ttl)
                return access_token

            except httpx.RequestError as exc:
                logger.error(f"PhonePe OAuth network request error: {exc}")
                raise PhonePeApiException(message="PhonePe OAuth network error", details={"error": str(exc)})

    async def _send_authenticated_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        retry_on_401: bool = True,
    ) -> Dict[str, Any]:
        """
        Sends an authenticated HTTP request to PhonePe API with automatic token retry on 401.
        """
        token = await self.get_access_token()
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Merchant-Id": self.merchant_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method.upper() == "POST":
                    response = await client.post(url, json=payload, headers=headers)
                elif method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status_code == 401 and retry_on_401:
                    logger.warning("PhonePe returned 401 Unauthorized. Refreshing token and retrying...")
                    # Force refresh token and retry once
                    token = await self.get_access_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {token}"
                    if method.upper() == "POST":
                        response = await client.post(url, json=payload, headers=headers)
                    else:
                        response = await client.get(url, headers=headers)

                if response.status_code >= 400:
                    logger.error(f"PhonePe API call failed: {method} {url} -> {response.status_code} {response.text}")
                    try:
                        error_details = response.json()
                    except Exception:
                        error_details = {"raw_response": response.text}

                    raise PhonePeApiException(
                        message=f"PhonePe API returned error ({response.status_code})",
                        details=error_details,
                    )

                return response.json()

            except httpx.RequestError as exc:
                logger.error(f"PhonePe API network error: {exc}")
                raise PhonePeApiException(message="Failed to communicate with PhonePe API", details={"error": str(exc)})

    async def initiate_payment(
        self,
        merchant_order_id: str,
        amount_paise: int,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiates PhonePe Standard Checkout payment order.
        Returns checkout redirect URL and PhonePe order identifier.
        """
        webhook_callback_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/v1/webhooks/phonepe"

        payload = {
            "merchantId": self.merchant_id,
            "merchantOrderId": merchant_order_id,
            "merchantTransactionId": merchant_order_id,
            "amount": amount_paise,
            "redirectUrl": redirect_url,
            "redirectMode": "POST",
            "callbackUrl": webhook_callback_url,
            "paymentInstrument": {
                "type": "PAY_PAGE",
            },
        }

        if customer_phone:
            payload["mobileNumber"] = customer_phone
        if metadata:
            payload["merchantMetadata"] = metadata

        logger.info(f"Initiating PhonePe checkout for merchant_order_id={merchant_order_id}, amount={amount_paise}")

        # In standard PhonePe checkout v1/v2:
        endpoint = "/checkout/v2/pay" if "/v2" in self.base_url else "/v1/checkout/init"
        response_data = await self._send_authenticated_request("POST", endpoint, payload)

        data = response_data.get("data", response_data)
        phonepe_order_id = data.get("orderId") or data.get("transactionId") or data.get("merchantTransactionId")

        # Checkout instrument URL where user should be redirected
        checkout_url = (
            data.get("instrumentResponse", {}).get("redirectInfo", {}).get("url")
            or data.get("redirectUrl")
            or data.get("checkoutUrl")
        )

        return {
            "phonepe_order_id": phonepe_order_id,
            "checkout_url": checkout_url,
            "state": data.get("state", "PENDING"),
            "raw_response": response_data,
        }

    async def check_order_status(self, merchant_order_id: str, phonepe_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Checks current order status from PhonePe Order Status API.
        """
        lookup_id = phonepe_order_id or merchant_order_id
        endpoint = f"/checkout/v2/order/{lookup_id}/status" if "/v2" in self.base_url else f"/v1/orders/{self.merchant_id}/{merchant_order_id}/status"

        response_data = await self._send_authenticated_request("GET", endpoint)
        data = response_data.get("data", response_data)

        state = data.get("state") or data.get("status") or response_data.get("code")
        # Map PhonePe states to canonical gateway status
        status_map = {
            "COMPLETED": "COMPLETED",
            "PAYMENT_SUCCESS": "COMPLETED",
            "SUCCESS": "COMPLETED",
            "FAILED": "FAILED",
            "PAYMENT_ERROR": "FAILED",
            "PAYMENT_DECLINED": "FAILED",
            "TIMED_OUT": "FAILED",
            "EXPIRED": "EXPIRED",
            "PENDING": "PENDING",
            "PAYMENT_PENDING": "PENDING",
            "INITIATED": "PENDING",
        }

        canonical_status = status_map.get(str(state).upper(), "PENDING")

        return {
            "status": canonical_status,
            "state": state,
            "phonepe_transaction_id": data.get("transactionId"),
            "amount": data.get("amount"),
            "response_code": response_data.get("code"),
            "raw_response": response_data,
        }

    async def initiate_refund(
        self,
        merchant_order_id: str,
        merchant_refund_id: str,
        amount_paise: int,
        phonepe_transaction_id: Optional[str] = None,
        reason: str = "Customer Refund",
    ) -> Dict[str, Any]:
        """
        Calls PhonePe Refund API.
        """
        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": merchant_refund_id,
            "originalTransactionId": phonepe_transaction_id or merchant_order_id,
            "amount": amount_paise,
            "callbackUrl": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/v1/webhooks/phonepe",
        }

        endpoint = "/v1/refunds"
        response_data = await self._send_authenticated_request("POST", endpoint, payload)
        data = response_data.get("data", response_data)

        state = data.get("state") or data.get("status") or response_data.get("code")
        status_map = {
            "COMPLETED": "SUCCESS",
            "PAYMENT_SUCCESS": "SUCCESS",
            "SUCCESS": "SUCCESS",
            "FAILED": "FAILED",
            "PENDING": "PENDING",
        }
        canonical_status = status_map.get(str(state).upper(), "PENDING")

        return {
            "refund_id": data.get("transactionId") or merchant_refund_id,
            "status": canonical_status,
            "state": state,
            "raw_response": response_data,
        }

    def verify_webhook_signature(self, raw_body: str | bytes, signature_header: Optional[str]) -> bool:
        """
        Verifies PhonePe webhook authenticity based on PhonePe checksum/signature scheme.
        PhonePe generates SHA256(raw_body + client_secret) or SHA256(base64 + endpoint + salt).
        """
        if not signature_header:
            return False

        if isinstance(raw_body, str):
            raw_body = raw_body.encode("utf-8")

        # Scheme 1: SHA256 of payload + client_secret
        expected_hash = hashlib.sha256(raw_body + self.client_secret.encode("utf-8")).hexdigest()
        if signature_header.lower() == expected_hash.lower():
            return True

        # Scheme 2: Checksum with index (hash + "###" + key_index)
        parts = signature_header.split("###")
        if len(parts) >= 1:
            if parts[0].lower() == expected_hash.lower():
                return True

        return False
