from alembic import op
import sqlalchemy as sa

revision = "0003_payments_rbac"
down_revision = "0002_services_overlap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # добавить значение в enum статусов записи
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'pending_payment'")

    # users.role
    op.add_column("users", sa.Column("role", sa.String(length=32), nullable=False, server_default="user"))
    op.alter_column("users", "role", server_default=None)

    # payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("pay_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )

    # appointments.payment_id
    op.add_column("appointments", sa.Column("payment_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_payment_id_payments",
        "appointments",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_appointments_payment_id", "appointments", ["payment_id"])
    op.create_index("ix_appointments_payment_id", "appointments", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_payment_id", table_name="appointments")
    op.drop_constraint("uq_appointments_payment_id", "appointments", type_="unique")
    op.drop_constraint("fk_appointments_payment_id_payments", "appointments", type_="foreignkey")
    op.drop_column("appointments", "payment_id")
    op.drop_table("payments")
    op.drop_column("users", "role")
    # enum значение назад обычно не откатывают
