"""Faculty-only reports derived from scoped traces and actual retrieval runs."""
import hashlib
import json
import math
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter,Depends,HTTPException,Query,Request
from pydantic import BaseModel,Field
from sqlalchemy import text

from api.dependencies import get_current_user
from api.services.retrieval.postgres_search import PostgresSearch
from core.telemetry import RunTrace,current_trace,stage,save_trace
from database.postgres import principal_session

router=APIRouter(prefix='/api/quality',tags=['Quality'])


async def faculty(request,principal,classroom_id):
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        role=(await session.execute(text('SELECT public.actor_role()'))).scalar_one()
        if role not in ('teacher','superadmin'):
            raise HTTPException(403,'Faculty access required')
        await request.app.state.actions._authorize(session,classroom_id,write=True)
        return (await session.execute(text('SELECT version FROM classroom_corpora WHERE classroom_id=:id'),{'id':classroom_id})).scalar_one()


@router.get('/overview')
async def overview(request:Request,classroom_id:str,origin:Literal['live','synthetic','benchmark']='live',principal=Depends(get_current_user)):
    await faculty(request,principal,classroom_id)
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        row=(await session.execute(text('''SELECT count(*) AS requests,count(*) FILTER(WHERE status='error') AS errors,
          count(*) FILTER(WHERE status='cancelled') AS cancelled,count(*) FILTER(WHERE fallback_reason IS NOT NULL) AS fallbacks,
          count(*) FILTER(WHERE cache_status='exact') AS cache_hits,
          percentile_cont(0.5) WITHIN GROUP(ORDER BY duration_ms) AS p50_ms,
          percentile_cont(0.95) WITHIN GROUP(ORDER BY duration_ms) AS p95_ms
          FROM ai_runs WHERE classroom_id=:id AND origin=:origin AND created_at>now()-interval '14 days' '''),
          {'id':classroom_id,'origin':origin})).mappings().one()
        usage=(await session.execute(text('''SELECT
          sum((event->>'input_tokens')::bigint) AS input_tokens,
          sum((event->>'output_tokens')::bigint) AS output_tokens,
          count(*) FILTER(WHERE event->>'input_tokens' IS NOT NULL) AS measured_calls
          FROM ai_runs r CROSS JOIN LATERAL jsonb_array_elements(r.events) event
          WHERE r.classroom_id=:id AND r.origin=:origin AND r.created_at>now()-interval '14 days'
          AND event->>'stage' LIKE 'provider.%%' '''),{'id':classroom_id,'origin':origin})).mappings().one()
        return {**dict(row),'usage':dict(usage),'origin':origin,'window_days':14,'cost_estimate':None}


@router.get('/runs')
async def runs(request:Request,classroom_id:str,page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),principal=Depends(get_current_user)):
    await faculty(request,principal,classroom_id)
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        rows=(await session.execute(text('''SELECT * FROM ai_runs WHERE classroom_id=:id
          ORDER BY created_at DESC,run_id LIMIT :limit OFFSET :offset'''),
          {'id':classroom_id,'limit':limit,'offset':(page-1)*limit})).mappings().all()
        return {'runs':[dict(row) for row in rows],'page':page}


class CompareInput(BaseModel):
    classroom_id:str=Field(min_length=1,max_length=100)
    query:str=Field(min_length=1,max_length=2000)
    origin:Literal['live','synthetic','benchmark']='live'


