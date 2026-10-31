"""Classroom read isolation for the future non-owner application role."""
from alembic import op

revision = "002_scope"
down_revision = "001_core"
branch_labels = None
depends_on = None


def upgrade():
    # Fixed search_path and qualified names prevent object substitution. The owner
    # resolves membership without recursive RLS; callers supply no alternate actor.
    op.execute("""
        CREATE FUNCTION public.can_read_classroom(target text) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
        AS $$ SELECT EXISTS (
            SELECT 1 FROM public.users u WHERE u.user_id = current_setting('app.user_id', true)
            AND (u.role = 'superadmin' OR EXISTS (
                SELECT 1 FROM public.classrooms c WHERE c.classroom_id = target
                AND (c.created_by = u.user_id OR EXISTS (
                    SELECT 1 FROM public.classroom_members m
                    WHERE m.classroom_id = target AND m.user_id = u.user_id
                ))
            ))
        ) $$
    """)
    # No write policies yet: the runtime role is read-only on these tables until
    # domain-specific write policies land with migrated CRUD handlers.
    for table in ("classrooms", "files", "chunks", "announcements", "calendar_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY classroom_read ON {table} FOR SELECT USING (public.can_read_classroom(classroom_id))")
    op.execute("ALTER TABLE file_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY revision_read ON file_revisions FOR SELECT USING (
        EXISTS (SELECT 1 FROM files f WHERE f.file_id = file_revisions.file_id)
    )""")


def downgrade():
    for table in ("classrooms", "files", "chunks", "announcements", "calendar_events"):
        op.execute(f"DROP POLICY classroom_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY revision_read ON file_revisions")
    op.execute("ALTER TABLE file_revisions DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION public.can_read_classroom(text)")
