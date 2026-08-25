from typing import Any, Dict
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from app.core.security import verify_admin_key
from app.schemas.common import ApiResponse

router = APIRouter(
    prefix="/admin/auth",
    tags=["Admin - Authentication"],
)


class AdminLoginRequest(BaseModel):
    admin_api_key: str = Field(..., description="Master Admin API Key")


@router.post("/verify", response_model=ApiResponse[Dict[str, Any]])
async def verify_admin_login(payload: AdminLoginRequest):
    if not verify_admin_key(payload.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid Master Admin API Key")
    return ApiResponse(
        success=True,
        data={
            "authenticated": True,
            "message": "Authentication successful",
        },
    )
