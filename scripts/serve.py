"""Start the local synthetic-data demo. Credentials are generated locally, never committed."""
import json
import os
import secrets
from pathlib import Path

import uvicorn


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    data = root / "data"
    data.mkdir(exist_ok=True)
    credentials = data / "local-credentials.json"
    if not credentials.exists():
        credentials.write_text(json.dumps({"operator": secrets.token_urlsafe(32), "viewer": secrets.token_urlsafe(32)}), encoding="utf-8")
        credentials.chmod(0o600)
    tokens = json.loads(credentials.read_text(encoding="utf-8"))
    os.environ["WITHAQ_ADMIN_TOKEN"] = tokens["operator"]
    os.environ["WITHAQ_VIEWER_TOKEN"] = tokens["viewer"]
    access = data / "local-access.txt"
    access.write_text(tokens["operator"], encoding="utf-8")
    access.chmod(0o600)
    print("WITHAQ simulation: http://127.0.0.1:8000")
    print("Local operator token: data/local-access.txt (not printed or committed)")
    uvicorn.run("withaq.main:create_app", factory=True, host="127.0.0.1", port=8000, access_log=False)
