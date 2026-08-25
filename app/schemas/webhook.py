from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PhonePeWebhookPayload(BaseModel):
    """
    Standard PhonePe Webhook callback payload structure.
    PhonePe sends either a base64 encoded response with checksum or direct JSON payload.
    """
    response: Optional[str] = Field(None, description="Base64 encoded event payload from PhonePe")
    event: Optional[str] = Field(None, description="Event type")
    payload: Optional[Dict[str, Any]] = Field(None, description="Direct event payload if not base64 encoded")


class OutboundTenantWebhookPayload(BaseModel):
    """
    Payload dispatched to tenant's webhook_url.
    Signed using HMAC-SHA256 with tenant's webhook_secret in X-PG-Signature header.
    """
    event: str = Field(..., description="e.g. payment.success, payment.failed, refund.success")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    data: Dict[str, Any] = Field(..., description="Order and transaction status details")
