"""Administrator routes backed by current database role checks."""
import asyncio
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter,Depends,HTTPException,Query,Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError,DBAPIError

from api.dependencies import get_current_user
from core.security import hash_password
from database.postgres import principal_session
from models.schemas import ProvisionTeacherBody

router=APIRouter(prefix='/api/superadmin',tags=['Superadmin'])


async def admin_session_check(session):
    if (await session.execute(text('SELECT public.actor_role()'))).scalar_one()!='superadmin':
        raise HTTPException(403,'Administrator required')


@router.get('/users')
async def users(request:Request,role:Literal['student','teacher','superadmin']|None=None,
                page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),principal=Depends(get_current_user)):
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        await admin_session_check(session)
        params={'role':role,'limit':limit,'offset':(page-1)*limit}
        total=(await session.execute(text('SELECT count(*) FROM users WHERE CAST(:role AS text) IS NULL OR role=:role'),params)).scalar_one()
        rows=(await session.execute(text('''SELECT user_id,email,name,role,profile FROM users
          WHERE CAST(:role AS text) IS NULL OR role=:role ORDER BY name,user_id LIMIT :limit OFFSET :offset'''),params)).mappings().all()
        return {'users':[dict(row) for row in rows],'total':total,'count':len(rows),'page':page}


@router.post('/provision-teacher',status_code=201)
async def teacher(body:ProvisionTeacherBody,request:Request,principal=Depends(get_current_user)):
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        await admin_session_check(session)
    user={'user_id':'tea_'+uuid4().hex[:12],'email':body.email.lower().strip(),'name':body.name,
          'password':await asyncio.to_thread(hash_password,body.password),'role':'teacher','profile':{}}
    try:
        await request.app.state.accounts.create(user)
    except IntegrityError:
        raise HTTPException(409,'Email already registered') from None
    return {key:value for key,value in user.items() if key!='password'}


@router.delete('/users/{user_id}')
async def remove(user_id:str,request:Request,principal=Depends(get_current_user)):
    try:
        async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
            await admin_session_check(session)
            removed=(await session.execute(text('SELECT public.delete_campus_user(:id)'),{'id':user_id})).scalar_one()
            if not removed:
                raise HTTPException(404,'User not found')
    except DBAPIError as exc:
        code=getattr(exc.orig,'sqlstate',None)
        if code=='23503':raise HTTPException(409,'Transfer or remove owned classrooms, files and posts before deleting this account') from None
        if code=='22023':raise HTTPException(400,'Cannot delete your own administrator account') from None
        if code=='42501':raise HTTPException(403,'Administrator required') from None
        raise
    return {'message':'User deleted','user_id':user_id}
