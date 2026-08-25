import uuid
from typing import List, Optional
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phonepe_client_id: Mapped[str] = mapped_column(Text, nullable=False)
    phonepe_client_secret: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted at rest
    phonepe_merchant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phonepe_env: Mapped[str] = mapped_column(String(20), default="sandbox", nullable=False)  # sandbox | production
    webhook_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String(255), nullable=False)  # For signing outbound webhooks
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="tenant", cascade="all, delete-orphan")
