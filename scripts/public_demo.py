"""Run four judge-demo processes with freshly generated service identities."""
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    port = int(os.environ.get("PORT", "8010"))
    validator_port = int(os.environ.get("WITHAQ_DEMO_VALIDATOR_PORT", "8012"))
    api_url = f"http://127.0.0.1:{port}"
    validator_url = f"http://127.0.0.1:{validator_port}"
    values = {name: secrets.token_urlsafe(32) for name in ("worker", "gateway", "validator")}
    base = {k: v for k, v in os.environ.items() if k.upper() in (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PYTHONPATH")}
    public = {k: v for k, v in os.environ.items() if k in (
        "RENDER_EXTERNAL_URL", "RENDER_GIT_COMMIT", "WITHAQ_PUBLIC_URL", "WITHAQ_SOURCE_COMMIT", "WITHAQ_DEMO_MAX_SESSIONS")}
    components = [
        ([sys.executable, "-m", "uvicorn", "withaq.public_demo:create_app", "--factory", "--host", "0.0.0.0", "--port", str(port), "--no-access-log", "--no-proxy-headers"],
         {**public, "WITHAQ_WORKER_TOKEN": values["worker"], "WITHAQ_GATEWAY_TOKEN": values["gateway"], "WITHAQ_VALIDATOR_URL": validator_url}),
        ([sys.executable, "-m", "uvicorn", "withaq.validator_service:create_app", "--factory", "--host", "127.0.0.1", "--port", str(validator_port), "--no-access-log", "--no-proxy-headers"],
         {"WITHAQ_VALIDATOR_TOKEN": values["validator"]}),
        ([sys.executable, "-m", "withaq.public_worker"],
         {"WITHAQ_API_URL": api_url, "WITHAQ_VALIDATOR_URL": validator_url, "WITHAQ_WORKER_TOKEN": values["worker"], "WITHAQ_VALIDATOR_TOKEN": values["validator"]}),
        ([sys.executable, "-m", "withaq.public_worker", "--gateway"],
         {"WITHAQ_API_URL": api_url, "WITHAQ_GATEWAY_TOKEN": values["gateway"]}),
    ]
    children, stopping = [], False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    with tempfile.TemporaryDirectory(prefix="withaq-judge-") as directory:
        components[0][1]["WITHAQ_DEMO_DIRECTORY"] = directory
        try:
            for command, extra in components:
                children.append(subprocess.Popen(command, cwd=root, env={**base, **extra}))
            print(f"WITHAQ disposable judge demo on port {port}; four processes; no packet adapter", flush=True)
            while not stopping:
                if any(p.poll() is not None for p in children):
                    raise SystemExit("A demo service exited; stopping all services")
                time.sleep(0.5)
        finally:
            for child in children:
                if child.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        child.terminate()
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    main()
