from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class RefundCreate(BaseModel):
    merchant_refund_id: Optional[str] = Field(
        None,
        description="Unique refund identifier from calling website. Auto-generated if omitted.",
    )
    amount: Optional[int] = Field(
        None,
        gt=0,
        description="Refund amount in paise. If omitted, the full order amount is refunded.",
    )
    reason: Optional[str] = Field(default="Customer requested refund", max_length=255)


class RefundResponse(BaseModel):
    id: str
    order_id: str
    merchant_order_id: str
    phonepe_transaction_id: Optional[str] = None
    amount: int
    status: str  # INITIATED, SUCCESS, FAILED, PENDING
    state: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
