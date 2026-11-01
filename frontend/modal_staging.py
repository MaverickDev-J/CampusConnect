"""New frontend for the PostgreSQL staging API; build-time API URL is explicit."""
import os
from pathlib import Path
from urllib.parse import urlsplit
import modal

api_url=os.environ.get('CAMPUS_STAGING_API_URL','').rstrip('/')
parsed=urlsplit(api_url)
if parsed.scheme!='https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
    raise ValueError('Set CAMPUS_STAGING_API_URL to the deployed HTTPS API origin')

image=(modal.Image.from_registry('node:22-bookworm-slim',add_python='3.11')
    .workdir('/app')
    .env({'CAMPUS_STAGING_API_URL':api_url,
          'NEXT_PUBLIC_API_URL':api_url,'NEXT_PUBLIC_WS_URL':api_url.replace('https:','wss:',1),
          'NEXT_PUBLIC_FACULTY_WORKFLOWS':'true','NEXT_PUBLIC_QUALITY_DASHBOARD':'true',
          'NEXT_PUBLIC_DEMO_ENABLED':'false','NEXT_TELEMETRY_DISABLED':'1'})
    .add_local_dir(Path(__file__).parent,remote_path='/app',copy=True,
        ignore=['node_modules','.next','.git','__pycache__','*.pyc','.env*','*.log'])
    .run_commands('npm ci','npm run build',
        'cp -r .next/static .next/standalone/.next/static',
        'cp -r public .next/standalone/public'))
app=modal.App('campusconnect-postgres-frontend',image=image)


@app.function(max_containers=1,scaledown_window=30,timeout=300,memory=512)
@modal.concurrent(max_inputs=30)
@modal.web_server(port=3000,startup_timeout=60)
def web():
    import subprocess
    subprocess.Popen(['node','/app/.next/standalone/server.js'],
        env={**os.environ,'PORT':'3000','HOSTNAME':'0.0.0.0'})
