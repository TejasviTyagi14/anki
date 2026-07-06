# Deploying the Reaction Mechanism Grader

The app is **one service**: the FastAPI backend (RDKit) serves the API *and* the
web UI at `/app/`. So "deploy" = ship one container and put HTTPS in front of it.
Desktop and mobile are covered by the same responsive web app, which is also an
installable **PWA**.

```
            HTTPS (managed by the host / a reverse proxy)
                              │
                    ┌─────────▼──────────┐
                    │  one container      │
                    │  uvicorn → FastAPI  │
                    │   • /grade, /problems, /structure/*   (API)
                    │   • /app/*  (static UI + PWA + JSME + React)
                    └─────────────────────┘
```

## 1. Build & run the container locally

```bash
cd chem-grader
docker build -t chemgrader .
docker run --rm -p 8000:8000 chemgrader
# open http://localhost:8000/app/
```

Image is ~600 MB (RDKit). Runtime needs **≥512 MB RAM (1 GB comfortable)**.

## 2. Pick a host (any of these work — one container + HTTPS)

**Fly.io** (simple, global, cheap):
```bash
fly launch --no-deploy      # generates fly.toml; set internal_port = 8000
fly deploy
# HTTPS + a *.fly.dev domain are automatic; add a custom domain with `fly certs add`
```

**Render** (`render.yaml`):
```yaml
services:
  - type: web
    name: chemgrader
    runtime: docker
    plan: starter          # >=512MB
    healthCheckPath: /
    envVars:
      - key: PORT
        value: 8000
```
Push to GitHub, "New → Blueprint", done. HTTPS + domain included.

**Google Cloud Run** (scales to zero, pay-per-request):
```bash
gcloud run deploy chemgrader --source . --region us-central1 \
  --allow-unauthenticated --memory 1Gi --port 8000
```

**Your own VPS** (Docker + Caddy for automatic HTTPS):
```bash
docker run -d --restart unless-stopped -p 127.0.0.1:8000:8000 --name chemgrader chemgrader
# Caddyfile:  grader.example.com { reverse_proxy 127.0.0.1:8000 }
caddy run     # obtains + renews TLS automatically
```

**HTTPS is required** for the PWA/service worker and for camera/clipboard on
mobile. Every managed option above provides it; on a VPS use Caddy/Traefik/nginx+certbot.

## 3. Desktop & mobile

- **Responsive web app** — works in any desktop/mobile browser as-is (touch is
  handled via pointer events; the drawing canvas is touch-friendly).
- **Installable PWA** — `manifest.webmanifest` + `service-worker.js` are wired in.
  On Chrome/Edge desktop an **Install** button appears in the address bar; on
  Android/iOS use **Add to Home Screen**. It then launches full-screen like an app
  and works offline for the UI shell (grading still needs the server).
  - iOS home-screen *icon* wants a PNG `apple-touch-icon` (180×180). Add
    `frontend/apple-touch-icon.png` and it'll be used automatically.
- **App-store apps (optional)** — wrap the same web UI:
  - Mobile: **Capacitor** (iOS/Android) pointing at your deployed URL.
  - Desktop: **Tauri** (tiny) or **Electron**.
  The RDKit backend still needs to be hosted (below), *unless* you port grading to
  **RDKit.js (WASM)** to run fully client-side — then the whole thing can be a
  static PWA with no server (bigger change; ask if you want this).

## 4. Production hardening checklist

- [ ] **Lock down CORS** — `api.py` currently allows all origins (dev). Set it to
      your domain(s) once deployed.
- [ ] **Add auth / rate limiting** — `/grade`, `/structure/*`, `/problems/*` are
      open and run RDKit (CPU). Put them behind an API key, session, or a rate
      limiter (e.g. `slowapi`) if the app is public.
- [ ] **Shared store for scale-out** — `GraphStore` is in-memory, so keep
      `--workers 1` (as in the Dockerfile) or move it to Redis/Postgres before
      running multiple workers/instances. (Practice mode is stateless, so it
      scales fine regardless.)
- [ ] **Pin dependencies** — pin `requirements.txt` (esp. `rdkit`) for
      reproducible builds.
- [ ] **Logging/health** — `/` is a fine health check; add structured logging.
- [ ] **Rebuild `builder.js`** if you edit `builder.jsx`
      (`esbuild frontend/builder.jsx --outfile=frontend/builder.js --target=es2018`).
