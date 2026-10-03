"""Supervise API, independent validator, worker and gateway. Ctrl+C stops children.

No database/password/operator credential reaches worker, validator or gateway.
PostgreSQL is optional for local development, required for the distributed-state gate.
"""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from init_lab import initialize
from withaq.database import migrate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--packets", action="store_true", help="Enable the disposable isolated packet adapter")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    values = initialize(root)
    url = ("postgresql+psycopg://withaq:" + values["postgres"] + "@127.0.0.1:55432/withaq") if args.postgres else "sqlite:///data/engine.sqlite3"
    migrate(url)
    if args.packets:
        subprocess.run(["docker", "build", "-q", "-f", "lab/Dockerfile", "-t", "withaq-packet-lab:local", "."], check=True, cwd=root)
    # Allow only ordinary OS/runtime variables; inherited app/provider secrets are excluded.
    base = {key: value for key, value in os.environ.items() if key.upper() in (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PYTHONPATH")}
    components = [
        ([sys.executable, "-m", "uvicorn", "withaq.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
         {"WITHAQ_ADMIN_TOKEN": values["operator"], "WITHAQ_VIEWER_TOKEN": values["viewer"],
          "WITHAQ_WORKER_TOKEN": values["worker"], "WITHAQ_GATEWAY_TOKEN": values["gateway"], "WITHAQ_DATABASE_URL": url,
          **({"WITHAQ_PEP_SIGNING_KEY": values["pep-signing"]} if args.packets else {})}),
        ([sys.executable, "-m", "withaq.validator_service"], {"WITHAQ_VALIDATOR_TOKEN": values["validator"]}),
        ([sys.executable, "-m", "withaq.worker"], {"WITHAQ_WORKER_TOKEN": values["worker"], "WITHAQ_VALIDATOR_TOKEN": values["validator"],
          **({"WITHAQ_PEP_TOKEN": values["pep"]} if args.packets else {})}),
        ([sys.executable, "-m", "withaq.gateway"], {"WITHAQ_GATEWAY_TOKEN": values["gateway"]}),
    ]
    if args.packets:
        components.append(([sys.executable, "-m", "withaq.pep_service"], {"WITHAQ_PEP_TOKEN": values["pep"], "WITHAQ_PEP_SIGNING_KEY": values["pep-signing"]}))
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    try:
        for command, environment in components:
            children.append(subprocess.Popen(command, env={**base, **environment}, cwd=root))
        print("WITHAQ lab: http://127.0.0.1:8000 | " + str(len(children)) + " service processes | " + ("PostgreSQL" if args.postgres else "SQLite fallback"), flush=True)
        print("Operator token: data/local-access.txt; Ctrl+C stops all children", flush=True)
        while not stopping:
            failed = [process for process in children if process.poll() is not None]
            if failed:
                raise SystemExit("A service exited; stopping lab. Inspect service output.")
            time.sleep(0.5)
    finally:
        for process in children:
            if process.poll() is None:
                if os.name == "nt":
                    # Python venv redirectors can own child interpreters on Windows.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.terminate()
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
