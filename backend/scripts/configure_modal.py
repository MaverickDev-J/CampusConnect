"""Copy only runtime credentials into separate Modal secrets, without printing them.

Run with a Python environment containing modal and python-dotenv.
Existing campusconnect-secrets supplies the hosted Redis connection when the
local .env points at a development-only Redis instance.
"""
import argparse
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]


def runtime_secrets(values,frontend_origin):
    origin=urlsplit(frontend_origin)
    if origin.scheme!='https' or not origin.hostname or origin.path not in ('','/') or origin.query or origin.fragment:
        raise ValueError('An explicit HTTPS frontend origin is required')
    for key in ('DATABASE_URL','WORKER_DATABASE_URL','JWT_SECRET'):
        if not values.get(key):
            raise ValueError('Missing required local runtime setting: '+key)
    common={key:value for key,value in values.items() if value and
        (key.startswith('GEMINI_') or key in {'JWT_SECRET','JWT_ALGORITHM','JWT_EXPIRE_MINUTES','AI_ANSWER_CACHE'})}
    redis=values.get('REDIS_URL','')
    if redis and urlsplit(redis).hostname not in {'localhost','127.0.0.1','redis'}:
        common['REDIS_URL']=redis
    api={**common,'DATABASE_URL':values['DATABASE_URL'],'CORS_ORIGINS':frontend_origin.rstrip('/'),'DEMO_ENABLED':'false'}
    groq_key=values.get('GROQ_API_KEY') or values.get('groq_api_key') or values.get('grop_api_key')
    provider=values.get('AI_TEXT_PROVIDER') or ('groq' if groq_key else 'gemini')
    api['AI_TEXT_PROVIDER']=provider
    if groq_key:
        api['GROQ_API_KEY']=groq_key
        api['GROQ_BUDGET_PROJECT']=values.get('GROQ_BUDGET_PROJECT') or 'groq-default'
    worker={**common,'DATABASE_URL':values['WORKER_DATABASE_URL']}
    return api,worker


def main():
    import modal
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-origin',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        api,worker=runtime_secrets(dotenv_values(ROOT/'.env'),args.frontend_origin)
        if not args.apply:
            print('Validated runtime settings. Use --apply to create/update the two staging secrets.')
            return
        modal.Secret.objects.create('campusconnect-postgres-api',api,allow_existing=True)
        modal.Secret.objects.create('campusconnect-postgres-worker',worker,allow_existing=True)
        modal.Secret.from_name('campusconnect-postgres-api').update(api)
        modal.Secret.from_name('campusconnect-postgres-worker').update(worker)
    except Exception as exc:
        print('Modal configuration failed ('+type(exc).__name__+'). Credentials were not printed.')
        raise SystemExit(1) from None
    print('Separate API/worker staging secrets saved. Owner migration credentials were excluded.')


if __name__=='__main__':
    main()
