"""Immediate document removal with durable, fenced physical cleanup."""
from alembic import op

revision = '006_cleanup'
down_revision = '005_campus_actions'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE storage_cleanup (
      file_id text PRIMARY KEY, storage_path text NOT NULL, actor_id text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
      attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
      lease_token text, lease_until timestamptz, last_error text)""")
    op.execute('ALTER TABLE storage_cleanup ENABLE ROW LEVEL SECURITY')
    op.execute("CREATE POLICY cleanup_owner ON storage_cleanup FOR SELECT USING (actor_id=current_setting('app.user_id',true))")
    op.execute("""CREATE FUNCTION public.queue_file_cleanup(target text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE document public.files;
      BEGIN
        PERFORM 1 FROM public.ingestion_jobs WHERE file_id=target FOR UPDATE;
        SELECT * INTO document FROM public.files WHERE file_id=target FOR UPDATE;
        IF NOT FOUND OR NOT public.can_write_classroom(document.classroom_id) THEN
          RAISE EXCEPTION 'File not accessible' USING ERRCODE='42501';
        END IF;
        INSERT INTO public.storage_cleanup(file_id,storage_path,actor_id)
          VALUES(target,document.storage_path,current_setting('app.user_id',true)) ON CONFLICT DO NOTHING;
        UPDATE public.files SET status='deleted',active_revision=NULL WHERE file_id=target;
        DELETE FROM public.ingestion_jobs WHERE file_id=target;
        DELETE FROM public.chunks WHERE file_id=target;
        DELETE FROM public.file_revisions WHERE file_id=target;
      END $$""")
    op.execute("""CREATE FUNCTION public.claim_storage_cleanup(token text) RETURNS SETOF public.storage_cleanup
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      UPDATE public.storage_cleanup SET attempts=attempts+1,lease_token=token,lease_until=now()+interval '1 minute'
      WHERE file_id=(SELECT file_id FROM public.storage_cleanup WHERE completed_at IS NULL AND attempts<5
        AND available_at<=now() AND (lease_until IS NULL OR lease_until<now())
        ORDER BY created_at,file_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING * $$""")
    op.execute("""CREATE FUNCTION public.cleanup_path_in_use(target text) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT EXISTS(SELECT 1 FROM public.files WHERE storage_path=target AND status<>'deleted') $$""")
    op.execute("""CREATE FUNCTION public.finish_storage_cleanup(target text,token text,success boolean) RETURNS void
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      UPDATE public.storage_cleanup SET completed_at=CASE WHEN success THEN now() ELSE NULL END,
        last_error=CASE WHEN success THEN NULL ELSE 'Cleanup failed; inspect worker configuration' END,
        lease_until=NULL,available_at=now()+interval '30 seconds'
      WHERE file_id=target AND lease_token=token AND lease_until>now() AND completed_at IS NULL $$""")
    for signature in ('queue_file_cleanup(text)', 'claim_storage_cleanup(text)', 'cleanup_path_in_use(text)', 'finish_storage_cleanup(text,text,boolean)'):
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC')


def downgrade():
    raise RuntimeError('Restore a verified backup to reverse cleanup migration')
