from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class PaymentGatewayException(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": details or {},
                },
            },
        )
        self.error_code = error_code
        self.message = message
        self.details = details or {}


class InvalidApiKeyException(PaymentGatewayException):
    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_API_KEY",
            message=message,
        )


class TenantInactiveException(PaymentGatewayException):
    def __init__(self, message: str = "Tenant account is inactive or disabled"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="TENANT_INACTIVE",
            message=message,
        )


class DuplicateOrderException(PaymentGatewayException):
    def __init__(self, message: str = "Order with this merchant_order_id already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="DUPLICATE_ORDER",
            message=message,
        )


class OrderNotFoundException(PaymentGatewayException):
    def __init__(self, message: str = "Order not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ORDER_NOT_FOUND",
            message=message,
        )


class PhonePeApiException(PaymentGatewayException):
    def __init__(self, message: str = "PhonePe upstream API error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="PHONEPE_ERROR",
            message=message,
            details=details,
        )


class RefundException(PaymentGatewayException):
    def __init__(self, message: str = "Refund processing failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="REFUND_ERROR",
            message=message,
            details=details,
        )


class RateLimitExceededException(PaymentGatewayException):
    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            message=message,
        )


class UnauthorizedAdminException(PaymentGatewayException):
    def __init__(self, message: str = "Unauthorized: Invalid master admin credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED_ADMIN",
            message=message,
        )
