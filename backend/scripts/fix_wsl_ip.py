import os
import subprocess
import re

def get_wsl_host_ip():
    try:
        # Get the default gateway IP from 'ip route'
        route_output = subprocess.check_output(["ip", "route"]).decode()
        match = re.search(r"default via ([\d\.]+)", route_output)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error detecting IP: {e}")
    return None

def update_env():
    host_ip = get_wsl_host_ip()
    if not host_ip:
        print("❌ Could not detect WSL Host IP. Are you in a WSL terminal?")
        return

    env_path = ".env"
    if not os.path.exists(env_path):
        print("❌ .env file not found in current directory.")
        return

    with open(env_path, "r") as f:
        content = f.read()

    # Replace localhost or host.docker.internal with the actual IP
    new_content = re.sub(r"(host\.docker\.internal|localhost)", host_ip, content)

    with open(env_path, "w") as f:
        f.write(new_content)

    print(f"✅ Successfully updated .env with Host IP: {host_ip}")
    print("🚀 You can now run the backend with: uv run uvicorn main:app --reload")

if __name__ == "__main__":
    update_env()
