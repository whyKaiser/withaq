"""Run the exact engine safety suite on PostgreSQL using disposable test schemas."""
import json
import os
import subprocess
import sys
from pathlib import Path

from withaq.database import migrate

root = Path(__file__).resolve().parent.parent
values = json.loads((root / "data/local-credentials.json").read_text(encoding="utf-8"))
url = "postgresql+psycopg://withaq:" + values["postgres"] + "@127.0.0.1:55432/withaq"
migrate(url)
environment = {**os.environ, "WITHAQ_TEST_DATABASE_URL": url}
result = subprocess.run([sys.executable, "-m", "pytest"], cwd=root, env=environment)
raise SystemExit(result.returncode)
