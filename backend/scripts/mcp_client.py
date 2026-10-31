"""Independent Streamable HTTP client for the local staging MCP demo.

Set CAMPUS_API_TOKEN to an existing API access token, then from backend run:
  uv run python -m scripts.mcp_client list_courses
  uv run python -m scripts.mcp_client search_documents --args '{...}'
Approval is deliberately available only in the faculty review UI/API.
"""
import argparse
import asyncio
import json
import os
from urllib.parse import urlparse

import httpx
from fastmcp import Client


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool', choices=['list_courses','search_documents','get_document',
        'prepare_revision_session','get_workflow_status','execute_approved_revision_session'])
    parser.add_argument('--args', default='{}', help='JSON object of tool arguments')
    parser.add_argument('--url', default='http://127.0.0.1:8001', help='Staging API origin')
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        parser.error('Use an origin without credentials, path, query, or fragment')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost','127.0.0.1')):
        parser.error('Use HTTPS for hosted servers; HTTP is allowed only on loopback')
    try:
        arguments = json.loads(args.args)
        if not isinstance(arguments, dict):
            raise ValueError
    except (ValueError, TypeError):
        parser.error('--args must be a JSON object')
    token = os.environ.get('CAMPUS_API_TOKEN')
    if not token:
        parser.error('Set CAMPUS_API_TOKEN to your API access token')
    base = args.url.rstrip('/')
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
        response = await http.post(base+'/api/mcp/token', headers={'Authorization':'Bearer '+token})
        if response.status_code != 200:
            raise SystemExit('Could not obtain an MCP credential; check your login and staging URL')
        mcp_token = response.json()['access_token']
    async with Client(base+'/mcp/', auth=mcp_token, timeout=90) as client:
        result = await client.call_tool(args.tool, arguments)
        print(json.dumps(result.data, indent=2, default=str))


if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
