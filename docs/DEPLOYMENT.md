# Public judge demonstration

Configured service URL: https://withaq-demo.onrender.com/. Initial deployment is being qualified; current activation evidence is in HANDOFF.

Existing WITHAQ APIs, planner, lineage engine and disclosure gateway run in four service processes, with a separate validator. Each visitor has a separate SQLite workspace and HttpOnly/SameSite cookie (Secure over HTTPS). Operator/service credentials and local PostgreSQL data are never exposed.

`render.yaml` / `deploy/Dockerfile`: Render Free, main, **On Commit**, health `/health/ready`. Builds run Python tests and TypeScript/Vite; failed builds cannot replace the working deployment. Local/unmerged branch commits do not update the URL. No GitHub Actions workflow permission required.

## Boundaries

- Synthetic data, mock content/disclosure, SIMULATED_CONFIRMED application. No packet broker, Docker socket or real AI key. Actual packet evidence is separately published.
- Eight workspaces, 45-minute lifetime, 256 writes per workspace, 20 requests/second, 32 KiB bodies, six published incident scenarios.
- Redeployment/restart resets temporary data. Workspaces are independent databases; not team storage.
- HTTP-only worker/gateway use authenticated loopback job routes; users cannot claim jobs or access other session IDs. No payload/token/body logs.
- Single API instance; no horizontal scaling/multiple Uvicorn workers. Supervisor stops services if any child exits.

Free instances sleep after 15 idle minutes; first opening can take longer. [Render limits](https://render.com/docs/free), [automatic deploys](https://render.com/docs/deploys).

## Local reproduction

```powershell
docker build -f deploy/Dockerfile -t withaq-public-demo:local .
docker run --rm --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8010:10000 -e WITHAQ_PUBLIC_URL=http://127.0.0.1:8010 withaq-public-demo:local
```

Open http://127.0.0.1:8010 and choose Try WITHAQ. On Render, RENDER_EXTERNAL_URL provides the HTTPS origin; RENDER_GIT_COMMIT identifies source in UI/health.

Preparation: 84 tests passed on Windows with SQLite + PostgreSQL; 68 passed in the Linux image (SQLite); TypeScript/Vite build passed. Six new tests cover isolation, cross-session reads, origins, private roles, expiry/cleanup, limits and forwarded-header spoofing. Container browser checks confirmed login, summary publication and independently validated a+b planning through the separate worker. Live deployment qualification is recorded in HANDOFF.
