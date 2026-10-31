-- First apply runtime_grants.sql for this separate, trusted ingestion-worker role.
GRANT INSERT,UPDATE ON chunks,file_revisions TO :"runtime_role";
GRANT UPDATE ON ingestion_jobs TO :"runtime_role";
GRANT EXECUTE ON FUNCTION public.claim_ingestion_job(text) TO :"runtime_role";
GRANT EXECUTE ON FUNCTION public.fail_ingestion_job(text,text) TO :"runtime_role";
GRANT EXECUTE ON FUNCTION public.claim_campus_event(text), public.finish_campus_event(text,text,boolean) TO :"runtime_role";
