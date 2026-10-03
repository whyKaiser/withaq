"""Generate local service credentials once. Never print or overwrite existing secrets."""
import json
import secrets
from pathlib import Path


def initialize(root):
    data = root / "data"
    data.mkdir(exist_ok=True)
    path = data / "local-credentials.json"
    if not path.exists() and (data / "postgres.env").exists():
        raise SystemExit("Existing PostgreSQL configuration found without credentials. Restore credentials; do not regenerate database passwords.")
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for role in ("operator", "viewer", "worker", "gateway", "validator", "postgres", "pep", "pep-signing"):
        values.setdefault(role, secrets.token_urlsafe(32))
    path.write_text(json.dumps(values), encoding="utf-8")
    path.chmod(0o600)
    (data / "local-access.txt").write_text(values["operator"], encoding="utf-8")
    (data / "local-access.txt").chmod(0o600)
    env = data / "postgres.env"
    if not env.exists():
        env.write_text("POSTGRES_DB=withaq\nPOSTGRES_USER=withaq\nPOSTGRES_PASSWORD=" + values["postgres"] + "\n", encoding="utf-8")
        env.chmod(0o600)
    return values


if __name__ == "__main__":
    initialize(Path(__file__).resolve().parent.parent)
    print("Local credentials ready in ignored data/; none printed")
