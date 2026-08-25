from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Display name for the tenant/website")
    phonepe_client_id: str = Field(..., min_length=1, description="PhonePe OAuth Client ID")
    phonepe_client_secret: str = Field(..., min_length=1, description="PhonePe OAuth Client Secret")
    phonepe_merchant_id: str = Field(..., min_length=1, description="PhonePe Merchant ID / MID")
    phonepe_env: str = Field(default="sandbox", pattern="^(sandbox|production)$", description="PhonePe environment")
    webhook_url: Optional[str] = Field(None, description="Tenant webhook URL for event forwarding")


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    phonepe_client_id: Optional[str] = None
    phonepe_client_secret: Optional[str] = None
    phonepe_merchant_id: Optional[str] = None
    phonepe_env: Optional[str] = Field(None, pattern="^(sandbox|production)$")
    webhook_url: Optional[str] = None
    is_active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    phonepe_client_id_masked: str
    phonepe_merchant_id: str
    phonepe_env: str
    webhook_url: Optional[str]
    webhook_secret: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
