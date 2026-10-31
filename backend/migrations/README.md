# PostgreSQL development

From the repository root:

```powershell
docker compose -f compose.postgres.yml up -d --wait
cd backend
$env:DATABASE_URL='postgresql+psycopg://campusconnect:campusconnect-local@127.0.0.1:5433/campusconnect'
uv run alembic upgrade head
$env:TEST_DATABASE_URL='postgresql://campusconnect:campusconnect-local@127.0.0.1:5433/campusconnect'
uv run python -m unittest discover -s tests -v
```

The Compose password is for loopback-only local development. Use a secret and TLS
for a hosted database. The application still uses the legacy store while route
migration is in progress; these migrations do not switch production traffic.

Migration 001 creates the first application tables, vector storage, and lexical
index. Migration 002 adds classroom read policies. Migration 003 adds account and
classroom write policies and narrow login, registration, and join functions.
Provision a separate non-owner login role and apply `runtime_grants.sql` with psql's
`runtime_role` variable set to that role. Never run the API as the migration owner.
Runtime credentials cannot select the password-hash column or update user roles.
Login's restricted function retrieves one account's credential for verification.
Profile and classroom access use current transaction-scoped identity.

Set DATABASE_URL to that runtime login, then run:

```powershell
uv run python postgres_main.py
```

The staging API listens on loopback port 8001 and serves the existing auth/profile
and classroom routes, plus `/health`. It rejects owner/bypass-RLS connections at
startup. Production `main:app` still uses the legacy store; the staging entrypoint
is for migration verification and will gain the remaining routes before cutover.
Keep it local until rate limiting, CORS, remaining routes, and deployment checks
are complete. Classroom deletion currently rejects classrooms with uploaded files
until durable file cleanup is migrated. No physical files are deleted by this slice.

Integration tests require an explicitly selected disposable database and a test
owner that can create temporary roles. SQL fixtures are rolled back; API fixtures
and restricted test roles are explicitly cleaned up. Do not point
TEST_DATABASE_URL at production. Ordinary tests run without this variable and
report database tests as skipped.

On Windows, Psycopg async connections require a selector event loop. The async
integration test and `python postgres_main.py` entrypoint configure that policy.
Linux
containers on Modal do not require this override.

PostgreSQL runs in Docker for local development. On Modal the ASGI application
will connect to a persistent PostgreSQL service through DATABASE_URL; running the
database inside the web container is not part of this deployment.
