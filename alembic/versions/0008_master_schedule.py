"""master schedule tables

Revision ID: 0008_master_schedule
Revises: 0007_master_days_off
Create Date: 2026-01-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_master_schedule"
down_revision = "0007_master_days_off"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_working_hours",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="ck_master_working_hours_time_order"),
        sa.UniqueConstraint("master_id", "weekday", name="uq_master_working_hours_master_weekday"),
    )
    op.create_index("ix_master_working_hours_master_id", "master_working_hours", ["master_id"])
    op.create_index("ix_master_working_hours_master_weekday", "master_working_hours", ["master_id", "weekday"])

    op.create_table(
        "master_breaks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="ck_master_breaks_time_order"),
    )
    op.create_index("ix_master_breaks_master_id", "master_breaks", ["master_id"])
    op.create_index("ix_master_breaks_master_weekday", "master_breaks", ["master_id", "weekday"])


def downgrade() -> None:
    op.drop_index("ix_master_breaks_master_weekday", table_name="master_breaks")
    op.drop_index("ix_master_breaks_master_id", table_name="master_breaks")
    op.drop_table("master_breaks")

    op.drop_index("ix_master_working_hours_master_weekday", table_name="master_working_hours")
    op.drop_index("ix_master_working_hours_master_id", table_name="master_working_hours")
    op.drop_table("master_working_hours")
