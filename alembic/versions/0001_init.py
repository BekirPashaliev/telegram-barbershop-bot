"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-01-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    appointment_status = sa.Enum("active", "cancelled", name="appointment_status")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("reg_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "masters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("name", name="uq_masters_name"),
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appointment_status, server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_appointments_user_id", "appointments", ["user_id"])
    op.create_index("ix_appointments_datetime", "appointments", ["datetime"])
    op.create_index("ix_appointments_master_id", "appointments", ["master_id"])

    op.create_index(
        "uq_appointments_master_datetime_active",
        "appointments",
        ["master_id", "datetime"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_appointments_master_datetime_active", table_name="appointments")
    op.drop_index("ix_appointments_master_id", table_name="appointments")
    op.drop_index("ix_appointments_datetime", table_name="appointments")
    op.drop_index("ix_appointments_user_id", table_name="appointments")

    op.drop_table("appointments")
    op.drop_table("masters")
    op.drop_table("users")

    appointment_status = sa.Enum("active", "cancelled", name="appointment_status")
    appointment_status.drop(op.get_bind(), checkfirst=True)


