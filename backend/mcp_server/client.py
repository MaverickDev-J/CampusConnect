"""First-party workflow adapter: real MCP calls, request-local credentials."""
import httpx
from fastapi import HTTPException
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from mcp_server.auth import issue_mcp_token
from core.telemetry import stage


class McpDocumentsClient:
    def __init__(self, app):
        self.app = app

    async def search(self, principal, classroom_id, query):
        # Stateless JSON HTTP also works inside the serving process. This uses
        # the same protocol/auth middleware as external clients without a second
        # service or a public self-request. Tokens never enter graph checkpoints.
        def client_factory(**kwargs):
            kwargs['timeout'] = httpx.Timeout(45)
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), **kwargs)

        transport = StreamableHttpTransport('http://campusconnect-internal/mcp/',
            auth=issue_mcp_token(principal['user_id'], principal['role']), httpx_client_factory=client_factory)
        try:
            async with Client(transport, timeout=45) as client:
                with stage('mcp.client.search_documents'):
                    # Faculty preparation needs the text budget for its draft.
                    # Hybrid retrieval supplies evidence without another Groq call.
                    return (await client.call_tool('search_documents', {'classroom_id': classroom_id, 'query': query,'rerank':False})).data
        except (ToolError, httpx.HTTPError, TimeoutError):
            raise HTTPException(503, 'Course document tools are unavailable; please retry') from None
