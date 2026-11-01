"""Provider-specific total-token limits without changing Gemini accounting."""
from alembic import op

revision='011_groq_budget'
down_revision='010_admin_demo'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""ALTER TABLE ai_budget_policies
      ADD COLUMN token_accounting text NOT NULL DEFAULT 'input' CHECK(token_accounting IN ('input','total')),
      ADD COLUMN tokens_per_day bigint CHECK(tokens_per_day>0),
      ADD COLUMN reserve_tpd bigint NOT NULL DEFAULT 0 CHECK(reserve_tpd>=0 AND (tokens_per_day IS NULL OR reserve_tpd<tokens_per_day)),
      ADD COLUMN rolling_day boolean NOT NULL DEFAULT false""")
    op.execute("""INSERT INTO ai_budget_policies(project_key,model,rpm,input_tpm,rpd,concurrent_requests,
      reserve_rpm,reserve_tpm,reserve_rpd,reserve_slots,token_accounting,tokens_per_day,reserve_tpd,rolling_day)
      VALUES('groq-default','openai/gpt-oss-120b',20,7000,600,2,2,4500,100,1,'total',160000,20000,true)""")
    op.execute("""CREATE OR REPLACE FUNCTION public.reserve_ai_call(target uuid, project text, target_model text,
      work text, input_estimate bigint, output_limit integer)
      RETURNS TABLE(allowed boolean,reason text,retry_after integer)
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE policy public.ai_budget_policies; stamp timestamptz; today date; priority boolean;
        recent bigint; tokens bigint; daily bigint; daily_tokens bigint; active bigint;
        headroom integer; token_headroom bigint; requested bigint; day_reset timestamptz;
      BEGIN
        IF work NOT IN ('answer','route','rerank','draft','embed_query','embed_document','extract','count')
          OR input_estimate<0 OR output_limit<0 OR output_limit>8192 THEN
          RAISE EXCEPTION 'Invalid inference reservation' USING ERRCODE='22023';
        END IF;
        SELECT * INTO policy FROM public.ai_budget_policies
          WHERE project_key=project AND model=target_model FOR UPDATE;
        IF NOT FOUND THEN RETURN QUERY SELECT false,'policy_missing',60; RETURN; END IF;
        stamp:=clock_timestamp(); today:=(stamp AT TIME ZONE 'America/Los_Angeles')::date;
        priority:=work IN ('answer','embed_query');
        IF policy.blocked_until>stamp THEN
          RETURN QUERY SELECT false,'provider_cooldown',greatest(1,ceil(extract(epoch FROM policy.blocked_until-stamp))::integer); RETURN;
        END IF;
        SELECT count(*) FILTER(WHERE created_at>stamp-interval '60 seconds'),
          coalesce(sum(charged) FILTER(WHERE created_at>stamp-interval '60 seconds'),0),
          count(*) FILTER(WHERE in_day),coalesce(sum(charged) FILTER(WHERE in_day),0),
          count(*) FILTER(WHERE finished_at IS NULL AND lease_until>stamp),
          min(created_at+interval '24 hours') FILTER(WHERE in_day)
          INTO recent,tokens,daily,daily_tokens,active,day_reset
          FROM (SELECT c.*,
            CASE WHEN policy.token_accounting='total'
              THEN greatest(reserved_input+reserved_output,coalesce(actual_input,0)+coalesce(actual_output,0))
              ELSE greatest(reserved_input,coalesce(actual_input,0)) END AS charged,
            CASE WHEN policy.rolling_day THEN created_at>stamp-interval '24 hours' ELSE quota_day=today END AS in_day
            FROM public.ai_budget_calls c WHERE project_key=project AND model=target_model
              AND (created_at>stamp-interval '24 hours' OR quota_day=today OR (finished_at IS NULL AND lease_until>stamp))) usage;
        IF NOT policy.rolling_day THEN day_reset:=((today+1)::timestamp AT TIME ZONE 'America/Los_Angeles'); END IF;
        requested:=input_estimate+CASE WHEN policy.token_accounting='total' THEN output_limit ELSE 0 END;
        headroom:=CASE WHEN priority THEN 0 ELSE policy.reserve_rpm END;
        token_headroom:=CASE WHEN priority THEN 0 ELSE policy.reserve_tpm END;
        IF daily>=policy.rpd-(CASE WHEN priority THEN 0 ELSE policy.reserve_rpd END) THEN
          RETURN QUERY SELECT false,'daily_limit',greatest(1,ceil(extract(epoch FROM day_reset-stamp))::integer); RETURN;
        END IF;
        IF policy.tokens_per_day IS NOT NULL AND daily_tokens+requested>
          policy.tokens_per_day-(CASE WHEN priority THEN 0 ELSE policy.reserve_tpd END) THEN
          RETURN QUERY SELECT false,'daily_token_limit',greatest(1,ceil(extract(epoch FROM coalesce(day_reset,stamp+interval '1 hour')-stamp))::integer); RETURN;
        END IF;
        IF recent>=policy.rpm-headroom THEN RETURN QUERY SELECT false,'request_limit',60; RETURN; END IF;
        IF tokens+requested>policy.input_tpm-token_headroom THEN RETURN QUERY SELECT false,'token_limit',60; RETURN; END IF;
        IF active>=policy.concurrent_requests-(CASE WHEN priority THEN 0 ELSE policy.reserve_slots END) THEN
          RETURN QUERY SELECT false,'concurrency_limit',5; RETURN;
        END IF;
        INSERT INTO public.ai_budget_calls(call_id,project_key,model,workload,reserved_input,reserved_output,created_at,quota_day,lease_until)
          VALUES(target,project,target_model,work,input_estimate,output_limit,stamp,today,stamp+interval '180 seconds');
        RETURN QUERY SELECT true,NULL::text,0;
      END $$""")


def downgrade():
    raise RuntimeError('Restore a verified backup; preserve provider usage accounting')
