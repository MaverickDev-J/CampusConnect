"""Shared project/model admission limits and privacy-preserving usage ledger."""
from alembic import op

revision = '008_ai_budget'
down_revision = '007_workflows'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE ai_budget_policies (
      project_key text NOT NULL, model text NOT NULL, rpm integer NOT NULL CHECK(rpm>0),
      input_tpm bigint NOT NULL CHECK(input_tpm>0), rpd integer NOT NULL CHECK(rpd>0),
      concurrent_requests integer NOT NULL CHECK(concurrent_requests>0),
      reserve_rpm integer NOT NULL CHECK(reserve_rpm>=0 AND reserve_rpm<rpm),
      reserve_tpm bigint NOT NULL CHECK(reserve_tpm>=0 AND reserve_tpm<input_tpm),
      reserve_rpd integer NOT NULL CHECK(reserve_rpd>=0 AND reserve_rpd<rpd),
      reserve_slots integer NOT NULL CHECK(reserve_slots>=0 AND reserve_slots<concurrent_requests),
      blocked_until timestamptz, PRIMARY KEY(project_key,model))''')
    op.execute('''INSERT INTO ai_budget_policies VALUES
      ('campusconnect-default','gemini-3.8-flash',4,32000,40,2,1,8000,5,1,NULL),
      ('campusconnect-default','gemini-embedding-2',10,16000,200,2,2,4000,20,1,NULL)''')
    op.execute('''CREATE TABLE ai_budget_calls (
      call_id uuid PRIMARY KEY, project_key text NOT NULL, model text NOT NULL,
      workload text NOT NULL CHECK(workload IN ('answer','route','rerank','draft','embed_query','embed_document','extract','count')),
      reserved_input bigint NOT NULL CHECK(reserved_input>=0), reserved_output integer NOT NULL CHECK(reserved_output>=0),
      actual_input bigint CHECK(actual_input>=0), actual_output bigint CHECK(actual_output>=0),
      actual_thinking bigint CHECK(actual_thinking>=0),
      created_at timestamptz NOT NULL, quota_day date NOT NULL, lease_until timestamptz NOT NULL,
      finished_at timestamptz, outcome text NOT NULL DEFAULT 'pending'
        CHECK(outcome IN ('pending','success','error','cancelled')),
      provider_status integer, FOREIGN KEY(project_key,model) REFERENCES ai_budget_policies(project_key,model))''')
    op.execute('CREATE INDEX ai_budget_recent_idx ON ai_budget_calls(project_key,model,created_at DESC)')
    op.execute('CREATE INDEX ai_budget_day_idx ON ai_budget_calls(project_key,model,quota_day)')
    for table in ('ai_budget_policies','ai_budget_calls'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute('''CREATE FUNCTION public.reserve_ai_call(target uuid, project text, target_model text,
      work text, input_estimate bigint, output_limit integer)
      RETURNS TABLE(allowed boolean,reason text,retry_after integer)
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE policy public.ai_budget_policies; stamp timestamptz; today date; priority boolean;
        recent bigint; tokens bigint; daily bigint; active bigint; headroom integer; token_headroom bigint;
      BEGIN
        IF work NOT IN ('answer','route','rerank','draft','embed_query','embed_document','extract','count')
          OR input_estimate<0 OR output_limit<0 OR output_limit>8192 THEN
          RAISE EXCEPTION 'Invalid inference reservation' USING ERRCODE='22023';
        END IF;
        SELECT * INTO policy FROM public.ai_budget_policies
          WHERE project_key=project AND model=target_model FOR UPDATE;
        IF NOT FOUND THEN RETURN QUERY SELECT false,'policy_missing',60; RETURN; END IF;
        stamp := clock_timestamp(); today := (stamp AT TIME ZONE 'America/Los_Angeles')::date;
        priority := work IN ('answer','embed_query');
        IF policy.blocked_until>stamp THEN
          RETURN QUERY SELECT false,'provider_cooldown',greatest(1,ceil(extract(epoch FROM policy.blocked_until-stamp))::integer); RETURN;
        END IF;
        SELECT count(*) FILTER(WHERE created_at>stamp-interval '60 seconds'),
          coalesce(sum(greatest(reserved_input,coalesce(actual_input,0))) FILTER(WHERE created_at>stamp-interval '60 seconds'),0),
          count(*) FILTER(WHERE quota_day=today),
          count(*) FILTER(WHERE finished_at IS NULL AND lease_until>stamp)
          INTO recent,tokens,daily,active FROM public.ai_budget_calls
          WHERE project_key=project AND model=target_model
            AND (created_at>stamp-interval '60 seconds' OR quota_day=today OR (finished_at IS NULL AND lease_until>stamp));
        headroom := CASE WHEN priority THEN 0 ELSE policy.reserve_rpm END;
        token_headroom := CASE WHEN priority THEN 0 ELSE policy.reserve_tpm END;
        IF daily>=policy.rpd-(CASE WHEN priority THEN 0 ELSE policy.reserve_rpd END) THEN
          RETURN QUERY SELECT false,'daily_limit',greatest(1,ceil(extract(epoch FROM
            ((today+1)::timestamp AT TIME ZONE 'America/Los_Angeles')-stamp))::integer); RETURN;
        END IF;
        IF recent>=policy.rpm-headroom THEN RETURN QUERY SELECT false,'request_limit',60; RETURN; END IF;
        IF tokens+input_estimate>policy.input_tpm-token_headroom THEN RETURN QUERY SELECT false,'token_limit',60; RETURN; END IF;
        IF active>=policy.concurrent_requests-(CASE WHEN priority THEN 0 ELSE policy.reserve_slots END) THEN
          RETURN QUERY SELECT false,'concurrency_limit',5; RETURN;
        END IF;
        INSERT INTO public.ai_budget_calls(call_id,project_key,model,workload,reserved_input,reserved_output,created_at,quota_day,lease_until)
          VALUES(target,project,target_model,work,input_estimate,output_limit,stamp,today,stamp+interval '180 seconds');
        RETURN QUERY SELECT true,NULL::text,0;
      END $$''')
    op.execute('''CREATE FUNCTION public.finish_ai_call(target uuid, result text, input_used bigint,
      output_used bigint, thinking_used bigint, status integer, cooldown integer) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE project text; target_model text;
      BEGIN
        IF result NOT IN ('success','error','cancelled') OR input_used<0 OR output_used<0 OR thinking_used<0
          OR cooldown<0 OR cooldown>86400 THEN RAISE EXCEPTION 'Invalid inference result' USING ERRCODE='22023'; END IF;
        SELECT project_key,model INTO project,target_model FROM public.ai_budget_calls WHERE call_id=target AND finished_at IS NULL;
        IF NOT FOUND THEN RETURN; END IF;
        PERFORM 1 FROM public.ai_budget_policies WHERE project_key=project AND model=target_model FOR UPDATE;
        UPDATE public.ai_budget_calls SET finished_at=clock_timestamp(),outcome=result,
          actual_input=input_used,actual_output=output_used,actual_thinking=thinking_used,provider_status=status
          WHERE call_id=target AND finished_at IS NULL;
        IF FOUND AND cooldown>0 THEN
          UPDATE public.ai_budget_policies SET blocked_until=greatest(coalesce(blocked_until,clock_timestamp()),
            clock_timestamp()+make_interval(secs=>cooldown)) WHERE project_key=project AND model=target_model;
        END IF;
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.reserve_ai_call(uuid,text,text,text,bigint,integer) FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION public.finish_ai_call(uuid,text,bigint,bigint,bigint,integer,integer) FROM PUBLIC')
    op.execute('''CREATE FUNCTION public.defer_ingestion_job(target text,token text,delay_seconds integer) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF delay_seconds<1 OR delay_seconds>86400 THEN RAISE EXCEPTION 'Invalid retry delay'; END IF;
        UPDATE public.ingestion_jobs SET state='pending',attempts=greatest(0,attempts-1),
          available_at=clock_timestamp()+make_interval(secs=>delay_seconds+floor(random()*5)::integer),
          lease_until=NULL,lease_token=NULL,last_error='Waiting for AI capacity'
          WHERE file_id=target AND lease_token=token AND state='working' AND lease_until>now();
        IF FOUND THEN UPDATE public.files SET status='pending',processing_error=NULL
          WHERE file_id=target AND status<>'deleted'; END IF;
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.defer_ingestion_job(text,text,integer) FROM PUBLIC')


def downgrade():
    raise RuntimeError('Restore a verified backup; usage records must not silently reset')
