-- Run using psql as the migration owner:
-- psql "$DATABASE_URL" -v runtime_role=your_runtime_role -f migrations/runtime_grants.sql
-- The runtime role must already exist and must not own tables or bypass RLS.
GRANT USAGE ON SCHEMA public TO :"runtime_role";
GRANT SELECT (user_id,email,name,role,profile) ON users TO :"runtime_role";
GRANT UPDATE (name,password_hash) ON users TO :"runtime_role";
GRANT SELECT, INSERT, DELETE ON classrooms TO :"runtime_role";
GRANT UPDATE (updated_at) ON classrooms TO :"runtime_role";
GRANT SELECT, INSERT ON classroom_members TO :"runtime_role";
GRANT SELECT ON files, file_revisions, chunks, alembic_version TO :"runtime_role";
GRANT EXECUTE ON FUNCTION public.actor_role(), public.login_account(text),
    public.register_account(text,text,text,text,text,jsonb), public.join_classroom(text),
    public.can_read_classroom(text) TO :"runtime_role";
