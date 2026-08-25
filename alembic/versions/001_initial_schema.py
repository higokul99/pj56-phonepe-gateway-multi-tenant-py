"""Initial schema migration: tenants, api_keys, orders, transactions, webhook_logs

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-25 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phonepe_client_id", sa.Text(), nullable=False),
        sa.Column("phonepe_client_secret", sa.Text(), nullable=False),
        sa.Column("phonepe_merchant_id", sa.String(length=255), nullable=False),
        sa.Column("phonepe_env", sa.String(length=20), server_default="sandbox", nullable=False),
        sa.Column("webhook_url", sa.String(length=1024), nullable=True),
        sa.Column("webhook_secret", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_tenant_active", "api_keys", ["tenant_id", "is_active"])

    # 3. Orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_order_id", sa.String(length=255), nullable=False),
        sa.Column("phonepe_order_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="CREATED", nullable=False),
        sa.Column("redirect_url", sa.String(length=1024), nullable=True),
        sa.Column("checkout_url", sa.String(length=1024), nullable=True),
        sa.Column("order_metadata", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "merchant_order_id", name="uq_tenant_merchant_order_id"),
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_phonepe_order_id", "orders", ["phonepe_order_id"])
    op.create_index("ix_orders_tenant_status", "orders", ["tenant_id", "status"])

    # 4. Transactions table
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phonepe_transaction_id", sa.String(length=255), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), server_default="PAYMENT", nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="INITIATED", nullable=False),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transactions_phonepe_transaction_id", "transactions", ["phonepe_transaction_id"])
    op.create_index("ix_transactions_order_type", "transactions", ["order_id", "transaction_type"])

    # 5. Webhook Logs table
    op.create_table(
        "webhook_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="RECEIVED", nullable=False),
        sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_logs_tenant_status", "webhook_logs", ["tenant_id", "status"])
    op.create_index("ix_webhook_logs_order", "webhook_logs", ["order_id"])


def downgrade() -> None:
    op.drop_table("webhook_logs")
    op.drop_table("transactions")
    op.drop_table("orders")
    op.drop_table("api_keys")
    op.drop_table("tenants")
