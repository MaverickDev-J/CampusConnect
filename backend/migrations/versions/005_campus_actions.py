"""Atomic campus actions, recipient notifications, and a durable event outbox."""
from alembic import op

revision = "005_campus_actions"
down_revision = "004_files_chat"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN resource_id text")
    op.execute("CREATE UNIQUE INDEX notification_resource_recipient ON notifications(resource_id,user_id,type)")
    op.execute("""CREATE TABLE campus_operations (
      actor_id text NOT NULL REFERENCES users ON DELETE CASCADE, operation_key text NOT NULL,
      payload_hash text NOT NULL, result jsonb, PRIMARY KEY(actor_id,operation_key))""")
    op.execute("ALTER TABLE campus_operations ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY own_operation ON campus_operations FOR ALL USING (actor_id=current_setting('app.user_id',true)) WITH CHECK (actor_id=current_setting('app.user_id',true))")
    op.execute("""CREATE TABLE campus_outbox (
      event_id text PRIMARY KEY, actor_id text NOT NULL REFERENCES users ON DELETE CASCADE,
      classroom_id text, event_type text NOT NULL CHECK(event_type IN ('announcement_updated','calendar_updated')),
      resource_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      delivered_at timestamptz, attempts integer NOT NULL DEFAULT 0,
      lease_token text, lease_until timestamptz,
      available_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("ALTER TABLE campus_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY own_outbox ON campus_outbox FOR SELECT USING (actor_id=current_setting('app.user_id',true))""")
    op.execute("""CREATE POLICY create_outbox ON campus_outbox FOR INSERT WITH CHECK (
      actor_id=current_setting('app.user_id',true) AND
      (public.can_write_classroom(classroom_id) OR (classroom_id IS NULL AND public.actor_role()='superadmin')))""")
    for table, author in (("announcements", "author_id"), ("calendar_events", "created_by")):
        access = "public.can_write_classroom(classroom_id)"
        if table == "calendar_events":
            access += " OR (classroom_id IS NULL AND public.actor_role()='superadmin')"
        op.execute(f"CREATE POLICY create_action ON {table} FOR INSERT WITH CHECK ({author}=current_setting('app.user_id',true) AND ({access}))")
        op.execute(f"CREATE POLICY delete_action ON {table} FOR DELETE USING (({author}=current_setting('app.user_id',true) OR public.actor_role()='superadmin') AND ({access}))")
    op.execute("CREATE POLICY global_event_read ON calendar_events FOR SELECT USING (classroom_id IS NULL AND public.actor_role() IS NOT NULL)")
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    readable = "user_id=current_setting('app.user_id',true) AND (classroom_id IS NULL OR public.can_read_classroom(classroom_id))"
    op.execute(f"CREATE POLICY own_notification ON notifications FOR SELECT USING ({readable})")
    op.execute(f"CREATE POLICY read_notification ON notifications FOR UPDATE USING ({readable}) WITH CHECK ({readable})")
    op.execute("""CREATE POLICY create_notification ON notifications FOR INSERT WITH CHECK (
      ((public.can_write_classroom(classroom_id) AND EXISTS (
        SELECT 1 FROM classroom_members m WHERE m.classroom_id=notifications.classroom_id AND m.user_id=notifications.user_id))
        OR (classroom_id IS NULL AND public.actor_role()='superadmin'))
      AND ((type='announcement' AND EXISTS (SELECT 1 FROM announcements a WHERE a.announcement_id=resource_id
        AND a.classroom_id=notifications.classroom_id AND a.author_id=current_setting('app.user_id',true)))
        OR (type='event' AND EXISTS (SELECT 1 FROM calendar_events e WHERE e.event_id=resource_id
          AND e.classroom_id IS NOT DISTINCT FROM notifications.classroom_id AND e.created_by=current_setting('app.user_id',true)))))""")
    op.execute("""CREATE FUNCTION public.claim_campus_event(token text) RETURNS SETOF public.campus_outbox
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      UPDATE public.campus_outbox SET attempts=attempts+1,lease_token=token,lease_until=now()+interval '1 minute'
      WHERE event_id=(SELECT event_id FROM public.campus_outbox WHERE delivered_at IS NULL
        AND attempts<5 AND available_at<=now() AND (lease_until IS NULL OR lease_until<now())
        ORDER BY created_at,event_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING * $$""")
    op.execute("""CREATE FUNCTION public.finish_campus_event(target text,token text,success boolean) RETURNS void
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      UPDATE public.campus_outbox SET delivered_at=CASE WHEN success THEN now() ELSE NULL END,
        lease_until=NULL,available_at=now()+interval '30 seconds'
      WHERE event_id=target AND lease_token=token AND lease_until>now() AND delivered_at IS NULL $$""")
    for signature in ("claim_campus_event(text)", "finish_campus_event(text,text,boolean)"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")


def downgrade():
    raise RuntimeError("Restore a verified backup to reverse campus-action migration")
