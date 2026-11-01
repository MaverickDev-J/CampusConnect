"""Hosting adapters; PostgreSQL queues remain the source of job truth."""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class VolumeRequests:
    """Serialize local volume reloads against open upload/download handles."""

    def __init__(self, app, *, reload):
        self.app, self.reload = app, reload
        self.lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not (path.startswith('/api/files') or path == '/api/upload/file'):
            return await self.app(scope, receive, send)
        async with self.lock:
            await self.reload()
            await self.app(scope, receive, send)


class WakeJobs:
    """Await enqueue, never leave a fire-and-forget task in an idle web process."""

    def __init__(self, app, *, wake):
        self.app, self.wake = app, wake

    async def __call__(self, scope, receive, send):
        status = 500

        async def observe(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        await self.app(scope, receive, observe)
        if scope['type'] != 'http' or not 200 <= status < 300:
            return
        path, method = scope.get('path',''), scope.get('method','GET')
        poll = method == 'GET' and (path == '/api/files' or
            (path.startswith('/api/files/') and not path.endswith('/download')))
        mutation = method in {'POST','PUT','PATCH','DELETE'} and (
            path.startswith(('/api/upload/','/api/files/','/api/classrooms','/api/announcements',
                             '/api/calendar','/api/workflows','/mcp')))
        if poll or mutation:
            try:
                await self.wake('ingestion' if poll or path == '/api/upload/file' or path.endswith('/retry') else 'delivery')
            except Exception:
                # The hourly rescue sweep recovers a commit/enqueue crash gap.
                logger.warning('Worker wake failed; committed jobs remain queued')


async def drain(*workers, max_rounds=20, max_seconds=45):
    """Stop when empty; leases and retry timestamps are owned by each worker."""
    started, handled = time.monotonic(), 0
    for _ in range(max_rounds):
        progress = False
        for worker in workers:
            progress = await worker.run_once() or progress
        if not progress:
            break
        handled += 1
        if time.monotonic() - started >= max_seconds:
            break
    return handled