@router.post('/compare')
async def compare(body:CompareInput,request:Request,principal=Depends(get_current_user)):
    corpus=await faculty(request,principal,body.classroom_id)
    rag=request.app.state.rag
    trace=RunTrace()
    token=current_trace.set(trace)
    state={'user_id':principal['user_id'],'scope_classroom_id':body.classroom_id,'query':body.query,'used_sources':[]}
    outcome='error'
    try:
        state.update(await rag.embed(state))
        results={}
        ranked={}
        for name in ('dense','hybrid'):
            if name=='dense' and state.get('query_embedding') is None:
                results[name]={'status':'unavailable','reason':'embedding_unavailable','sources':[],'candidate_ids':[]}
                continue
            strategy=name if state.get('query_embedding') else 'lexical'
            with stage('compare.'+name,strategy=strategy) as event:
                async with principal_session(rag.factory,principal['user_id']) as session:
                    candidates=await PostgresSearch(session).search(body.query,state.get('query_embedding'),classroom_id=body.classroom_id,strategy=strategy)
                ranked[name]=candidates
                _,sources=await rag.evidence(state,candidates)
                event['candidate_count']=len(candidates)
            results[name]={'status':'success','strategy':strategy,'sources':sources,
                           'candidate_ids':[c.chunk_id for c in candidates],'duration_ms':event['duration_ms']}
        candidates=ranked.get('hybrid',[])
        fallback='reranker_unavailable'
        with stage('compare.hybrid_rerank') as event:
            if rag.reranker:
                ranking=await rag.reranker.rerank(body.query,candidates)
                candidates,fallback=ranking.candidates,ranking.fallback_reason
            _,sources=await rag.evidence(state,candidates)
        results['hybrid_rerank']={'status':'success','strategy':results['hybrid']['strategy']+'+rerank' if not fallback else results['hybrid']['strategy'],
            'sources':sources,'candidate_ids':[c.chunk_id for c in candidates],'fallback_reason':fallback,'duration_ms':event['duration_ms']}
        if await faculty(request,principal,body.classroom_id)!=corpus:
            raise HTTPException(409,'Corpus changed during comparison; retry')
        trace.events.append({'stage':'comparison_results','rankings':{key:value['candidate_ids'] for key,value in results.items()},
                             'strategies':{key:{field:value.get(field) for field in ('status','strategy','fallback_reason')} for key,value in results.items()},
                             'query_hash':hashlib.sha256(body.query.encode()).hexdigest(),'corpus_version':corpus})
        state.update(used_sources=sources,retrieval_strategy='comparison',rerank_fallback_reason=fallback)
        outcome='success'
        return {'run_id':trace.run_id,'corpus_version':corpus,'strategies':results,'cache':'disabled',
                'embedding_namespace':rag.embeddings.settings.namespace}
    finally:
        current_trace.reset(token)
        await save_trace(rag.factory,principal,body.classroom_id,trace,state,outcome,kind='comparison',origin=body.origin)


class EvaluationCase(BaseModel):
    case_id:str=Field(min_length=1,max_length=100)
    run_id:str=Field(min_length=1,max_length=100)
    relevant_chunk_ids:list[str]=Field(max_length=60)


class EvaluationInput(BaseModel):
    classroom_id:str
    dataset_version:str=Field(min_length=1,max_length=100)
    reviewed:bool=False
    source_commit:str|None=Field(None,max_length=64)
    source_dirty:bool=False
    cases:list[EvaluationCase]=Field(min_length=1,max_length=60)


def metrics(ranking,relevant,k=6):
    relevant=set(relevant)
    if not relevant:
        return {'recall_at_12':None,'ndcg_at_6':None,'label':'unanswerable; answer/refusal grading required'}
    dcg=sum(1/math.log2(i+2) for i,cid in enumerate(ranking[:k]) if cid in relevant)
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
    return {'recall_at_12':len(set(ranking[:12])&relevant)/len(relevant),'ndcg_at_6':dcg/ideal}


