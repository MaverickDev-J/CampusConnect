"""Owner-scoped faculty drafts and official PostgreSQL LangGraph checkpoints."""
from alembic import op

revision = '007_workflows'
down_revision = '006_cleanup'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE faculty_workflows (
      workflow_id text PRIMARY KEY, actor_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      classroom_id text NOT NULL REFERENCES classrooms(classroom_id) ON DELETE CASCADE,
      topic text NOT NULL, payload jsonb NOT NULL, payload_hash text NOT NULL, sources jsonb NOT NULL,
      version integer NOT NULL DEFAULT 1 CHECK(version>0),
      status text NOT NULL DEFAULT 'awaiting_approval'
        CHECK(status IN ('awaiting_approval','approved','completed','rejected')),
      approved_hash text, approved_at timestamptz, result jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL DEFAULT now()+interval '24 hours',
      CHECK ((status IN ('approved','completed'))=(approved_hash IS NOT NULL)),
      CHECK ((status='completed')=(result IS NOT NULL)))''')
    op.execute('CREATE INDEX faculty_workflows_owner_idx ON faculty_workflows(actor_id,created_at DESC)')
    op.execute('ALTER TABLE faculty_workflows ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY workflow_owner ON faculty_workflows FOR ALL
      USING (actor_id=current_setting('app.user_id',true) AND public.can_write_classroom(classroom_id)
        AND public.actor_role() IN ('teacher','superadmin'))
      WITH CHECK (actor_id=current_setting('app.user_id',true) AND public.can_write_classroom(classroom_id)
        AND public.actor_role() IN ('teacher','superadmin'))''')
    # Frozen schema from langgraph-checkpoint-postgres 3.2.0 migrations 0..9.
    # Setup belongs to Alembic, never the non-owner runtime or request startup.
    op.execute('CREATE TABLE checkpoint_migrations(v integer PRIMARY KEY)')
    op.execute('INSERT INTO checkpoint_migrations(v) SELECT generate_series(0,9)')
    op.execute('''CREATE TABLE checkpoints (
      thread_id text NOT NULL REFERENCES faculty_workflows(workflow_id) ON DELETE CASCADE,
      checkpoint_ns text NOT NULL DEFAULT '', checkpoint_id text NOT NULL, parent_checkpoint_id text,
      type text, checkpoint jsonb NOT NULL, metadata jsonb NOT NULL DEFAULT '{}',
      PRIMARY KEY(thread_id,checkpoint_ns,checkpoint_id))''')
    op.execute('''CREATE TABLE checkpoint_blobs (
      thread_id text NOT NULL REFERENCES faculty_workflows(workflow_id) ON DELETE CASCADE,
      checkpoint_ns text NOT NULL DEFAULT '', channel text NOT NULL, version text NOT NULL,
      type text NOT NULL, blob bytea, PRIMARY KEY(thread_id,checkpoint_ns,channel,version))''')
    op.execute('''CREATE TABLE checkpoint_writes (
      thread_id text NOT NULL REFERENCES faculty_workflows(workflow_id) ON DELETE CASCADE,
      checkpoint_ns text NOT NULL DEFAULT '', checkpoint_id text NOT NULL, task_id text NOT NULL,
      idx integer NOT NULL, channel text NOT NULL, type text, blob bytea NOT NULL,
      task_path text NOT NULL DEFAULT '', PRIMARY KEY(thread_id,checkpoint_ns,checkpoint_id,task_id,idx))''')
    for table in ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes'):
        op.execute(f'CREATE INDEX {table}_thread_id_idx ON {table}(thread_id)')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY checkpoint_owner ON {table} FOR ALL
          USING (EXISTS(SELECT 1 FROM faculty_workflows w WHERE w.workflow_id=thread_id))
          WITH CHECK (EXISTS(SELECT 1 FROM faculty_workflows w WHERE w.workflow_id=thread_id))''')


def downgrade():
    raise RuntimeError('Restore a verified backup; workflow history must not be silently discarded')
