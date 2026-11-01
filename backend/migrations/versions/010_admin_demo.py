"""Administrative account parity and isolated, expiring public demo visitors."""
from alembic import op

revision='010_admin_demo'
down_revision='009_quality_cache'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('ALTER TABLE users ADD COLUMN demo_expires_at timestamptz')
    op.execute('''CREATE OR REPLACE FUNCTION public.actor_role() RETURNS text
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT role FROM public.users WHERE user_id=current_setting('app.user_id',true)
        AND (demo_expires_at IS NULL OR demo_expires_at>now()) $$''')
    op.execute('''CREATE OR REPLACE FUNCTION public.can_read_classroom(target text) RETURNS boolean
      LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT EXISTS(SELECT 1 FROM public.users u WHERE u.user_id=current_setting('app.user_id',true)
        AND (u.demo_expires_at IS NULL OR u.demo_expires_at>now()) AND
        (u.role='superadmin' OR EXISTS(SELECT 1 FROM public.classrooms c WHERE c.classroom_id=target AND c.created_by=u.user_id)
        OR EXISTS(SELECT 1 FROM public.classroom_members m WHERE m.classroom_id=target AND m.user_id=u.user_id))) $$''')
    op.execute('''CREATE FUNCTION public.delete_campus_user(target text) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF public.actor_role() IS DISTINCT FROM 'superadmin' THEN
          RAISE EXCEPTION 'Administrator required' USING ERRCODE='42501'; END IF;
        IF target=current_setting('app.user_id',true) THEN
          RAISE EXCEPTION 'Cannot delete your own administrator account' USING ERRCODE='22023'; END IF;
        DELETE FROM public.users WHERE user_id=target;
        RETURN FOUND;
      EXCEPTION WHEN foreign_key_violation THEN
        RAISE EXCEPTION 'Transfer or remove owned resources before deleting this account' USING ERRCODE='23503';
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.delete_campus_user(text) FROM PUBLIC')
    op.execute('''CREATE FUNCTION public.create_demo_guest(target text,credential text) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF left(target,9)<>'stu_demo_' OR length(target)>60 OR length(credential)<40 THEN
          RAISE EXCEPTION 'Invalid demo identity' USING ERRCODE='22023'; END IF;
        IF NOT EXISTS(SELECT 1 FROM public.files WHERE classroom_id='cls_demo_sandbox' AND status='ready' AND active_revision IS NOT NULL) THEN
          RAISE EXCEPTION 'Demo materials are not ready' USING ERRCODE='55000'; END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('campusconnect-demo-guests',0));
        DELETE FROM public.users WHERE demo_expires_at<now()-interval '1 hour';
        IF (SELECT count(*) FROM public.users WHERE demo_expires_at>now())>=50 THEN
          RAISE EXCEPTION 'Demo capacity reached' USING ERRCODE='53300'; END IF;
        INSERT INTO public.users(user_id,email,name,password_hash,role,profile,demo_expires_at)
          VALUES(target,target||'@demo.campusconnect.example.com','Demo Guest',credential,'student',jsonb_build_object('is_demo',true),now()+interval '1 hour');
        INSERT INTO public.classroom_members(classroom_id,user_id) VALUES('cls_demo_sandbox',target);
        RETURN target;
      END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.create_demo_guest(text,text) FROM PUBLIC')


def downgrade():
    raise RuntimeError('Restore a verified backup; preserve account history')
