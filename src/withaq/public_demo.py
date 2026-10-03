"""Disposable, cookie-isolated judge workspaces using the existing lab APIs.

Public mode never exposes local lab data, operator credentials or Docker. Workers
use authenticated loopback routes. SQLite and simulated application are explicit.
One API process only: session ownership is process-local and deliberately bounded.
"""
import hmac
import json
import os
import secrets
import shutil
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .main import create_app as lab_app
from .scenarios import scenarios

COOKIE = "withaq_demo"
DIST = Path(__file__).resolve().parents[2] / "apps/console/dist"
LOOPBACK = {"127.0.0.1", "::1", "testclient"}


@dataclass
class Session:
    identity: str
    app: FastAPI
    token: str
    created: float
    mutations: int = 0
    active: int = 0
    rate_second: int = -1
    rate_count: int = 0


class Workspaces:
    def __init__(self, directory, ttl=2700, maximum=8, clock=time.monotonic):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl, self.maximum, self.clock = ttl, maximum, clock
        self.lock = threading.RLock()
        self.sessions = {}

    def purge(self, all_sessions=False):
        with self.lock:
            for identity, session in list(self.sessions.items()):
                if not session.active and (all_sessions or self.clock() - session.created >= self.ttl):
                    session.app.state.engine.db.engine.dispose()
                    target = (self.directory / identity).resolve()
                    # Only an owned UUID directory directly under this workspace.
                    assert target.parent == self.directory and target.name == identity
                    shutil.rmtree(target)
                    del self.sessions[identity]

    def create(self):
        with self.lock:
            self.purge()
            if len(self.sessions) >= self.maximum:
                raise HTTPException(503, detail="DEMO_CAPACITY_BUSY")
            identity, token = uuid4().hex, secrets.token_urlsafe(32)
            path = self.directory / identity
            path.mkdir()
            app = lab_app(database=path / "explorer.sqlite3", token=token,
                          viewer_token=secrets.token_urlsafe(32),
                          engine_url="sqlite:///" + str(path / "engine.sqlite3").replace("\\", "/"))
            session = Session(identity, app, token, self.clock())
            self.sessions[identity] = session
            return session

    def lookup(self, identity):
        with self.lock:
            session = self.sessions.get(identity)
            if not session or self.clock() - session.created >= self.ttl:
                raise HTTPException(401, detail="DEMO_SESSION_EXPIRED")
            return session


