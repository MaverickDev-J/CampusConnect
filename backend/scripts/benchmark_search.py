"""Measure actual scoped SQL retrieval on disposable, loopback PostgreSQL only.

Synthetic vectors measure execution cost, never semantic quality or LLM capacity.
Set TEST_DATABASE_URL explicitly. No hosted database or provider is contacted.
"""
import argparse
import asyncio
import json
import os
import platform
from pathlib import Path
import random
import secrets
import statistics
import sys
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from api.services.retrieval.postgres_search import PostgresSearch
from database.postgres import create_session_factory,principal_session

ROOT=Path(__file__).resolve().parents[1]


def distribution(values):
    ordered=sorted(values)
    return {'samples':len(values),'p50_ms':round(statistics.median(values),2),
            'p95_ms':round(ordered[max(0,__import__('math').ceil(.95*len(ordered))-1)],2),
            'max_ms':round(max(values),2)}


async def benchmark(url,chunk_count,samples,output):
    parsed=make_url(url)
    if parsed.host not in ('127.0.0.1','localhost') or parsed.database in ('postgres','template0','template1'):
        raise ValueError('Use an explicitly selected disposable loopback database')
    tag='perf_'+uuid4().hex[:12];role=tag;cid=tag+'_class';fid=tag+'_file'
    users=[tag+'_teacher']+[tag+'_student'+str(i) for i in range(5)]
    password=secrets.token_urlsafe(24);engine=None
    report={'kind':'synthetic-local-sql','chunks':chunk_count,'dimensions':1536,
        'operator_host':{'platform':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count()},
        'vectors':'deterministic pseudo-random; not model embeddings','provider_calls':0,
        'pool_size':3,'max_overflow':0,'results':[],
        'limitations':['Warm repeated query; local Docker, not hosted Modal capacity.',
                      'Latency includes pool waiting and transaction setup; excludes HTTP and providers.',
                      'Shared PostgreSQL index sizes include other local rows.']}
    try:
        with psycopg.connect(url) as conn:
            report['postgres_version']=conn.execute('SELECT version()').fetchone()[0]
            report['pgvector_version']=conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
            for statement in (ROOT/'migrations/runtime_grants.sql').read_text().split(';'):
                if statement.strip():conn.execute(statement.replace(':"runtime_role"',sql.Identifier(role).as_string(conn)))
            for i,uid in enumerate(users):
                conn.execute('INSERT INTO users(user_id,email,name,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                    (uid,uid+'@example.test','Synthetic benchmark','not-a-login','teacher' if i==0 else 'student'))
            conn.execute('INSERT INTO classrooms(classroom_id,name,join_code,created_by) VALUES (%s,%s,%s,%s)',(cid,'Synthetic benchmark',tag,users[0]))
            for uid in users[1:]:conn.execute('INSERT INTO classroom_members VALUES (%s,%s)',(cid,uid))
            conn.execute('INSERT INTO files(file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by,status,active_revision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)',
                (fid,cid,'synthetic.txt','/nonexistent/benchmark-only','txt',tag,users[0],'ready'))
            conn.execute('INSERT INTO file_revisions VALUES (%s,1,%s,%s,%s)',(fid,'gemini-embedding-2:1536:search-v1','synthetic','ready'))
            rng=random.Random(42);query_vector=None
            with conn.cursor().copy('COPY chunks(chunk_id,file_id,classroom_id,revision,chunk_index,title,text,content_hash,page_number,embedding) FROM STDIN') as copy:
                for i in range(chunk_count):
                    vector=[round(rng.uniform(-1,1),4) for _ in range(1536)]
                    if i==42:query_vector=vector
                    content=(f'Network topic {i%100}: packet routing, addressing and reliable data delivery. '
                             f'The experiment identifier is topic{i%100}. ')*12
                    copy.write_row((tag+'_'+str(i),fid,cid,1,i,'Networking '+str(i%100),content,str(i),i+1,json.dumps(vector)))
            conn.commit()
            conn.execute('ANALYZE chunks')
        engine,factory=create_session_factory(parsed.set(username=role,password=password).render_as_string(hide_password=False))
        for concurrency in (1,5):
            for strategy in ('lexical','dense','hybrid'):
                async def worker(uid):
                    times=[]
                    for _ in range(samples):
                        started=time.perf_counter()
                        async with principal_session(factory,uid) as session:
                            rows=await PostgresSearch(session).search('topic42 packet routing',query_vector,classroom_id=cid,strategy=strategy)
                        if len(rows)!=12:raise RuntimeError('Unexpected scoped search result count')
                        times.append((time.perf_counter()-started)*1000)
                    return times
                # Warm connections and pages, then measure independently.
                await worker(users[1])
                started=time.perf_counter()
                groups=await asyncio.gather(*(worker(uid) for uid in users[1:concurrency+1]))
                elapsed=time.perf_counter()-started
                values=[value for group in groups for value in group]
                report['results'].append({'strategy':strategy,'concurrent_principals':concurrency,
                    **distribution(values),'queries_per_second':round(len(values)/elapsed,2)})
        with psycopg.connect(url) as conn:
            report['indexes']=[{'name':n,'bytes':b} for n,b in conn.execute("SELECT indexrelname,pg_relation_size(indexrelid) FROM pg_stat_user_indexes WHERE relname='chunks'")]
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            conn.execute("SELECT set_config('app.user_id',%s,true)",(users[1],))
            scope="FROM chunks c JOIN files f ON f.file_id=c.file_id JOIN file_revisions r ON r.file_id=c.file_id AND r.revision=c.revision WHERE c.classroom_id=%s AND public.can_read_classroom(c.classroom_id) AND f.status='ready' AND f.active_revision=c.revision AND r.status='ready' AND r.embedding_namespace='gemini-embedding-2:1536:search-v1' AND c.embedding IS NOT NULL"
            report['plans']={
                'dense':conn.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT c.chunk_id,c.text '+scope+' ORDER BY c.embedding <=> %s::vector,c.chunk_id LIMIT 30',(cid,json.dumps(query_vector))).fetchone()[0],
                'lexical':conn.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT c.chunk_id,c.text "+scope+" AND c.lexical @@ websearch_to_tsquery('english','topic42 OR packet OR routing') ORDER BY ts_rank_cd(c.lexical,websearch_to_tsquery('english','topic42 OR packet OR routing')) DESC,c.chunk_id LIMIT 30",(cid,)).fetchone()[0]}
        report['status']='passed'
    finally:
        if engine:await engine.dispose()
        with psycopg.connect(url) as conn:
            conn.execute('DELETE FROM classrooms WHERE classroom_id=%s',(cid,))
            conn.execute('DELETE FROM storage_cleanup WHERE file_id=%s',(fid,))
            conn.execute('DELETE FROM users WHERE user_id=ANY(%s)',(users,))
            exists=conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
            if exists:
                conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
        report['fixtures_removed']=True
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','chunks','results','fixtures_removed')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chunks',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=12)
    parser.add_argument('--output',type=Path,default=ROOT/'storage/operations/search-performance.json')
    args=parser.parse_args()
    if not 100<=args.chunks<=50000 or not 3<=args.samples<=100:parser.error('Use 100..50000 chunks and 3..100 samples')
    if not os.getenv('TEST_DATABASE_URL'):parser.error('Set TEST_DATABASE_URL explicitly')
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(benchmark(os.environ['TEST_DATABASE_URL'],args.chunks,args.samples,args.output))
