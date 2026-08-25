from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    environment: str = Field(default="live", pattern="^(live|test)$", description="API key environment tag")


class ApiKeyCreatedResponse(BaseModel):
    id: str
    tenant_id: str
    key_prefix: str
    raw_api_key: str = Field(..., description="Raw API key — shown ONCE only! Store it securely.")
    is_active: bool
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: str
    tenant_id: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
