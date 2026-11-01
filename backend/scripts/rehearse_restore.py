"""Rehearse a Neon point-in-time recovery using disposable branches only.

No live branch, local connection file, or uploaded file is modified. Connection
strings remain in memory and never appear in the report or command output.
"""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT=Path(__file__).resolve().parents[1]


def snapshot_files():
    return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (ROOT/'.env',ROOT.parent/'.env.local',ROOT.parent/'.neon') if path.exists()}


def rehearse(project,profile,output):
    neon=shutil.which('neon') or shutil.which('neon.cmd')
    if not neon:raise RuntimeError('Neon CLI is unavailable')
    tag='recovery-'+uuid4().hex[:10]
    created=[];report={'started_at':datetime.now(timezone.utc).isoformat(),'project_id':project,'branches':[]}
    originals=snapshot_files()
    output.mkdir(parents=True,exist_ok=True)
    def cli(*args):
        report['last_operation']=' '.join(args[:2])
        result=subprocess.run([neon,*args,'--project-id',project,'--profile',profile,'--output','json',
            '--no-color','--context-file',str(output/'neon-context.json')],capture_output=True,text=True,encoding='utf-8',timeout=120)
        if result.returncode:
            # Never copy CLI output: connection commands can include credentials.
            report['command_exit_code']=result.returncode
            report['failed_operation']=' '.join(args[:2])
            report['command_error']=re.sub(r'postgres(?:ql)?://\S+', '[redacted connection]',result.stderr+'\n'+result.stdout)[-2000:]
            raise RuntimeError('Neon command failed: '+' '.join(args[:2]))
        try:return json.loads(result.stdout)
        except json.JSONDecodeError:return result.stdout.strip()
    def branch_object(value):
        if isinstance(value,list):return next(v for v in value if isinstance(v,dict) and str(v.get('id','')).startswith('br-'))
        return value.get('branch',value)
    def create(name,parent,lsn=None):
        expiry=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
        if lsn:
            # The CLI's --parent resolves branch IDs before parsing a point in
            # time. The API accepts explicit parent_id and parent_lsn together.
            value=branch_object(cli('api',f'/projects/{project}/branches','--method','POST','--data',json.dumps({
                'branch':{'name':name,'parent_id':parent,'parent_lsn':lsn,'expires_at':expiry},
                'endpoints':[{'type':'read_write','autoscaling_limit_min_cu':0.25,'autoscaling_limit_max_cu':0.25}]})))
        else:
            # Neon disallows children of expiring branches. The source therefore
            # relies on the guarded finally cleanup; only the restored leaf expires.
            value=branch_object(cli('branches','create','--name',name,'--parent',parent,'--no-secrets','--cu','0.25'))
        if value.get('default') or value.get('primary') or value['id']==main['id'] or not value['name'].startswith(tag):
            raise RuntimeError('Refusing an unexpected recovery branch target')
        created.append(value['id']);report['branches'].append({'id':value['id'],'name':value['name'],'parent_id':value.get('parent_id')})
        return value
    def connection(branch):
        value=cli('connection-string',branch['id'],'--role-name','neondb_owner','--database-name','neondb')
        if isinstance(value,dict):
            report['connection_response_keys']=sorted(value)
            value=value.get('connection_string') or value.get('connection_uri') or value.get('uri')
        if not isinstance(value,str) or not value.startswith('postgresql://'):raise RuntimeError('Unexpected connection response')
        live=dotenv_values(ROOT.parent/'.env.local').get('DATABASE_URL_UNPOOLED','')
        if live and conninfo_to_dict(value)['host']==conninfo_to_dict(live)['host']:
            raise RuntimeError('Refusing to use the live endpoint for a recovery probe')
        return value
    try:
        branches=cli('branches','list')
        main=next(branch for branch in branches if branch.get('default'))
        source=create(tag+'-source',main['id'])
        source_url=connection(source)
        started=time.monotonic()
        with psycopg.connect(source_url,connect_timeout=30) as conn:
            baseline=conn.execute('SELECT (SELECT count(*) FROM users),(SELECT count(*) FROM classrooms),(SELECT count(*) FROM chunks)').fetchone()
            conn.execute('CREATE SCHEMA recovery_verification')
            conn.execute('CREATE TABLE recovery_verification.marker(id integer PRIMARY KEY,value text NOT NULL)')
            conn.execute("INSERT INTO recovery_verification.marker VALUES(1,'recover-this-committed-value')")
            conn.commit()
            lsn=conn.execute('SELECT pg_current_wal_lsn()::text').fetchone()[0]
            conn.execute('DELETE FROM recovery_verification.marker')
            conn.commit()
            assert conn.execute('SELECT count(*) FROM recovery_verification.marker').fetchone()[0]==0
        restored=create(tag+'-restored',source['id'],lsn)
        if restored.get('parent_id')!=source['id']:raise RuntimeError('Restored branch has an unexpected parent')
        restored_url=connection(restored)
        with psycopg.connect(restored_url,connect_timeout=30) as conn:
            value=conn.execute('SELECT value FROM recovery_verification.marker WHERE id=1').fetchone()
            assert value and value[0]=='recover-this-committed-value'
            recovered=conn.execute('SELECT (SELECT count(*) FROM users),(SELECT count(*) FROM classrooms),(SELECT count(*) FROM chunks)').fetchone()
            assert recovered==baseline
        report.update({'pitr_verified':True,'elapsed_seconds':round(time.monotonic()-started,3),
            'baseline_counts':dict(zip(('users','classrooms','chunks'),baseline))})
        # Validate current migration against a realistic clone, never against main.
        prior=os.environ.get('DATABASE_URL');os.environ['DATABASE_URL']=restored_url
        try:
            config=Config(str(ROOT/'alembic.ini'));config.set_main_option('script_location',str(ROOT/'migrations'))
            command.upgrade(config,'head')
        finally:
            if prior is None:os.environ.pop('DATABASE_URL',None)
            else:os.environ['DATABASE_URL']=prior
        with psycopg.connect(restored_url,connect_timeout=30) as conn:
            report['migration_revision']=conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
            assert conn.execute('SELECT value FROM recovery_verification.marker WHERE id=1').fetchone()[0]=='recover-this-committed-value'
            report['migration_preserved_data']=conn.execute('SELECT (SELECT count(*) FROM users),(SELECT count(*) FROM classrooms),(SELECT count(*) FROM chunks)').fetchone()==baseline
        report['status']='passed'
    except Exception as exc:
        report['status']='failed'
        report['error_type']=type(exc).__name__
        raise
    finally:
        cleanup=[]
        for branch_id in reversed(created):
            try:
                cli('branches','delete',branch_id)
                cleanup.append({'branch_id':branch_id,'deleted':True})
            except Exception:cleanup.append({'branch_id':branch_id,'deleted':False})
        report['cleanup']=cleanup
        report['local_connections_unchanged']=snapshot_files()==originals
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (output/'restore-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='lucky-silence-57200933')
    parser.add_argument('--profile',default='campusconnect-joy')
    parser.add_argument('--output',type=Path,default=ROOT/'storage'/'operations')
    args=parser.parse_args()
    try:print(json.dumps(rehearse(args.project,args.profile,args.output),indent=2))
    except Exception as exc:
        print('Recovery rehearsal failed ('+type(exc).__name__+'). Inspect the sanitized report; credentials were not printed.')
        raise SystemExit(1) from None
