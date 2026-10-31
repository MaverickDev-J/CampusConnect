"""Human review uses API credentials, separate from model-facing MCP credentials."""
from fastapi import APIRouter, Depends, Request

from api.agent.faculty_workflow import EditDraft, PrepareRevision, ReviewDraft
from api.dependencies import get_current_user
from mcp_server.auth import issue_mcp_token

router = APIRouter(prefix='/api', tags=['Faculty workflows'])


@router.post('/mcp/token')
async def mcp_token(principal=Depends(get_current_user)):
    return {'access_token': issue_mcp_token(principal['user_id'], principal['role']), 'token_type': 'Bearer', 'expires_in': 600}


@router.post('/workflows/revision', status_code=201)
async def prepare(body: PrepareRevision, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.prepare(principal, body)


@router.get('/workflows')
async def listing(classroom_id: str, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.list(principal, classroom_id)


@router.get('/workflows/{workflow_id}')
async def status(workflow_id: str, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.get(principal, workflow_id)


@router.patch('/workflows/{workflow_id}')
async def edit(workflow_id: str, body: EditDraft, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.edit(principal, workflow_id, body)


@router.post('/workflows/{workflow_id}/approve')
async def approve(workflow_id: str, body: ReviewDraft, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.review(principal, workflow_id, body, approve=True)


@router.post('/workflows/{workflow_id}/reject')
async def reject(workflow_id: str, body: ReviewDraft, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.review(principal, workflow_id, body, approve=False)


@router.post('/workflows/{workflow_id}/execute')
async def execute(workflow_id: str, request: Request, principal=Depends(get_current_user)):
    return await request.app.state.workflows.execute(principal, workflow_id)
