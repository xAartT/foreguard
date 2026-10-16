"""create request_logs

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("raw_request", sa.JSON(), nullable=True),
    )
    op.create_index("ix_request_logs_timestamp", "request_logs", ["timestamp"])
    op.create_index("ix_request_logs_ip", "request_logs", ["ip"])
    op.create_index("ix_request_logs_risk_level", "request_logs", ["risk_level"])


def downgrade() -> None:
    op.drop_index("ix_request_logs_risk_level", table_name="request_logs")
    op.drop_index("ix_request_logs_ip", table_name="request_logs")
    op.drop_index("ix_request_logs_timestamp", table_name="request_logs")
    op.drop_table("request_logs")
