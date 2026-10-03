"""Immutable artifacts, complete manifests, and revocation barriers."""
from alembic import op
from withaq.schema import GROUPS

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def upgrade():
    for table in GROUPS[revision]:
        table.create(op.get_bind())


def downgrade():
    for table in reversed(GROUPS[revision]):
        table.drop(op.get_bind())
