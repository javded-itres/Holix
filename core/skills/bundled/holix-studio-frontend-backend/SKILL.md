---
name: holix-studio-frontend-backend
description: >
  Run frontend (and FE+BE) apps in Holix Studio: always bind 0.0.0.0, always open
  Studio preview links in chat, always prefer docker-compose with an nginx reverse
  proxy that joins frontend and backend. Use when starting Vite/Next/Nuxt/React,
  SPA+API monorepos, or any web app the user should open in Studio Browser.
  Invoke via /holix-studio-frontend-backend.
tags:
  - holix
  - studio
  - frontend
  - backend
  - preview
  - docker
  - nginx
  - vite
  - compose
  - required
user-invocable: true
required: true
platform: true
---

## When to use (always in Studio)

Apply this skill **whenever** you start, fix, or demo a **web** frontend (or FE+API) in Holix Studio:

- User asks to run the app, open the UI, “подними фронт”, “запусти preview”, “открой в браузере”
- Project has Vite / Next / Nuxt / CRA / static SPA ± API
- You are about to say the app is ready

This skill is **platform / required**: do not ignore it for Studio web work.

## Non‑negotiable rules

1. **Listen on `0.0.0.0` (never only `127.0.0.1`)** for any process that Studio Preview must reach  
   (Vite/Nuxt `host: '0.0.0.0'`, uvicorn `--host 0.0.0.0`, nginx published port, etc.).
2. **Always form real preview links in chat** after the app listens:
   - Call MCP **`open_preview_url(port=…)`** (and for FE+BE, for **every** public port users need).
   - Paste into the chat reply: `frame_url` / public origin from the tool result (Markdown link).
   - Never tell the user to open `localhost` / bare `host:port` as the main URL.
3. **Prefer docker-compose + nginx** for “run the app” demos:
   - One **published** port on the host (nginx).
   - Frontend and backend only on the **compose network** (expose, not host-publish unless needed).
   - Nginx routes UI + API on the **same origin** (`/` → FE, `/api/` → BE) so the browser does not need a separate API host when possible.
4. **Do not use Desktop / noVNC** for web apps — only **Studio → Browser** via `open_preview_url`.
5. **Do not claim** “preview is ready” without a successful tool result that includes the public URL.

## Preferred architecture (FE + BE)

```text
Browser → Studio preview (public HTTPS) → host:PORT → nginx container
                                              ├─ /        → frontend:3000
                                              └─ /api/    → backend:8000
```

Single public port → **one** `open_preview_url` → **one** link in chat.

### docker-compose.yml (template — adapt ports/paths)

Write under the project (e.g. `docker-compose.yml` or `deploy/docker-compose.studio.yml`):

```yaml
services:
  frontend:
    build: ./frontend   # or image + command for node
    # CRITICAL: app inside container must listen 0.0.0.0
    environment:
      - HOST=0.0.0.0
      - PORT=3000
      # Prefer same-origin /api via nginx — no absolute localhost API
      - VITE_API_URL=/api
      - NEXT_PUBLIC_API_URL=/api
    expose:
      - "3000"
    # no ports: on host — only nginx publishes

  backend:
    build: ./backend
    environment:
      - HOST=0.0.0.0
      - PORT=8000
    expose:
      - "8000"

  nginx:
    image: nginx:alpine
    depends_on:
      - frontend
      - backend
    ports:
      # Published port = Studio preview port (pick free project port)
      - "8080:80"
    volumes:
      - ./deploy/nginx.studio.conf:/etc/nginx/conf.d/default.conf:ro
```

### nginx.studio.conf (template)

```nginx
server {
    listen 80;
    server_name _;
    client_max_body_size 50m;

    # Frontend (Vite/Next/Nuxt/static)
    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Backend API (adjust prefix to match the app)
    location /api/ {
        proxy_pass http://backend:8000/;   # trailing slash strips /api prefix if BE has no /api
        # use proxy_pass http://backend:8000;  # if BE routes already start with /api
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Optional OpenAPI / health
    location /docs {
        proxy_pass http://backend:8000/docs;
        proxy_set_header Host $host;
    }
    location /health {
        proxy_pass http://backend:8000/health;
        proxy_set_header Host $host;
    }
}
```

### Frontend API base when nginx fronts both

| Stack | Prefer |
| --- | --- |
| Vite | `VITE_API_URL=/api` (or empty + relative `/api/...`) |
| Next | `NEXT_PUBLIC_API_URL=/api` |
| CRA | `REACT_APP_API_URL=/api` |
| Axios/fetch | relative `/api/...` |

