"""Record uncached, repeated faculty RAG answers for rubric review.

Requires CAMPUS_API_TOKEN and the deployed benchmark controls. Raw answers stay
in the operator-selected private output. Passing keyword checks is not a grade.
"""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import datetime,timezone
from pathlib import Path
import time
from urllib.parse import urlparse

import httpx


async def evaluate(args,token):
    dataset=json.loads(args.dataset.read_text(encoding='utf-8'))
    selected=[case for case in dataset['cases'] if case['id'] in args.case_id]
    if len(selected)!=len(args.case_id):raise ValueError('Unknown or duplicate case ID')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    report=json.loads(args.output.read_text()) if args.output.exists() else {
        'dataset_sha256':fingerprint,'status':'partial','grading_status':'human review pending','answers':[],
        'run_label':args.run_label,'started_at':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),
        'source_dirty':bool(subprocess.run(['git','status','--porcelain','--untracked-files=no'],capture_output=True,text=True,check=True).stdout.strip())}
    if report['dataset_sha256']!=fingerprint:raise ValueError('Output belongs to another dataset')
    if report.get('run_label',args.run_label)!=args.run_label:
        raise ValueError('Output belongs to another configuration; choose a new output')
    completed={(row['case_id'],row['trial']) for row in report['answers'] if not row.get('errors')}
    async with httpx.AsyncClient(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=150) as client:
        for case in selected:
            for trial in range(1,args.trials+1):
                if (case['id'],trial) in completed:continue
                response=await client.post('/api/chat/sessions',json={'classroom_id':dataset['classroom_id'],
                    'title':'Private evaluation '+case['id']})
                if response.status_code!=201:raise RuntimeError('Session creation HTTP '+str(response.status_code))
                session=response.json()['session_id'];started=time.perf_counter();first=None
                row={'case_id':case['id'],'trial':trial,'category':case['category'],'split':case['split'],
                     'query':case['query'],'expected_answer':case['expected_answer'],'answer':'','sources':[],
                     'errors':[],'review':{'correctness':None,'citation_support':None,'refusal':None,'reviewer':None}}
                try:
                    async with client.stream('POST',f'/api/chat/sessions/{session}/message',json={
                        'query':case['query'],'origin':'benchmark','bypass_cache':True}) as stream:
                        if stream.status_code!=200:raise RuntimeError('Chat HTTP '+str(stream.status_code))
                        done=False
                        async for line in stream.aiter_lines():
                            if not line.startswith('data: '):continue
                            event=json.loads(line[6:]);kind=event.get('t');value=event.get('d')
                            if kind=='token':
                                if first is None:first=(time.perf_counter()-started)*1000
                                row['answer']+=value
                            elif kind=='sources':row['sources']=value
                            elif kind=='error':row['errors'].append(value)
                            elif kind=='done':done=True
                        if not done:row['errors'].append('Stream ended before completion')
                    row.update(duration_ms=round((time.perf_counter()-started)*1000,2),
                               first_token_ms=round(first,2) if first is not None else None)
                    report['answers'].append(row)
                    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    if row['errors']:raise RuntimeError('Answer unavailable; progress saved, wait for capacity before resuming')
                    print('Recorded '+case['id']+' trial '+str(trial),flush=True)
                finally:
                    deleted=await client.delete('/api/chat/sessions/'+session)
                    if deleted.status_code not in (200,404):raise RuntimeError('Temporary evaluation session cleanup failed')
                if case is not selected[-1] or trial!=args.trials:
                    await asyncio.sleep(args.pause_seconds)
    report['status']='recorded; rubric review pending'
    report['sample_count']=len(report['answers'])
    report['rubric']={
        'correctness':'0 incorrect, 1 partly correct, 2 fully answers the question; verify against source.',
        'citation_support':'0 unsupported, 1 partly supported, 2 all material claims supported by cited source pages.',
        'refusal':'For absent-answer cases: pass only if it identifies missing evidence without inventing requested specifics.'}
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--url',required=True)
    parser.add_argument('--case-id',action='append',required=True)
    parser.add_argument('--trials',type=int,default=2)
    parser.add_argument('--pause-seconds',type=float,default=65)
    parser.add_argument('--output',type=Path,default=Path('storage/evals/answers.json'))
    parser.add_argument('--run-label',default='answer-rubric-review')
    args=parser.parse_args();parsed=urlparse(args.url)
    if parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):parser.error('Use HTTPS except on loopback')
    if parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:parser.error('Provide an API origin without credentials')
    if not 1<=args.trials<=5 or not 0<=args.pause_seconds<=300 or len(args.case_id)>10:parser.error('Use 1..5 trials, up to 10 cases and a pause of 0..300s')
    token=os.getenv('CAMPUS_API_TOKEN')
    if not token:parser.error('Set CAMPUS_API_TOKEN to a faculty access token')
    asyncio.run(evaluate(args,token))
