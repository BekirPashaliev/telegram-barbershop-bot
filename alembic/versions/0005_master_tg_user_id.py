from alembic import op
import sqlalchemy as sa

revision = "0005_master_tg_user_id"
down_revision = "0004_user_role_default"

def upgrade():
    op.add_column("masters", sa.Column("tg_user_id", sa.BigInteger(), nullable=True))

def downgrade():
    op.drop_column("masters", "tg_user_id")
