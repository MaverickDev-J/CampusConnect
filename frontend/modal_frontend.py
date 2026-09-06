"""
modal_frontend.py — Serverless Next.js deployment for CampusConnect on Modal.
Scales to zero when idle ($0 cost).

Deploy:  modal deploy modal_frontend.py
Test:    modal serve modal_frontend.py
"""

from pathlib import Path
import modal

# Resolve the frontend directory relative to this file
frontend_dir = Path(__file__).parent

# Build the container image: Node 20 + Next.js standalone build
image = (
    modal.Image.from_registry("node:20-slim", add_python="3.11")
    .workdir("/app")
    # Copy frontend source into the image (copy=True because npm build needs them)
    .add_local_dir(frontend_dir, remote_path="/app", copy=True, ignore=[
        "node_modules",
        ".next",
        ".git",
        "__pycache__",
        "*.pyc",
        ".env.local",
        ".env.development",
    ])
    .run_commands(
        # Install all deps (including devDependencies for the build)
        "npm ci",
        # Build the Next.js app in standalone mode
        "npm run build",
        # Copy static assets into the standalone output
        "cp -r .next/static .next/standalone/.next/static || true",
        "test -d public && cp -r public .next/standalone/public || true",
        # Clean up to reduce image size
        "rm -rf node_modules .next/cache",
    )
)

app = modal.App("campusconnect-frontend", image=image)


@app.function(
    scaledown_window=60,   # Stay warm for 60s after last request
    timeout=300,
    memory=512,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=3000, startup_timeout=30)
def web():
    """Start the Next.js standalone server."""
    import subprocess
    import os

    env = {**os.environ, "PORT": "3000", "HOSTNAME": "0.0.0.0"}
    subprocess.Popen(["node", "/app/.next/standalone/server.js"], env=env)
