"""Account and classroom policies for the staged PostgreSQL API."""
from alembic import op

revision = "003_accounts"
down_revision = "002_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE classroom_members ADD COLUMN joined_at timestamptz NOT NULL DEFAULT now()")
    op.execute("""CREATE FUNCTION public.actor_role() RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
        AS $$ SELECT role FROM public.users WHERE user_id=current_setting('app.user_id',true) $$""")
    op.execute("""CREATE FUNCTION public.login_account(target_email text)
        RETURNS TABLE(user_id text,email text,name text,password text,role text,profile jsonb)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
        AS $$ SELECT user_id,email,name,password_hash,role,profile FROM public.users
              WHERE email=lower(trim(target_email)) $$""")
    op.execute("""CREATE FUNCTION public.register_account(id text, mail text, display_name text,
        hashed_password text, requested_role text, attributes jsonb) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        BEGIN
          IF requested_role NOT IN ('student','teacher') THEN
            RAISE EXCEPTION 'Invalid registration role' USING ERRCODE='23514';
          END IF;
          INSERT INTO public.users(user_id,email,name,password_hash,role,profile)
          VALUES(id,lower(trim(mail)),display_name,hashed_password,requested_role,attributes);
        END $$""")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY account_read ON users FOR SELECT USING (
        user_id=current_setting('app.user_id',true) OR public.actor_role()='superadmin'
        OR EXISTS (SELECT 1 FROM public.classroom_members m WHERE m.user_id=users.user_id
                   AND public.can_read_classroom(m.classroom_id)))""")
    op.execute("""CREATE POLICY account_update ON users FOR UPDATE
        USING (user_id=current_setting('app.user_id',true))
        WITH CHECK (user_id=current_setting('app.user_id',true))""")
    op.execute("""CREATE POLICY classroom_insert ON classrooms FOR INSERT WITH CHECK (
        created_by=current_setting('app.user_id',true) AND public.actor_role() IN ('teacher','superadmin'))""")
    op.execute("""CREATE POLICY classroom_update ON classrooms FOR UPDATE
        USING (created_by=current_setting('app.user_id',true) OR public.actor_role()='superadmin')
        WITH CHECK (created_by=current_setting('app.user_id',true) OR public.actor_role()='superadmin')""")
    op.execute("""CREATE POLICY classroom_delete ON classrooms FOR DELETE
        USING (created_by=current_setting('app.user_id',true) OR public.actor_role()='superadmin')""")
    op.execute("ALTER TABLE classroom_members ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY member_read ON classroom_members FOR SELECT USING (public.can_read_classroom(classroom_id))""")
    op.execute("""CREATE POLICY member_insert ON classroom_members FOR INSERT WITH CHECK (
        user_id=current_setting('app.user_id',true) AND EXISTS (
          SELECT 1 FROM classrooms c WHERE c.classroom_id=classroom_members.classroom_id
          AND c.created_by=current_setting('app.user_id',true)))""")
    op.execute("""CREATE FUNCTION public.join_classroom(code text)
        RETURNS TABLE(classroom_id text,name text,join_code text,already_member boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE target public.classrooms; actor text := current_setting('app.user_id',true);
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM public.users u WHERE u.user_id=actor) THEN
            RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501';
          END IF;
          SELECT * INTO target FROM public.classrooms c WHERE c.join_code=upper(trim(code)) FOR UPDATE;
          IF NOT FOUND THEN RETURN; END IF;
          RETURN QUERY SELECT target.classroom_id,target.name,target.join_code,
            EXISTS (SELECT 1 FROM public.classroom_members m WHERE m.classroom_id=target.classroom_id AND m.user_id=actor);
          INSERT INTO public.classroom_members(classroom_id,user_id) VALUES(target.classroom_id,actor)
            ON CONFLICT DO NOTHING;
          UPDATE public.classrooms c SET updated_at=now() WHERE c.classroom_id=target.classroom_id;
        END $$""")
    # Deployment grants these functions explicitly to the runtime group role.
    for signature in ("actor_role()", "login_account(text)",
                      "register_account(text,text,text,text,text,jsonb)", "join_classroom(text)"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")


def downgrade():
    raise RuntimeError("Restore a verified backup to reverse account-policy migration")
