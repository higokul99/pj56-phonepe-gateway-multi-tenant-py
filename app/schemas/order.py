from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    merchant_order_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Calling website's unique order identifier (idempotency key per tenant)",
    )
    amount: int = Field(
        ...,
        gt=0,
        description="Amount in smallest currency unit (e.g. paise for INR: 100 paise = ₹1.00)",
    )
    currency: str = Field(default="INR", max_length=10, description="ISO Currency code")
    redirect_url: str = Field(
        ...,
        description="URL where user is redirected after completing payment on PhonePe checkout",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary metadata attached to the order",
    )
    customer_id: Optional[str] = Field(default=None, description="Optional customer ID on the calling website")
    customer_phone: Optional[str] = Field(default=None, description="Optional customer 10-digit mobile number")
    customer_email: Optional[str] = Field(default=None, description="Optional customer email address")


class OrderResponse(BaseModel):
    id: str
    merchant_order_id: str
    phonepe_order_id: Optional[str] = None
    amount: int
    currency: str
    status: str
    checkout_url: Optional[str] = None
    redirect_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrderStatusResponse(BaseModel):
    id: str
    merchant_order_id: str
    phonepe_order_id: Optional[str] = None
    amount: int
    currency: str
    status: str  # CREATED, PENDING, COMPLETED, FAILED, EXPIRED
    state: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
