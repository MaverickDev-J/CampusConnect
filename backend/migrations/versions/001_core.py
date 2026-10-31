"""Initial relational store and versioned text/vector indexes."""
from pathlib import Path
from alembic import op

revision = "001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    # This initial migration contains ordinary DDL, with no procedural bodies.
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Restore a verified backup to reverse the initial data-store migration")
