from typing import Any, Dict, Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    model_config = ConfigDict(from_attributes=True)


class HealthCheckResponse(BaseModel):
    status: str = "healthy"
    version: str
    environment: str
    database: str
    redis: str