@router.post('/evaluations',status_code=201)
async def evaluation(body:EvaluationInput,request:Request,principal=Depends(get_current_user)):
    corpus=await faculty(request,principal,body.classroom_id)
    if len({case.case_id for case in body.cases})!=len(body.cases):
        raise HTTPException(422,'Case IDs must be unique')
    factory=request.app.state.accounts.factory
    async with principal_session(factory,principal['user_id']) as session:
        current=(await session.execute(text('SELECT public.lock_corpus(:id)'),{'id':body.classroom_id})).scalar_one()
        if current!=corpus:
            raise HTTPException(409,'Corpus changed; retry the evaluation')
        rows=(await session.execute(text('''SELECT run_id,events,status,origin FROM ai_runs
          WHERE classroom_id=:classroom AND kind='comparison' AND run_id=ANY(CAST(:ids AS text[]))'''),
          {'classroom':body.classroom_id,'ids':[case.run_id for case in body.cases]})).mappings().all()
        traces={row['run_id']:row for row in rows}
        cases=[]
        for case in body.cases:
            run=traces.get(case.run_id)
            event=next((event for event in run['events'] if event['stage']=='comparison_results'),None) if run else None
            if not event or run['status']!='success' or run['origin'] not in ('benchmark','synthetic') or event['corpus_version']!=corpus:
                raise HTTPException(409,'Evaluation requires successful benchmark/synthetic comparisons against the current corpus')
            if case.relevant_chunk_ids:
                count=(await session.execute(text('''SELECT count(*) FROM chunks c JOIN files f ON f.file_id=c.file_id
                  WHERE c.chunk_id=ANY(CAST(:ids AS text[])) AND c.classroom_id=:classroom AND f.status='ready' AND f.active_revision=c.revision'''),
                  {'ids':case.relevant_chunk_ids,'classroom':body.classroom_id})).scalar_one()
                if count!=len(set(case.relevant_chunk_ids)):
                    raise HTTPException(422,'Evidence labels must reference current authorized chunks')
            scored={}
            for name,ranking in event['rankings'].items():
                meta=event['strategies'][name]
                scored[name]={**(metrics(ranking,case.relevant_chunk_ids) if meta['status']=='success' else
                    {'recall_at_12':None,'ndcg_at_6':None,'label':'strategy unavailable'}),**meta}
            cases.append({'case_id':case.case_id,'run_id':case.run_id,'query_hash':event['query_hash'],
                          'relevant_chunk_ids':sorted(set(case.relevant_chunk_ids)),'strategies':scored})
        summary={}
        for name in ('dense','hybrid','hybrid_rerank'):
            summary[name]={}
            for metric in ('recall_at_12','ndcg_at_6'):
                values=[case['strategies'][name][metric] for case in cases if case['strategies'][name][metric] is not None]
                summary[name][metric]=sum(values)/len(values) if values else None
                summary[name]['scored_cases']=len(values)
            summary[name]['fallback_cases']=sum(bool(case['strategies'][name].get('fallback_reason')) for case in cases)
        report={'dataset_version':body.dataset_version,'reviewed':body.reviewed,'case_count':len(cases),
                'corpus_version':corpus,'cases':cases,'summary':summary,'generation_evaluated':False,
                'label_status':'human-reviewed' if body.reviewed else 'provisional','rank_depth':12,'evidence_depth':6,
                'source_commit':body.source_commit,'source_dirty':body.source_dirty,
                'embedding_namespace':request.app.state.rag.embeddings.settings.namespace}
        key='eval_'+uuid4().hex
        dataset_hash=hashlib.sha256(json.dumps({'version':body.dataset_version,'cases':[
            {key:case[key] for key in ('case_id','query_hash','relevant_chunk_ids')} for case in cases]},sort_keys=True).encode()).hexdigest()
        await session.execute(text('''INSERT INTO evaluation_runs(evaluation_id,actor_id,classroom_id,dataset_hash,dataset_version,corpus_version,reviewed,report)
          VALUES (:id,:actor,:classroom,:hash,:version,:corpus,:reviewed,CAST(:report AS jsonb))'''),
          {'id':key,'actor':principal['user_id'],'classroom':body.classroom_id,'hash':dataset_hash,'version':body.dataset_version,
           'corpus':corpus,'reviewed':body.reviewed,'report':json.dumps(report)})
        return {'evaluation_id':key,'dataset_hash':dataset_hash,**report}


@router.get('/evaluations')
async def evaluations(request:Request,classroom_id:str,principal=Depends(get_current_user)):
    await faculty(request,principal,classroom_id)
    async with principal_session(request.app.state.accounts.factory,principal['user_id']) as session:
        rows=(await session.execute(text('SELECT * FROM evaluation_runs WHERE classroom_id=:id ORDER BY created_at DESC LIMIT 50'),{'id':classroom_id})).mappings().all()
        return {'evaluations':[dict(row) for row in rows]}
