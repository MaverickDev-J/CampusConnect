"""Corpus-versioned answer caches and classroom-scoped operational reports."""
from alembic import op

revision='009_quality_cache'
down_revision='008_ai_budget'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE classroom_corpora (
      classroom_id text PRIMARY KEY REFERENCES classrooms ON DELETE CASCADE,
      version bigint NOT NULL DEFAULT 0)''')
    op.execute('INSERT INTO classroom_corpora(classroom_id) SELECT classroom_id FROM classrooms')
    op.execute('ALTER TABLE classroom_corpora ENABLE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY corpus_read ON classroom_corpora FOR SELECT USING(public.can_read_classroom(classroom_id))')
    op.execute('''CREATE FUNCTION public.initialize_corpus() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN INSERT INTO public.classroom_corpora(classroom_id) VALUES(NEW.classroom_id); RETURN NULL; END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.initialize_corpus() FROM PUBLIC')
    op.execute('CREATE TRIGGER initialize_corpus AFTER INSERT ON classrooms FOR EACH ROW EXECUTE FUNCTION public.initialize_corpus()')
    op.execute('''CREATE FUNCTION public.bump_corpus_version() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE scope text;
      BEGIN
        IF TG_TABLE_NAME='files' THEN
          scope := CASE WHEN TG_OP='DELETE' THEN OLD.classroom_id ELSE NEW.classroom_id END;
        ELSE
          SELECT classroom_id INTO scope FROM public.files WHERE file_id=
            CASE WHEN TG_OP='DELETE' THEN OLD.file_id ELSE NEW.file_id END
            AND status='ready' AND active_revision=CASE WHEN TG_OP='DELETE' THEN OLD.revision ELSE NEW.revision END;
        END IF;
        UPDATE public.classroom_corpora SET version=version+1 WHERE classroom_id=scope;
        RETURN NULL;
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.bump_corpus_version() FROM PUBLIC')
    op.execute('''CREATE FUNCTION public.lock_corpus(target text) RETURNS bigint
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE result bigint;
      BEGIN
        IF NOT public.can_write_classroom(target) OR public.actor_role() NOT IN ('teacher','superadmin') THEN
          RAISE EXCEPTION 'Faculty access required' USING ERRCODE='42501';
        END IF;
        SELECT version INTO result FROM public.classroom_corpora WHERE classroom_id=target FOR SHARE;
        RETURN result;
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.lock_corpus(text) FROM PUBLIC')
    op.execute('''CREATE TRIGGER file_corpus_version AFTER INSERT OR DELETE OR UPDATE OF status,active_revision,original_name,file_type
      ON files FOR EACH ROW EXECUTE FUNCTION public.bump_corpus_version()''')
    op.execute('''CREATE TRIGGER chunk_corpus_version AFTER INSERT OR DELETE OR UPDATE OF text,content_hash,embedding,title,page_number,revision,file_id
      ON chunks FOR EACH ROW EXECUTE FUNCTION public.bump_corpus_version()''')
    op.execute('''CREATE TRIGGER revision_corpus_version AFTER DELETE OR UPDATE OF status,embedding_namespace
      ON file_revisions FOR EACH ROW EXECUTE FUNCTION public.bump_corpus_version()''')
    op.execute('''CREATE TABLE answer_cache (
      cache_key text PRIMARY KEY, actor_id text NOT NULL REFERENCES users ON DELETE CASCADE,
      classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
      context_key text NOT NULL, answer text NOT NULL CHECK(length(answer)<=100000),
      sources jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL DEFAULT now()+interval '15 minutes')''')
    op.execute('CREATE INDEX answer_cache_expiry_idx ON answer_cache(expires_at)')
    op.execute('ALTER TABLE answer_cache ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY cache_owner ON answer_cache FOR ALL
      USING(actor_id=current_setting('app.user_id',true) AND public.can_read_classroom(classroom_id))
      WITH CHECK(actor_id=current_setting('app.user_id',true) AND public.can_read_classroom(classroom_id))''')
    op.execute('''CREATE TABLE ai_runs (
      run_id text PRIMARY KEY, actor_id text NOT NULL REFERENCES users ON DELETE CASCADE,
      classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
      kind text NOT NULL CHECK(kind IN ('chat','comparison','evaluation')),
      origin text NOT NULL CHECK(origin IN ('live','synthetic','benchmark')),
      status text NOT NULL CHECK(status IN ('success','error','cancelled')),
      strategy text, cache_status text NOT NULL DEFAULT 'miss', fallback_reason text,
      duration_ms integer NOT NULL CHECK(duration_ms>=0), first_token_ms integer,
      source_ids jsonb NOT NULL DEFAULT '[]', events jsonb NOT NULL DEFAULT '[]',
      created_at timestamptz NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX ai_runs_scope_time_idx ON ai_runs(classroom_id,created_at DESC,run_id)')
    op.execute('ALTER TABLE ai_runs ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY run_read ON ai_runs FOR SELECT USING (
      public.can_read_classroom(classroom_id) AND
      (actor_id=current_setting('app.user_id',true) OR (public.actor_role() IN ('teacher','superadmin') AND public.can_write_classroom(classroom_id))))''')
    op.execute('''CREATE POLICY run_write ON ai_runs FOR INSERT WITH CHECK (
      actor_id=current_setting('app.user_id',true) AND public.can_read_classroom(classroom_id))''')
    op.execute('''CREATE TABLE evaluation_runs (
      evaluation_id text PRIMARY KEY, actor_id text NOT NULL REFERENCES users ON DELETE CASCADE,
      classroom_id text NOT NULL REFERENCES classrooms ON DELETE CASCADE,
      dataset_hash text NOT NULL, dataset_version text NOT NULL, corpus_version bigint NOT NULL,
      reviewed boolean NOT NULL, report jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX evaluations_scope_time_idx ON evaluation_runs(classroom_id,created_at DESC)')
    op.execute('ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY evaluation_faculty ON evaluation_runs FOR ALL
      USING(public.actor_role() IN ('teacher','superadmin') AND public.can_write_classroom(classroom_id))
      WITH CHECK(actor_id=current_setting('app.user_id',true) AND public.actor_role() IN ('teacher','superadmin') AND public.can_write_classroom(classroom_id))''')


def downgrade():
    raise RuntimeError('Restore a verified backup; do not silently discard reports')
