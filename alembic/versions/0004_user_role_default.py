from alembic import op
import sqlalchemy as sa

revision = "0004_user_role_default"
down_revision = "0003_payments_rbac"

def upgrade():
    op.execute("UPDATE users SET role='user' WHERE role IS NULL")
    op.alter_column("users", "role",
                    existing_type=sa.String(length=32),
                    server_default="user",
                    nullable=False)

def downgrade():
    op.alter_column("users", "role",
                    existing_type=sa.String(length=32),
                    server_default=None,
                    nullable=False)
