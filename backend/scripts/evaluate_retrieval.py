"""Resumable retrieval benchmark against recorded, authorized comparison runs.

Set CAMPUS_API_TOKEN, then run from backend:
  uv run python -m scripts.evaluate_retrieval --dataset path/to/reviewed-cases.json
Reports are JSON/CSV; provisional labels and missing model results stay explicit.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import httpx


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--url',default='http://127.0.0.1:8001')
    parser.add_argument('--output',type=Path,default=Path('storage/evals/latest'))
    parser.add_argument('--pause-seconds',type=float,default=20)
    args=parser.parse_args()
    parsed=urlparse(args.url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
        parser.error('Use HTTPS except on loopback')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        parser.error('Use an API origin without credentials or a path')
    token=os.getenv('CAMPUS_API_TOKEN')
    if not token:
        parser.error('Set CAMPUS_API_TOKEN to a faculty API access token')
    dataset=json.loads(args.dataset.read_text(encoding='utf-8'))
    cases=dataset.get('cases',[])
    if not 1<=len(cases)<=60 or len({case['id'] for case in cases})!=len(cases):
        parser.error('Provide 1..60 cases with unique IDs')
    if not 0<=args.pause_seconds<=300:
        parser.error('Pause must be between 0 and 300 seconds')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    journal=args.output.with_suffix('.progress.json')
    dataset_hash=hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest()
    progress=json.loads(journal.read_text()) if journal.exists() else {'dataset_hash':dataset_hash,'runs':{}}
    if progress['dataset_hash']!=dataset_hash:
        parser.error('Output belongs to a different dataset; choose a new --output')
    async with httpx.AsyncClient(base_url=args.url.rstrip('/'),headers={'Authorization':'Bearer '+token},timeout=90) as client:
        for index,case in enumerate(cases):
            if case['id'] in progress['runs']:
                continue
            response=await client.post('/api/quality/compare',json={'classroom_id':dataset['classroom_id'],'query':case['query'],'origin':'benchmark'})
            if response.status_code!=200:
                raise SystemExit('Comparison failed with HTTP '+str(response.status_code)+'; completed runs remain resumable')
            progress['runs'][case['id']]=response.json()['run_id']
            journal.write_text(json.dumps(progress,indent=2),encoding='utf-8')
            print('Recorded '+case['id'])
            if index<len(cases)-1:
                await asyncio.sleep(args.pause_seconds)
        git=lambda *flags:subprocess.run(['git',*flags],capture_output=True,text=True,check=True).stdout.strip()
        body={'classroom_id':dataset['classroom_id'],'dataset_version':dataset['version'],'reviewed':dataset.get('reviewed',False),
              'source_commit':git('rev-parse','HEAD'),'source_dirty':bool(git('status','--porcelain','--untracked-files=no')),
              'cases':[{'case_id':case['id'],'run_id':progress['runs'][case['id']],
                        'relevant_chunk_ids':case.get('relevant_chunk_ids',[])} for case in cases]}
        response=await client.post('/api/quality/evaluations',json=body)
        if response.status_code!=201:
            raise SystemExit('Report rejected with HTTP '+str(response.status_code)+'; verify labels and corpus versions before rerunning')
        report=response.json()
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with args.output.with_suffix('.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['case_id','strategy','status','recall_at_12','ndcg_at_6','fallback_reason'])
        writer.writeheader()
        for case in report['cases']:
            for name,scores in case['strategies'].items():
                writer.writerow({'case_id':case['case_id'],'strategy':name,**{key:scores.get(key) for key in ('status','recall_at_12','ndcg_at_6','fallback_reason')}})
    print('Saved JSON/CSV report; labels: '+report['label_status'])


if __name__=='__main__':
    asyncio.run(main())
