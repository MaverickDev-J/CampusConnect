"""Correlated operation traces and worker-only bounded telemetry retention."""
from alembic import op

revision='012_operations'
down_revision='011_groq_budget'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("ALTER TABLE ai_runs DROP CONSTRAINT ai_runs_kind_check")
    op.execute("ALTER TABLE ai_runs ADD CHECK(kind IN ('chat','comparison','evaluation','workflow','mcp','ingestion','delivery','cleanup'))")
    op.execute('''ALTER TABLE ai_runs ADD COLUMN trace_id text, ADD COLUMN parent_run_id text,
      ADD COLUMN resource_type text, ADD COLUMN resource_id text''')
    op.execute('UPDATE ai_runs SET trace_id=run_id')
    op.execute('ALTER TABLE ai_runs ALTER COLUMN trace_id SET NOT NULL')
    op.execute('''CREATE FUNCTION public.initialize_trace_identity() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog AS $$ BEGIN NEW.trace_id:=coalesce(nullif(NEW.trace_id,''),NEW.run_id); RETURN NEW; END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.initialize_trace_identity() FROM PUBLIC')
    op.execute('CREATE TRIGGER initialize_trace_identity BEFORE INSERT ON ai_runs FOR EACH ROW EXECUTE FUNCTION public.initialize_trace_identity()')
    op.execute('CREATE INDEX ai_runs_trace_idx ON ai_runs(trace_id,created_at,run_id)')
    op.execute('CREATE INDEX ai_runs_expiry_idx ON ai_runs(created_at,run_id)')
    op.execute('CREATE INDEX evaluation_runs_expiry_idx ON evaluation_runs(created_at,evaluation_id)')
    op.execute('CREATE INDEX ai_budget_calls_expiry_idx ON ai_budget_calls(created_at,call_id)')
    op.execute('ALTER TABLE faculty_workflows ADD COLUMN trace_id text')
    op.execute("UPDATE faculty_workflows SET trace_id='legacy_'||workflow_id")
    for table in ('ingestion_jobs','campus_outbox','storage_cleanup'):
        op.execute(f'ALTER TABLE {table} ADD COLUMN trace_id text, ADD COLUMN parent_run_id text')
    op.execute('ALTER TABLE storage_cleanup ADD COLUMN classroom_id text')
    op.execute('''CREATE TABLE operational_settings (
      singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
      trace_days integer NOT NULL DEFAULT 14 CHECK(trace_days BETWEEN 7 AND 90),
      evaluation_days integer NOT NULL DEFAULT 90 CHECK(evaluation_days BETWEEN 30 AND 365),
      budget_days integer NOT NULL DEFAULT 30 CHECK(budget_days BETWEEN 7 AND 365),
      last_cleanup_at timestamptz,last_counts jsonb NOT NULL DEFAULT '{}')''')
    op.execute('INSERT INTO operational_settings(singleton) VALUES(true)')
    op.execute('ALTER TABLE operational_settings ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE FUNCTION public.prune_ai_history(batch_size integer DEFAULT 500) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE settings public.operational_settings; traces integer; evaluations integer; budgets integer; caches integer;
      BEGIN
        IF batch_size IS NULL OR batch_size<1 OR batch_size>2000 THEN RAISE EXCEPTION 'Invalid cleanup batch' USING ERRCODE='22023'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('campusconnect-telemetry-retention',0));
        SELECT * INTO STRICT settings FROM public.operational_settings WHERE singleton;
        WITH expired AS (SELECT run_id FROM public.ai_runs WHERE created_at<now()-make_interval(days=>settings.trace_days)
          ORDER BY created_at,run_id LIMIT batch_size FOR UPDATE SKIP LOCKED)
          DELETE FROM public.ai_runs r USING expired e WHERE r.run_id=e.run_id;
        GET DIAGNOSTICS traces=ROW_COUNT;
        WITH expired AS (SELECT evaluation_id FROM public.evaluation_runs WHERE created_at<now()-make_interval(days=>settings.evaluation_days)
          ORDER BY created_at,evaluation_id LIMIT batch_size FOR UPDATE SKIP LOCKED)
          DELETE FROM public.evaluation_runs r USING expired e WHERE r.evaluation_id=e.evaluation_id;
        GET DIAGNOSTICS evaluations=ROW_COUNT;
        WITH expired AS (SELECT call_id FROM public.ai_budget_calls WHERE created_at<now()-make_interval(days=>settings.budget_days)
          AND (finished_at IS NOT NULL OR lease_until<now()) ORDER BY created_at,call_id LIMIT batch_size FOR UPDATE SKIP LOCKED)
          DELETE FROM public.ai_budget_calls r USING expired e WHERE r.call_id=e.call_id;
        GET DIAGNOSTICS budgets=ROW_COUNT;
        WITH expired AS (SELECT cache_key FROM public.answer_cache WHERE expires_at<now()
          ORDER BY expires_at,cache_key LIMIT batch_size FOR UPDATE SKIP LOCKED)
          DELETE FROM public.answer_cache r USING expired e WHERE r.cache_key=e.cache_key;
        GET DIAGNOSTICS caches=ROW_COUNT;
        UPDATE public.operational_settings SET last_cleanup_at=clock_timestamp(),last_counts=
          jsonb_build_object('traces',traces,'evaluations',evaluations,'budget_calls',budgets,'caches',caches) WHERE singleton;
        RETURN jsonb_build_object('traces',traces,'evaluations',evaluations,'budget_calls',budgets,'caches',caches);
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.prune_ai_history(integer) FROM PUBLIC')
    op.execute('''CREATE OR REPLACE FUNCTION public.queue_file_cleanup(target text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE document public.files;
      BEGIN
        PERFORM 1 FROM public.ingestion_jobs WHERE file_id=target FOR UPDATE;
        SELECT * INTO document FROM public.files WHERE file_id=target FOR UPDATE;
        IF NOT FOUND OR NOT public.can_write_classroom(document.classroom_id) THEN
          RAISE EXCEPTION 'File not accessible' USING ERRCODE='42501'; END IF;
        INSERT INTO public.storage_cleanup(file_id,storage_path,actor_id,classroom_id,trace_id,parent_run_id)
          VALUES(target,document.storage_path,current_setting('app.user_id',true),document.classroom_id,
            nullif(current_setting('app.trace_id',true),''),nullif(current_setting('app.run_id',true),'')) ON CONFLICT DO NOTHING;
        UPDATE public.files SET status='deleted',active_revision=NULL WHERE file_id=target;
        DELETE FROM public.ingestion_jobs WHERE file_id=target;
        DELETE FROM public.chunks WHERE file_id=target;
        DELETE FROM public.file_revisions WHERE file_id=target;
      END $$''')


def downgrade():
    raise RuntimeError('Restore a verified backup; preserve operational records')
