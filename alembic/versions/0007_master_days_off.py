from alembic import op
import sqlalchemy as sa

revision = "0007_master_days_off"
down_revision = "0006_audit_log"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "master_days_off",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint(
        "uq_master_days_off_master_date",
        "master_days_off",
        ["master_id", "date"],
    )
    op.create_index(
        "ix_master_days_off_master_id_date",
        "master_days_off",
        ["master_id", "date"],
        unique=False,
    )

def downgrade():
    op.drop_index("ix_master_days_off_master_id_date", table_name="master_days_off")
    op.drop_constraint("uq_master_days_off_master_date", "master_days_off", type_="unique")
    op.drop_table("master_days_off")
