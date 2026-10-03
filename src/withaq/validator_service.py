"""Independent loopback validator process. No database or provider credentials."""
import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Model, Plan, Snapshot
from .store import digest
from .validator import validate


class ValidationRequest(Model):
    snapshot: Snapshot
    candidate: Plan


def create_app():
    app = FastAPI(title="WITHAQ independent validator")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    token = os.environ.get("WITHAQ_VALIDATOR_TOKEN", "")

    @app.get("/health/live")
    def live():
        return {"status": "ok", "service": "validator", "ready": bool(token)}

    @app.post("/v1/validate")
    def check(body: ValidationRequest, authorization: str = Header(default="")):
        scheme, _, supplied = authorization.partition(" ")
        if not token or scheme != "Bearer" or not hmac.compare_digest(token, supplied):
            raise HTTPException(403, detail="VALIDATOR_ROLE_DENIED")
        return {"snapshot_hash": digest(body.snapshot.model_dump(mode="json")),
                "plan_hash": digest(body.candidate.model_dump(mode="json")),
                "verdict": validate(body.snapshot, body.candidate).model_dump(mode="json")}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8002, access_log=False)
