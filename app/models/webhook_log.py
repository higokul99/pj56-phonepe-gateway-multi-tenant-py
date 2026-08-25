import uuid
from typing import Any, Dict, Optional
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # PHONEPE (inbound) or OUTBOUND_TENANT
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # PAYMENT_SUCCESS, PAYMENT_FAILED, etc.
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", nullable=False)  # RECEIVED, PROCESSED, FORWARDED, FAILED
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_webhook_logs_tenant_status", "tenant_id", "status"),
        Index("ix_webhook_logs_order", "order_id"),
    )
