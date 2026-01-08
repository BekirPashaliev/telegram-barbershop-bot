"""services + overlap protection + reminders

Revision ID: 0002_services_overlap
Revises: 0001_init
Create Date: 2026-01-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_services_overlap"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) services
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )

    # seed default service
    op.execute(
        "INSERT INTO services (name, description, duration_minutes, price_cents) "
        "VALUES ('Стрижка', 'Базовая стрижка', 60, 150000)"
    )

    # 2) appointments: new columns
    op.add_column("appointments", sa.Column("service_id", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("reminded_24h", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("appointments", sa.Column("reminded_1h", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    op.create_foreign_key(
        "fk_appointments_service_id_services",
        "appointments",
        "services",
        ["service_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Backfill from old 'datetime' column (from 0001_init)
    op.execute(
        "UPDATE appointments "
        "SET starts_at = datetime, ends_at = datetime + interval '60 minutes' "
        "WHERE starts_at IS NULL"
    )
    op.execute(
        "UPDATE appointments "
        "SET service_id = (SELECT id FROM services WHERE name='Стрижка' LIMIT 1) "
        "WHERE service_id IS NULL"
    )

    op.alter_column("appointments", "service_id", nullable=False)
    op.alter_column("appointments", "starts_at", nullable=False)
    op.alter_column("appointments", "ends_at", nullable=False)

    # Drop old unique index and datetime index/column
    op.execute("DROP INDEX IF EXISTS uq_appointments_master_datetime_active")
    op.execute("DROP INDEX IF EXISTS ix_appointments_datetime")
    op.drop_column("appointments", "datetime")

    # 3) Overlap protection (EXCLUDE constraint)
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_no_overlap
        EXCLUDE USING gist (
          master_id WITH =,
          tstzrange(starts_at, ends_at, '[)') WITH &&
        )
        WHERE (status = 'active')
        """
    )

    # 4) Useful indexes
    op.create_index("ix_appointments_starts_at", "appointments", ["starts_at"])
    op.create_index("ix_appointments_master_starts_at", "appointments", ["master_id", "starts_at"])
    op.create_index("ix_appointments_user_starts_at", "appointments", ["user_id", "starts_at"])


def downgrade() -> None:
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_no_overlap")

    op.drop_index("ix_appointments_user_starts_at", table_name="appointments")
    op.drop_index("ix_appointments_master_starts_at", table_name="appointments")
    op.drop_index("ix_appointments_starts_at", table_name="appointments")

    op.add_column("appointments", sa.Column("datetime", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE appointments SET datetime = starts_at WHERE datetime IS NULL")

    op.drop_constraint("fk_appointments_service_id_services", "appointments", type_="foreignkey")

    op.drop_column("appointments", "reminded_1h")
    op.drop_column("appointments", "reminded_24h")
    op.drop_column("appointments", "ends_at")
    op.drop_column("appointments", "starts_at")
    op.drop_column("appointments", "service_id")

    op.execute(
        "CREATE UNIQUE INDEX uq_appointments_master_datetime_active "
        "ON appointments(master_id, datetime) WHERE status = 'active'"
    )
    op.create_index("ix_appointments_datetime", "appointments", ["datetime"])

    op.drop_table("services")
