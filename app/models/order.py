import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    merchant_order_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Calling site's order ID / idempotency key
    phonepe_order_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)  # PhonePe transaction / order id
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Amount in paise
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="CREATED", nullable=False, index=True)  # CREATED, PENDING, COMPLETED, FAILED, EXPIRED
    redirect_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    checkout_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    order_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "merchant_order_id", name="uq_tenant_merchant_order_id"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
    )
