"""enums + overlap predicate fix

Revision ID: 0009_enums_and_overlap_fix
Revises: 0008_master_schedule
Create Date: 2026-01-08
"""

from __future__ import annotations

from alembic import op


revision = "0009_enums_and_overlap_fix"
down_revision = "0008_master_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Ensure appointment_status has pending_payment (idempotent)
    # В Postgres новое значение ENUM нельзя использовать в той же транзакции,
    # где оно добавлено. Нужен COMMIT -> autocommit_block().
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'pending_payment'")

    # 2) Create enum types used by ORM (idempotent)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
                CREATE TYPE user_role AS ENUM ('user', 'master', 'admin');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'payment_status') THEN
                CREATE TYPE payment_status AS ENUM ('pending', 'paid', 'failed', 'refunded', 'cancelled');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'payment_provider') THEN
                CREATE TYPE payment_provider AS ENUM ('dummy', 'yookassa', 'stripe');
            END IF;
        END$$;
        """
    )

    # 3) Convert columns from VARCHAR -> ENUM (safe if values are valid)
    # users.role: VARCHAR -> user_role
    # Postgres cannot always cast the existing DEFAULT automatically; drop it first.
    # Also normalize any unexpected values to 'user' to avoid upgrade failures.
    op.execute("UPDATE users SET role='user' WHERE role IS NULL OR role NOT IN ('user','master','admin')")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    # На всякий случай: нормализуем мусорные/NULL значения и убираем DEFAULT перед кастом
    op.execute("UPDATE users SET role='user' WHERE role IS NULL OR role NOT IN ('user','master','admin')")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'::user_role")

    # payments.status/provider: VARCHAR -> enums
    op.execute("ALTER TABLE payments ALTER COLUMN status TYPE payment_status USING status::payment_status")
    op.execute("ALTER TABLE payments ALTER COLUMN provider TYPE payment_provider USING provider::payment_provider")

    # 4) Overlap protection must include pending_payment too (otherwise double-booking is possible)
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_no_overlap")
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_no_overlap
        EXCLUDE USING gist (
          master_id WITH =,
          tstzrange(starts_at, ends_at, '[)') WITH &&
        )
        WHERE (status IN ('active','pending_payment'))
        """
    )


def downgrade() -> None:
    # rollback constraint to previous predicate
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_no_overlap")
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

    # enums downgrade: keep types (dropping types can fail if used elsewhere)
    # revert columns to VARCHAR for safety
    op.execute("ALTER TABLE payments ALTER COLUMN provider TYPE varchar USING provider::text")
    op.execute("ALTER TABLE payments ALTER COLUMN status TYPE varchar USING status::text")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE varchar USING role::text")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'")
