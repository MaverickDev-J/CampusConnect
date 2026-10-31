"""Apply Alembic and provision separate API/worker logins without printing secrets.

Run from backend after `neon init`:
  uv run python -m scripts.bootstrap_postgres --apply
Owner credentials come from ../.env.local; existing .env settings are preserved.
"""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import secrets

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values, set_key
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def migration_environment(url):
    previous = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('DATABASE_URL',None)
        else:
            os.environ['DATABASE_URL'] = previous


def provision_role(connection, role, pooled_url, existing_url, *, worker=False):
    previous = connection.execute('''SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole
      FROM pg_roles WHERE rolname=%s''',(role,)).fetchone()
    if previous:
        if any(previous):
            raise RuntimeError('Refusing to reuse a privileged runtime role')
        if not existing_url:
            raise RuntimeError('Role already exists but its local credential is missing; no password was changed')
        candidate, target = make_url(existing_url), make_url(pooled_url)
        if (candidate.username,candidate.host,candidate.database)!=(role,target.host,target.database):
            raise RuntimeError('Existing runtime credential belongs to another role or database')
        with psycopg.connect(existing_url,connect_timeout=15) as probe:
            probe.execute('SELECT 1')
        runtime_url = existing_url
    else:
        password = secrets.token_urlsafe(32)
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        runtime_url = make_url(pooled_url).set(username=role,password=password).render_as_string(hide_password=False)
    for filename in ('runtime_grants.sql', *(['worker_grants.sql'] if worker else [])):
        for statement in (ROOT/'migrations'/filename).read_text(encoding='utf-8').split(';'):
            if statement.strip():
                connection.execute(statement.replace(':"runtime_role"',sql.Identifier(role).as_string(connection)))
    return runtime_url


def bootstrap(source_env, target_env):
    source = dotenv_values(source_env)
    owner_url = source.get('DATABASE_URL_UNPOOLED')
    pooled_url = source.get('DATABASE_URL')
    if not owner_url or not pooled_url:
        raise RuntimeError('Source env needs DATABASE_URL and DATABASE_URL_UNPOOLED from Neon')
    if '-pooler.' in (make_url(owner_url).host or ''):
        raise RuntimeError('Migrations require the direct/unpooled owner connection')
    existing = dotenv_values(target_env) if target_env.exists() else {}
    with migration_environment(owner_url):
        command.upgrade(Config(str(ROOT/'alembic.ini')),'head')
    with psycopg.connect(owner_url,connect_timeout=20) as connection:
        api_url = provision_role(connection,'campusconnect_api',pooled_url,existing.get('DATABASE_URL'))
        worker_url = provision_role(connection,'campusconnect_worker',pooled_url,existing.get('WORKER_DATABASE_URL'),worker=True)
    # Roles are committed before credentials are stored; a rerun never rotates them.
    target_env.parent.mkdir(parents=True,exist_ok=True)
    target_env.touch(exist_ok=True)
    for key,value in {'DATABASE_URL':api_url,'WORKER_DATABASE_URL':worker_url,'MIGRATION_DATABASE_URL':owner_url}.items():
        set_key(str(target_env),key,value)
    return api_url,worker_url


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-env',type=Path,default=ROOT.parent/'.env.local')
    parser.add_argument('--target-env',type=Path,default=ROOT/'.env')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('Would apply Alembic, create API/worker roles, and update the target env. Use --apply to run.')
        return
    try:
        bootstrap(args.source_env.resolve(),args.target_env.resolve())
    except Exception as exc:
        # Driver errors can include connection strings; do not echo them.
        print('Database setup failed ('+type(exc).__name__+'). Credentials were not printed.')
        raise SystemExit(1) from None
    print('Schema applied. Restricted API/worker credentials saved locally; existing settings preserved.')


if __name__=='__main__':
    main()
