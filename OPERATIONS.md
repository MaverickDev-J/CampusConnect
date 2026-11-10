# CampusConnect operations

The application uses Neon for persistent relational/vector data and a Modal v2 volume for uploads. PostgreSQL runs as a managed database, outside the Modal application container.

## Release checks

Run commands from `backend`, with the existing environment and dependencies. Keep connection strings and API tokens out of terminal output and Git.

```powershell
$env:TEST_DATABASE_URL='postgresql://campusconnect:campusconnect-local@127.0.0.1:5433/campusconnect'
$env:TEST_REDIS_URL='redis://127.0.0.1:6380/15'
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

Run `npm run build` from `frontend`. For schema changes, first run the disposable Neon recovery/migration rehearsal below; then run `.venv/Scripts/python.exe -m scripts.bootstrap_postgres --apply` from `backend`. Bootstrap applies Alembic and refreshes existing least-privilege API/worker grants without rotating their credentials.

Deploy the backend with `modal deploy modal_staging.py`. Frontend deployment uses `frontend/modal_staging.py` and requires the existing `CAMPUS_STAGING_API_URL` at build and runtime. On Windows, set `$env:PYTHONUTF8='1'` before Modal commands. The current schema is `012_operations`.

Deploy the frontend from `frontend` using the active API origin:

```powershell
$env:PYTHONUTF8='1'
$env:CAMPUS_STAGING_API_URL='https://yjoy1572--campusconnect-postgres-fastapi-app.us-east.modal.run'
modal deploy modal_staging.py
```

This builds the public API/WebSocket origins and faculty/quality feature switches into the frontend image. The existing frontend URL remains unchanged. After a UI release, check student and faculty views, light/dark preference persistence, mobile navigation, chat Markdown rendering, and scroll behaviour during streaming. UI polish does not change backend model latency or provider quotas.

After release, verify `/health`, a ready PDF, student SSE chat and citations, faculty review/approval, linked traces, and delivery. Do not run integration fixtures or fault injection against the main Neon branch.

## Traces and retention

`trace_id` links permitted workflow review/execute requests and their MCP stages; queued jobs store trace/parent IDs for ingestion, delivery, and physical cleanup. Chat traces identify their session. The faculty Quality page shows related activity. There is a 100-event bound per operation and a 200-row bound in a trace response, with truncation indicated. This is operational tracing of scoped operations, not a comprehensive security audit log.

Worker-only retention runs through Modal's hourly rescue. Each invocation handles at most four batches of 500 rows per category. It removes traces older than 14 days, evaluation reports older than 90 days, finished/expired budget calls older than 30 days, and expired answer-cache entries. It preserves users, files, course content, domain actions, workflows, and graph checkpoints. Recent budget history remains intact for quota accounting.

The owner-managed singleton `operational_settings` controls retention within database-enforced ranges. API roles cannot call the cleanup function. `last_cleanup_at` and `last_counts` record the last batch; the function's return gives invocation totals. Trigger a bounded cleanup with `modal run modal_staging.py::retain`, or `.venv/Scripts/python.exe -m scripts.prune_history --apply` using the worker connection. Do not reset budget records to bypass a provider limit.

Telemetry persistence is best effort with a three-second deadline. Approval and domain-action persistence are mandatory. Raw prompts, source text, credentials, and private reasoning do not belong in trace events.

## Isolated database recovery rehearsal

```powershell
.venv/Scripts/python.exe -m scripts.rehearse_restore --project lucky-silence-57200933 --profile campusconnect-joy
```

The operator's Neon CLI must already be authenticated. The script clones the default branch to a disposable source, commits then deletes a unique marker there, creates a second branch at the saved WAL position, verifies marker recovery and baseline row counts, and upgrades the recovered branch to current Alembic head. It refuses the live endpoint for the probe and leaves local connection files unchanged. Both branches are deleted in `finally`; inspect the private report's cleanup results after any interrupted run. The source cannot have an expiry because Neon forbids child branches on an expiring parent; the restored leaf expires in two hours as an additional fallback.

Report: `backend/storage/operations/restore-report.json`. Never reset or restore the main branch simply to rehearse. For a real incident, stop writes, determine the recovery point and missing-write window, create an isolated recovered branch, verify schema/domain counts and upload references, then prepare a controlled cutover and rollback. Neon point-in-time recovery **does not restore the Modal upload volume**. Deleting a PDF physically may leave older database snapshots referencing an unavailable file; recover files separately from a retained export/backup before cutover. This rehearsal verifies database recovery, not a complete file-backup policy or an RTO guarantee. Free-plan history is limited; confirm the project's current restore window in Neon before relying on it.

## Reproducible measurements

- `python -m scripts.benchmark_search`: local-only, explicit `TEST_DATABASE_URL`, 10,000 synthetic vectors by default, exact application retrieval, one/five principals, p50/p95/sample counts, plans, index sizes, and fixture cleanup. No provider calls; the loopback guard prevents accidental hosted seeding.
- `modal run modal_staging.py::measure_startup`: two fresh isolated containers using staging configuration; separates imports, application startup, warm health requests, and remote roundtrip. It does not interrupt the live app or spend provider quota.
- `python -m scripts.evaluate_retrieval --dataset <private-json> --url <api-origin> --output storage/evals/latest`: faculty `CAMPUS_API_TOKEN` required, rate-limited/resumable comparisons, paired dense/hybrid/rerank scores, current-corpus validation, source commit and provisional-label status. Existing comparison/report endpoints enforce authorization.
- `python -m scripts.evaluate_answers --dataset <private-json> --url <api-origin> --case-id <id> --trials 2`: faculty-only uncached benchmark chat, separate origin, temporary sessions cleaned afterward, private answer/evidence/timing output, manual correctness/citation/refusal rubric. Completed successful trials resume; an unavailable provider stops the run rather than counting a failed answer as a quality score.

Keep datasets, source excerpts, raw answers, auth files, screenshots, and operational JSON reports in ignored storage. Review labels independently of the model's rankings. Keep related paraphrases in the same split; report sample counts, fallbacks, missing measurements, and limited coverage. Provisional scores do not establish validated accuracy.

## Provider incidents

Groq supplies text generation/routing/reranking; Gemini supplies embeddings and optional multimodal extraction. An embedding outage can use lexical fallback; reranker failure retains the retrieval order; exhausted answer capacity returns a retryable user message. A 503 is a provider availability failure, not proof of an invalid API key. Check the recorded stage and provider status before rotating keys. Multiple keys from one project/organization do not create independent quotas.

Application limits reserve answer capacity. Real provider limits can be lower and can change. Observe retry timing; do not increase application caps merely to make a benchmark finish. Ingestion resumes through leased jobs and wake/rescue calls when capacity becomes available. The exact answer cache remains scoped and versioned; semantic reuse is disabled pending equivalence evaluation.

The current answer policy is `grounded-v3`: course answers use supplied evidence, acknowledge missing facts, and cite supporting pages. Totals require evidence of a complete enumeration. Groq context selection keeps whole passages within the existing input-token budget and reports budget omissions instead of cutting each passage to a fixed prefix. A changed policy hash invalidates earlier cache entries. The same policy applies to the Groq text path and Gemini text fallback. Prompt rules reduce unsupported answers; they do not establish a guarantee of factual correctness. Use the private rubric review and distinguish agent assessments from human signoff.

Faculty draft preparation calls MCP document search with optional reranking disabled. This preserves the non-chat text allowance for the draft instead of spending it on ranking first. Hybrid retrieval, membership checks and evidence validation still run. General MCP document search keeps reranking enabled by default; ordinary student chat is unchanged. The trace marks intentional reranking skips explicitly. More keys in the same provider organization do not resolve an application token-budget reservation.