Only if the user **must** call a **separate** public BE port (no nginx): set API base from MCP backend **public origin** (not localhost) — see “Split ports” below.

## Mandatory agent workflow

### A. Default: compose + nginx (propose this first)

1. Inspect project (package.json, existing Dockerfile/compose, ports).
2. **Propose** (and implement if user agrees / task implies run):
   - `docker-compose` with **frontend**, **backend** (if any), **nginx**
   - nginx joins FE+BE as above
   - host bind **0.0.0.0** inside services; **one** published host port on nginx
3. Start stack from workspace:
   - Studio Docker tools / `docker compose up -d --build` in the project dir
   - Or background process if user forbids Docker — still **0.0.0.0** + preview
4. Wait until nginx port accepts HTTP (health / log / `check_background_process` / docker ps).
5. **`open_preview_url(port=NGINX_HOST_PORT)`** (e.g. 8080).
6. In the **same** assistant message after tools succeed, include Markdown links, e.g.:

   ```markdown
   **Приложение:** [открыть preview](<frame_url or public origin from tool>)
   Порт: 8080 · nginx → frontend + `/api` → backend
   ```

7. If FE-only (no BE), still use nginx (or the FE process on `0.0.0.0`) and still call `open_preview_url` + link in chat.

### B. Dev servers without Docker (fallback)

Only if Docker is unavailable or user forbids it:

1. Start processes with **host `0.0.0.0`**:
   - Vite: `server: { host: '0.0.0.0', port, strictPort: true, allowedHosts: true }`
   - Nuxt: `devServer: { host: '0.0.0.0', port }`
   - uvicorn: `--host 0.0.0.0 --port …`
2. Prefer a small **local nginx** (compose one-service nginx + upstream host network) still if possible.
3. `open_preview_url` for each user-facing port; put **all** links in chat.
4. If FE and BE are separate public ports (no shared nginx origin):
   - `open_preview_url` for FE **and** BE
   - Set FE env to **backend public origin** from `resolve_preview_origin_tool` / `preview_origins`
   - CORS on BE must allow **frontend public origin**

### C. Split ports (no nginx) — API base

Same as before, but secondary to nginx:

1. `resolve_preview_origin_tool(port=BACKEND)` or `preview_origins`
2. FE env = backend **origin** (H2 or path proxy) — never `http://localhost:PORT` for the browser
3. Restart FE after env change; re-open previews; link both URLs in chat

## Vite / Nuxt HMR (secondary)

HMR WebSocket may fail behind Studio preview. SPA can still work without hot reload.

- Keep listen port consistent with `open_preview_url`
- Prefer `allowedHosts: true`, host `0.0.0.0`
- If HMR spam: `hmr: false` or `clientPort: 443` for wss edge — see stack docs
- Do **not** confuse HMR errors with broken REST API

## Do NOT

- Start web servers only on `127.0.0.1` when Studio preview is required
- Advertise localhost as the user URL
- Invent H2 hostnames — only MCP `open_preview_url` / `preview_origins`
- Open web apps via Desktop/noVNC
- Install random host nginx/yadisk/rclone for “preview” when Studio Browser + compose is available
- Say “я открыл preview” without a tool result containing the URL
- Skip proposing **docker-compose + nginx** for FE+BE run tasks

## Checklist before “done”

- [ ] Services listen on **0.0.0.0** (or via nginx published port)
- [ ] **docker-compose + nginx** proposed (and used when possible) for FE+BE
- [ ] Nginx routes `/` → FE and `/api/` (or project prefix) → BE
- [ ] FE uses **same-origin `/api`** or backend **public** origin (not laptop localhost)
- [ ] `open_preview_url` called for the public port(s)
- [ ] Chat message includes clickable **preview link(s)** from tool output
- [ ] User told: Studio Browser / the link — not localhost

## Related tools (Studio)

- MCP `holix_studio`: `open_preview_url`, `list_preview_targets`, `preview_origins`, `resolve_preview_origin_tool`
- Docker panel / compose tools for workspace stacks
- `start_background_process` / terminal only as fallback when compose is impossible

## Telegram + Studio (same Holix profile)

Processes started from **Telegram** for a user profile must appear in **Studio** for that
same profile (Processes panel + Browser targets):

- Holix persists a shared index: `HOLIX_HOME/profiles/<profile>/data/background_processes.json`
- Always use `start_background_process` (not detached raw nohup outside Holix)
- Bind **0.0.0.0** and call `open_preview_url` so Studio Browser can attach
- Workspace cwd must stay under the profile workspace so Studio can list the app

## Slash

`/holix-studio-frontend-backend` — re-apply this workflow (ports, compose+nginx, preview links).
