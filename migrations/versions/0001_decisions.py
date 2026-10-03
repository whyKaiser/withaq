"""Containment state and workspace transaction boundary."""
from alembic import op
from withaq.schema import GROUPS

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    for table in GROUPS[revision]:
        table.create(op.get_bind())
    op.get_bind().execute(GROUPS[revision][0].insert().values(id=1, version=0))


def downgrade():
    for table in reversed(GROUPS[revision]):
        table.drop(op.get_bind())
