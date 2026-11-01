"""Guest identities are isolated, short-lived, and cannot write campus content."""
import asyncio
from datetime import timedelta
import os
from uuid import uuid4

from fastapi import APIRouter,HTTPException,Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.security import create_access_token,hash_password

router=APIRouter(tags=['Demo'])


@router.post('/api/auth/demo-login')
async def demo(request:Request):
    if os.getenv('DEMO_ENABLED','false').lower()!='true':
        raise HTTPException(503,'Demo access is not enabled')
    user_id='stu_demo_'+uuid4().hex
    credential=await asyncio.to_thread(hash_password,uuid4().hex)
    try:
        async with request.app.state.accounts.factory() as session,session.begin():
            await session.execute(text('SELECT public.create_demo_guest(:id,:credential)'),{'id':user_id,'credential':credential})
    except DBAPIError as exc:
        if getattr(exc.orig,'sqlstate',None)=='53300':
            raise HTTPException(429,'Demo capacity is currently full; please try later',headers={'Retry-After':'300'}) from None
        raise HTTPException(503,'Demo materials are not ready yet') from None
    return {'access_token':create_access_token({'user_id':user_id,'role':'student'},timedelta(hours=1)),'token_type':'bearer'}
