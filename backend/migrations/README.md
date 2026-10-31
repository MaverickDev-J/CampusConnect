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
index. Migration 002 adds classroom read policies. Writes are deliberately denied
for a non-owner role until domain-specific policies and handlers are migrated.
Provision a separate non-owner runtime role; never use the migration owner to
claim row-security enforcement. Authentication/bootstrap access and broader user,
chat, and notification policies still need their own reviewed migration.

Integration tests require an explicitly selected disposable database and a test
owner that can create a temporary role. Fixtures are rolled back. Do not point
TEST_DATABASE_URL at production. Ordinary tests run without this variable and
report database tests as skipped.

On Windows, Psycopg async connections require a selector event loop. The async
integration test configures that policy before creating a loop; use the same
policy in any future Windows server entrypoint that enables PostgreSQL. Linux
containers on Modal do not require this override.

PostgreSQL runs in Docker for local development. On Modal the ASGI application
will connect to a persistent PostgreSQL service through DATABASE_URL; running the
database inside the web container is not part of this deployment.
