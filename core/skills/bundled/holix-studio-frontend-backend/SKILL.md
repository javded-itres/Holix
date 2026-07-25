---
name: holix-studio-frontend-backend
description: >
  Wire frontend API base to the real Holix Studio backend public origin when both
  apps run in Studio. Use when building or fixing SPA/API monorepos, Vite/Next/React
  + FastAPI/Express, or any FE that calls a BE on another Studio preview port.
  Invoke via /holix-studio-frontend-backend.
tags:
  - holix
  - studio
  - frontend
  - backend
  - preview
  - vite
  - api
  - cors
user-invocable: true
---

## When to use

You are in **Holix Studio** and the project has (or will have) **both**:

- a **frontend** (Vite, Next, CRA, static SPA, etc.) on one listen port
- a **backend** API (FastAPI, Express, Django, …) on another listen port

Apply this skill **before** telling the user the app is ready, and whenever the frontend still points at `localhost` after both services are up.

## Goal

The browser loads the frontend from Studio’s **public** preview URL (H2 subdomain or path proxy). From that browser context, `http://localhost:8000` is **the user’s machine**, not the Studio host. API calls must use the backend’s **real Studio public origin**.

## Mandatory workflow

1. Start backend and frontend under the **profile workspace** (`start_background_process` / project scripts). Keep the **project’s configured ports** (do not invent random ports).
2. Wait until both are healthy (listen + health check).
3. Resolve public origins via built-in MCP **`holix_studio`** (tools appear as `mcp_holix_studio_*`):
   - `open_preview_url(port=…)` for each service (user Browser + registers H2 when enabled)
   - `preview_origins` — map `port → origin` for the whole profile
   - `resolve_preview_origin_tool(port=BACKEND_PORT)` — single backend origin + siblings
4. Set the **frontend** API base to the **backend** `origin` from that response (not localhost).
5. If the backend enforces CORS, allow the **frontend** public origin (from `origins` / `open_preview_url` for the FE port).
6. Restart the frontend dev server if env files changed, re-check health, open both previews again if needed.
7. Tell the user to open **Studio → Browser** (or the returned `frame_url`) — never `localhost`.

## What to put in frontend config

Prefer the project’s existing env convention. Examples (use the real backend origin string from MCP):

| Stack | Typical keys |
| --- | --- |
| Vite | `VITE_API_URL`, `VITE_API_BASE`, `VITE_BACKEND_URL` |
| Next.js | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BACKEND_URL` |
| CRA | `REACT_APP_API_URL` |
| Code | `axios.defaults.baseURL`, `fetch` base, OpenAPI client `basePath` |

Rules:

- Value = **backend** public origin from MCP, e.g. `https://p8000-<id>.preview.example.com` or path-proxy `https://studio.example.com/studio/preview/8000`
- No trailing slash unless the project already expects one (match existing style).
- Do **not** use `http://127.0.0.1:PORT` or `http://localhost:PORT` for browser-facing API base.
- Server-side only code that runs **on the Studio host** (SSR, build scripts talking to loopback) may still use `http://127.0.0.1:PORT` for same-machine calls — never for client-bundled env.

## Backend CORS / cookies

- Allow origin = frontend public origin (from MCP for the FE port).
- If cookies/auth cross FE↔BE hosts (especially H2 subdomains), configure CORS credentials and cookie `SameSite` appropriately; prefer Studio ticket/bootstrap for preview auth rather than inventing hostnames.
- In **path** mode both services may share the Studio host under different `/studio/preview/{port}/` prefixes — still use those public bases, not raw loopback.

## Vite / Nuxt HMR WebSocket (not the API)

Console errors like:

```text
[vite] failed to connect to websocket
WebSocket connection to 'wss://p3000-….preview…/_nuxt/?token=…' failed
WebSocket connection to 'wss://localhost:5173/_nuxt/?token=…' failed
```

are **Hot Module Replacement**, not REST/GraphQL frontend↔backend wiring.

- The browser loads the app from the Studio **public** preview host.
- Vite then opens a **WebSocket** for live reload. That path often fails behind Studio H2 / reverse proxy.
- Fallback to `wss://localhost:5173` always fails for remote users (localhost is their laptop).
- **The SPA can still work** without HMR (no hot reload until you refresh). Do not treat this as a broken API unless `fetch`/XHR to the backend also fails.

### Port must match

If the preview host is `p3000-…` but Vite prints `localhost:5173` as the server, ports are inconsistent:

1. Run the dev server on **one** port (prefer the project’s Nuxt/Vite port).
2. Call `open_preview_url` with **that same** listen port.
3. Do not open preview for 3000 while only Vite listens on 5173 (or vice versa).

### Preferred fix (keep HMR when possible)

**Nuxt** (`nuxt.config.ts`):

```ts
export default defineNuxtConfig({
  devServer: { host: '127.0.0.1', port: 3000 },
  vite: {
    server: {
      allowedHosts: true,
      hmr: {
        protocol: 'wss',
        clientPort: 443, // public HTTPS edge; avoids empty :port in wss URL
      },
    },
  },
})
```

**Vite** (`vite.config.ts`):

```ts
export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: {
      protocol: 'wss',
      clientPort: 443,
    },
  },
})
```

Then `open_preview_url(port=5173)` (or 3000 for Nuxt) — same port the process listens on.

### Reliable Studio fallback (no hot reload)

If HMR still fails after the config above, **disable HMR** so the client does not spam errors or throw:

```ts
// when process.env.HOLIX_STUDIO is set, or always for Studio-targeted projects
vite: {
  server: {
    hmr: false,
    allowedHosts: true,
  },
},
```

Or start with a flag if the toolchain supports it. Hard-refresh the Browser panel after restart.

### Do not confuse with API base

| Concern | Fix |
| --- | --- |
| REST/API `fetch` to backend | Backend **public origin** via MCP (`VITE_API_URL` / …) |
| `[vite] failed to connect to websocket` | HMR config / same listen port / `hmr: false` |
| User open URL | `frame_url` / Studio Browser — never localhost |

## Do NOT

- Advertise `localhost` / bare host:port as the user-facing API or app URL.
- Invent H2 hostnames or endpoint ids — always call `open_preview_url` / `resolve_preview_origin_tool`.
- Leave a committed `.env` with `localhost` as the only API URL when the app is meant to run in Studio (use Studio-resolved origin or document both local vs Studio).
- Point the frontend at the **frontend** origin by mistake — API base must be the **backend** port’s origin.
- Open the app via **Desktop** (`desktop_start` / `desktop_exec` / firefox in noVNC). Web apps go to **Studio → Browser** via `open_preview_url`. Desktop is only for native GUI apps or when the user asks for Desktop.

## Checklist before “done”

- [ ] Backend healthy on its port
- [ ] Frontend healthy on its port
- [ ] `resolve_preview_origin_tool` (or `preview_origins`) used for backend
- [ ] Frontend env / client baseURL = backend public origin
- [ ] CORS allows frontend public origin if needed
- [ ] Frontend restarted after env change
- [ ] User told to open Studio Browser / `frame_url`, not localhost

## Related

- System prompt block: Holix Studio browser preview
- MCP: `list_preview_targets`, `preview_origins`, `resolve_preview_origin_tool`, `open_preview_url`
- Skill: holix-cron / holix-subagents are unrelated; this skill is only FE↔BE wiring in Studio
