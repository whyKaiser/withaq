import hmac
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Model
from .scenarios import scenarios
from .store import DomainError, Store
from .database import migrate
from .engine import Engine
from .routes import routes
from sqlalchemy.exc import SQLAlchemyError


class CreateRun(Model):
    scenario: str = "separable"
    policy: Literal["mfsc", "quarantine", "single-block"] = "mfsc"


class Command(Model):
    expected_version: int = Field(ge=1)


class Inspect(Command):
    artifact: str
    destination: str = "mock://review"
    account: str = "demo"
    purpose: str = "competition-demo"
    extra_text: str = Field(default="", max_length=1000)


class Approval(Command):
    request_id: str
    payload_hash: str
    lose_response: bool = False


def create_app(database=None, token=None, viewer_token=None, engine_url=None):
    app = FastAPI(title="WITHAQ lab", version="0.2.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    store = Store(database or os.environ.get("WITHAQ_DB", "data/withaq.sqlite3"))
    engine_path = Path(database).with_name("engine.sqlite3") if database else Path("data/engine.sqlite3")
    url = engine_url or os.environ.get("WITHAQ_DATABASE_URL") or "sqlite:///" + str(engine_path).replace("\\", "/")
    if url.startswith("sqlite"):
        migrate(url)
    engine = Engine(url, os.environ.get("WITHAQ_POLICY_PATH"))
    app.state.engine = engine
    admin = token or os.environ.get("WITHAQ_ADMIN_TOKEN", "")
    viewer = viewer_token or os.environ.get("WITHAQ_VIEWER_TOKEN", "")

    def identity(authorization: str = Header(default="")):
        scheme, _, supplied = authorization.partition(" ")
        if scheme != "Bearer" or not supplied:
            raise HTTPException(401, detail="AUTHENTICATION_REQUIRED")
        if admin and hmac.compare_digest(supplied, admin):
            return "operator"
        if viewer and hmac.compare_digest(supplied, viewer):
            return "viewer"
        raise HTTPException(401, detail="INVALID_CREDENTIAL")

    def operator(role=Depends(identity)):
        if role != "operator":
            raise HTTPException(403, detail="ROLE_DENIED")

    def key(idempotency_key: str = Header(min_length=8, max_length=128)):
        return idempotency_key

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse(status_code=error.status, content={"detail": error.code})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return JSONResponse(status_code=503, content={"detail": "DATABASE_UNAVAILABLE"})

    @app.get("/health/live")
    def live():
        return {"status": "ok", "mode": "simulation"}

    @app.get("/health/ready")
    def ready():
        try:
            engine.policy.load()
            available = bool(admin) and store.ready() and engine.db.ready()
        except Exception:
            available = False
        return JSONResponse(status_code=200 if available else 503,
                            content={"status": "ready" if available else "not_ready", "mode": "simulation"})

    @app.get("/v1/scenarios", dependencies=[Depends(identity)])
    def get_scenarios():
        return [s.model_dump(mode="json") for s in scenarios().values()]

    @app.post("/v1/demo/runs", dependencies=[Depends(operator)])
    def create_run(body: CreateRun, command_key=Depends(key)):
        return store.create(body.scenario, body.policy, command_key)

    @app.get("/v1/demo/runs/{run_id}", dependencies=[Depends(identity)])
    def get_run(run_id: str):
        return store.read(run_id)

    @app.get("/v1/demo/runs/{run_id}/artifacts/{artifact_id}", dependencies=[Depends(identity)])
    def get_artifact(run_id: str, artifact_id: str):
        return store.read_artifact(run_id, artifact_id)

    @app.post("/v1/demo/runs/{run_id}/inspect", dependencies=[Depends(operator)])
    def inspect(run_id: str, body: Inspect, command_key=Depends(key)):
        return store.mutate(run_id, "inspect", body.expected_version, command_key, body.model_dump(exclude={"expected_version"}))

    @app.post("/v1/demo/runs/{run_id}/egress/{action}", dependencies=[Depends(operator)])
    def egress(run_id: str, action: Literal["approve", "dispatch"], body: Approval, command_key=Depends(key)):
        return store.mutate(run_id, action, body.expected_version, command_key, body.model_dump(exclude={"expected_version"}))

    @app.post("/v1/demo/runs/{run_id}/{action}", dependencies=[Depends(operator)])
    def command(run_id: str, action: Literal["apply", "revoke", "complete-late", "recover"], body: Command, command_key=Depends(key)):
        return store.mutate(run_id, action, body.expected_version, command_key)

    app.include_router(routes(engine, identity, operator, key))

    dist = Path(__file__).resolve().parent.parent.parent / "apps" / "console" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app