def create_app(directory=None, public_url=None, maximum=None, ttl=2700, clock=time.monotonic):
    if os.environ.get("WITHAQ_PEP_SIGNING_KEY") or os.environ.get("WITHAQ_DATABASE_URL"):
        raise RuntimeError("Public demo must not inherit packet or local database configuration")
    worker = os.environ.get("WITHAQ_WORKER_TOKEN", "")
    gateway = os.environ.get("WITHAQ_GATEWAY_TOKEN", "")
    if not worker or not gateway:
        raise RuntimeError("Private demo service credentials are required")
    origin = (public_url or os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WITHAQ_PUBLIC_URL") or "http://127.0.0.1:8010").rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.path or parsed.username:
        raise RuntimeError("Invalid public demo origin")
    if parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost", "testserver"):
        raise RuntimeError("Public demo requires HTTPS")
    manager = Workspaces(directory or os.environ.get("WITHAQ_DEMO_DIRECTORY", "data/public-demo"), ttl,
                         maximum if maximum is not None else int(os.environ.get("WITHAQ_DEMO_MAX_SESSIONS", "8")), clock)
    source = os.environ.get("RENDER_GIT_COMMIT", os.environ.get("WITHAQ_SOURCE_COMMIT", "development"))

    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.purge(all_sessions=True)

    app = FastAPI(title="WITHAQ judge demo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.workspaces = manager
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list({parsed.hostname, "127.0.0.1", "localhost", "testserver"}))

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        return response

    def same_origin(request):
        if request.headers.get("x-withaq-demo") != "1" or request.headers.get("origin", origin) != origin:
            raise HTTPException(403, detail="DEMO_ORIGIN_DENIED")

    @app.get("/health/live")
    def live():
        return {"status": "ok", "mode": "public-disposable-simulation", "source_commit": source}

    @app.get("/health/ready")
    async def ready():
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                result = await client.get(os.environ.get("WITHAQ_VALIDATOR_URL", "http://127.0.0.1:8002") + "/health/live")
            good = result.status_code == 200 and result.json().get("ready") is True and DIST.exists()
        except (httpx.HTTPError, ValueError):
            good = False
        return JSONResponse({"status": "ready" if good else "not_ready", "mode": "public-disposable-simulation", "source_commit": source}, status_code=200 if good else 503)

    @app.get("/demo/config")
    def config():
        return {"public_demo": True, "source_commit": source, "session_minutes": ttl // 60,
                "packet_lab_configured": False, "provider": "mock", "database": "per-visitor-sqlite"}

    @app.post("/demo/session")
    async def session(request: Request):
        same_origin(request)
        manager.purge()
        identity = request.cookies.get(COOKIE, "")
        try:
            current = manager.lookup(identity)
        except HTTPException:
            current = manager.create()
        response = JSONResponse({"ready": True, "expires_in_s": max(0, int(ttl - (clock() - current.created)))})
        response.set_cookie(COOKIE, current.identity, max_age=int(ttl), httponly=True,
                            secure=parsed.scheme == "https", samesite="strict", path="/")
        return response

    def private(request):
        auth = request.headers.get("authorization", "")
        # Never trust a spoofed X-Forwarded-For header to grant private access.
        if not request.client or request.client.host not in LOOPBACK:
            raise HTTPException(404)
        if hmac.compare_digest(auth, "Bearer " + worker):
            return "worker"
        if hmac.compare_digest(auth, "Bearer " + gateway):
            return "gateway"
        raise HTTPException(403, detail="SERVICE_ROLE_DENIED")

    @app.get("/internal/demo/sessions")
    def workspaces(request: Request):
        private(request)
        manager.purge()
        with manager.lock:
            return {"sessions": [s.identity for s in manager.sessions.values() if clock() - s.created < ttl]}

    async def forward(request, current, path, is_private=False):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 32768:
                raise HTTPException(413, detail="DEMO_BODY_TOO_LARGE")
        if not is_private:
            same_origin(request)
            with manager.lock:
                # Bound requests and writes for every disposable workspace.
                second = int(clock())
                count = current.rate_count + 1 if current.rate_second == second else 1
                current.rate_second, current.rate_count = second, count
                if count > 20:
                    raise HTTPException(429, detail="DEMO_RATE_LIMIT")
                if request.method != "GET":
                    if current.mutations >= 256:
                        raise HTTPException(429, detail="DEMO_WORKSPACE_LIMIT")
                    current.mutations += 1
            if request.method == "POST" and path == "/v1/snapshots":
                try:
                    spec = json.loads(data)["spec"]
                except (ValueError, KeyError, TypeError):
                    raise HTTPException(422, detail="DEMO_SNAPSHOT_INVALID")
                if spec not in [s.model_dump(mode="json") for s in scenarios().values()]:
                    raise HTTPException(422, detail="DEMO_SCENARIOS_ONLY")
            if path.endswith("/apply"):
                try:
                    if json.loads(data).get("adapter", "simulation") != "simulation":
                        raise HTTPException(403, detail="PUBLIC_PACKET_ADAPTER_UNAVAILABLE")
                except ValueError:
                    raise HTTPException(422, detail="DEMO_BODY_INVALID")
        forwarded = {"Authorization": request.headers.get("authorization", "") if is_private else "Bearer " + current.token}
        for name in ("Content-Type", "Idempotency-Key"):
            if name in request.headers:
                forwarded[name] = request.headers[name]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=current.app), base_url="http://127.0.0.1", trust_env=False) as client:
            result = await client.request(request.method, path, headers=forwarded, content=bytes(data))
        return Response(result.content, status_code=result.status_code, media_type=result.headers.get("content-type", "application/json"))

    async def relay(request, identity, path, is_private=False):
        with manager.lock:
            current = manager.lookup(identity)
            current.active += 1
        try:
            return await forward(request, current, path, is_private)
        finally:
            with manager.lock:
                current.active -= 1

    @app.post("/internal/demo/sessions/{identity}/{path:path}")
    async def service_proxy(identity: str, path: str, request: Request):
        private(request)
        if not path.startswith("internal/jobs/"):
            raise HTTPException(404)
        return await relay(request, identity, "/" + path, True)

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
    async def public_proxy(path: str, request: Request):
        return await relay(request, request.cookies.get(COOKIE, ""), "/v1/" + path)

    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(DIST / "index.html")

    return app
