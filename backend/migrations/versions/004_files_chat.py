"""Durable ingestion, scoped file writes, and owner-scoped chat storage."""
from alembic import op

revision = "004_files_chat"
down_revision = "003_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE files ADD COLUMN mime_type text NOT NULL DEFAULT 'application/pdf', ADD COLUMN file_size_bytes bigint NOT NULL DEFAULT 0, ADD COLUMN doc_type text, ADD COLUMN processing_error text")
    op.execute("""CREATE FUNCTION public.can_write_classroom(target text) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT public.can_read_classroom(target) AND public.actor_role() IN ('teacher','superadmin') $$""")
    for table in ("files", "chunks"):
        op.execute(f"CREATE POLICY scoped_insert ON {table} FOR INSERT WITH CHECK (public.can_write_classroom(classroom_id))")
        op.execute(f"CREATE POLICY scoped_update ON {table} FOR UPDATE USING (public.can_write_classroom(classroom_id)) WITH CHECK (public.can_write_classroom(classroom_id))")
    op.execute("""CREATE POLICY revision_write ON file_revisions FOR ALL USING (
      EXISTS (SELECT 1 FROM files f WHERE f.file_id=file_revisions.file_id AND public.can_write_classroom(f.classroom_id))) WITH CHECK (
      EXISTS (SELECT 1 FROM files f WHERE f.file_id=file_revisions.file_id AND public.can_write_classroom(f.classroom_id)))""")
    op.execute("""CREATE TABLE ingestion_jobs (
      file_id text PRIMARY KEY REFERENCES files ON DELETE CASCADE,
      actor_id text NOT NULL REFERENCES users ON DELETE CASCADE,
      state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','working','completed','failed')),
      attempts integer NOT NULL DEFAULT 0, lease_token text, lease_until timestamptz,
      available_at timestamptz NOT NULL DEFAULT now(), last_error text
    )""")
    op.execute("ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY own_job ON ingestion_jobs FOR ALL USING (actor_id=current_setting('app.user_id',true)) WITH CHECK (actor_id=current_setting('app.user_id',true) AND EXISTS (SELECT 1 FROM files f WHERE f.file_id=ingestion_jobs.file_id AND public.can_write_classroom(f.classroom_id)))")
    op.execute("""CREATE FUNCTION public.claim_ingestion_job(token text)
      RETURNS SETOF public.ingestion_jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE target text;
      BEGIN
        UPDATE public.files f SET status='failed',processing_error='Worker lease expired; retry is available'
          WHERE EXISTS (SELECT 1 FROM public.ingestion_jobs j WHERE j.file_id=f.file_id
            AND j.state='working' AND j.attempts>=3 AND j.lease_until<now()) AND f.status<>'deleted';
        UPDATE public.ingestion_jobs SET state='failed',last_error='Worker lease expired'
          WHERE state='working' AND attempts>=3 AND lease_until<now();
        SELECT j.file_id INTO target FROM public.ingestion_jobs j
          WHERE j.attempts < 3 AND ((j.state='pending' AND j.available_at<=now())
            OR (j.state='working' AND j.lease_until<now()))
          ORDER BY j.available_at,j.file_id FOR UPDATE SKIP LOCKED LIMIT 1;
        IF NOT FOUND THEN RETURN; END IF;
        RETURN QUERY UPDATE public.ingestion_jobs SET state='working', attempts=attempts+1,
          lease_token=token, lease_until=now()+interval '15 minutes'
          WHERE file_id=target RETURNING *;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.claim_ingestion_job(text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.fail_ingestion_job(target text, token text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        UPDATE public.ingestion_jobs SET state=CASE WHEN attempts<3 THEN 'pending' ELSE 'failed' END,
          available_at=now()+interval '30 seconds',lease_until=NULL,last_error='Processing failed'
          WHERE file_id=target AND lease_token=token AND state='working' AND lease_until>now();
        IF FOUND THEN UPDATE public.files SET status='failed',processing_error='Processing failed; retry is available'
          WHERE file_id=target AND status<>'deleted'; END IF;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.fail_ingestion_job(text,text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.retry_ingestion_job(target text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE cls text;
      BEGIN
        SELECT classroom_id INTO cls FROM public.files WHERE file_id=target AND status <> 'deleted';
        IF cls IS NULL OR NOT public.can_write_classroom(cls) THEN
          RAISE EXCEPTION 'File not accessible' USING ERRCODE='42501';
        END IF;
        INSERT INTO public.ingestion_jobs(file_id,actor_id) VALUES(target,current_setting('app.user_id',true))
          ON CONFLICT(file_id) DO UPDATE SET state='pending',attempts=0,lease_token=NULL,lease_until=NULL,
            actor_id=current_setting('app.user_id',true),available_at=now(),last_error=NULL
          WHERE public.ingestion_jobs.state='failed' OR
            (public.ingestion_jobs.state='working' AND public.ingestion_jobs.lease_until<now());
        UPDATE public.files SET status='pending',processing_error=NULL WHERE file_id=target
          AND EXISTS (SELECT 1 FROM public.ingestion_jobs j WHERE j.file_id=target AND j.state='pending');
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.retry_ingestion_job(text) FROM PUBLIC")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN busy_until timestamptz, ADD COLUMN run_token text")
    for table in ("chat_sessions", "chat_messages"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    session_scope = "user_id=current_setting('app.user_id',true) AND (classroom_id IS NULL OR public.can_read_classroom(classroom_id))"
    op.execute(f"CREATE POLICY session_owner ON chat_sessions FOR ALL USING ({session_scope}) WITH CHECK ({session_scope})")
    op.execute("""CREATE POLICY message_owner ON chat_messages FOR ALL USING (
      EXISTS (SELECT 1 FROM chat_sessions s WHERE s.session_id=chat_messages.session_id))
      WITH CHECK (EXISTS (SELECT 1 FROM chat_sessions s WHERE s.session_id=chat_messages.session_id))""")


def downgrade():
    raise RuntimeError("Restore a verified backup to reverse file/chat migration")
