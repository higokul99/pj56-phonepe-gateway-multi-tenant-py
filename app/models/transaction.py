import uuid
from typing import Any, Dict, Optional
from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    phonepe_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(20), default="PAYMENT", nullable=False)  # PAYMENT, REFUND
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Amount in paise
    status: Mapped[str] = mapped_column(String(30), default="INITIATED", nullable=False)  # INITIATED, SUCCESS, FAILED, PENDING
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # PhonePe state string (e.g. COMPLETED, PAYMENT_SUCCESS)
    response_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_order_type", "order_id", "transaction_type"),
    )
