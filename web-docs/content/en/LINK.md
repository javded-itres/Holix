# Holix Link — Remote Folder Access

Holix Link lets a **server-side Holix agent** read and write files in a **folder on the user's PC** behind NAT — without installing full Holix on that machine.

| Component | Package | Where it runs |
|-----------|---------|---------------|
| **Holix Link client** | [Holix-Link](https://pypi.org/project/Holix-Link/) (`holix-link`) | User PC (Windows / Linux / macOS) |
| **Link Relay + agent tools** | `Holix` (`holix`, `holix gateway`) | Your VPS / server |

The client opens an **outbound WebSocket** (TLS/WSS). No inbound ports on the user's network.

---

## Quick start

### Server

```bash
holix link create --profile support --ttl 10m
# → LINK-7K3M-9Q2P

holix gateway start
```

Share the pairing code with the user (Telegram, email, support portal).

### Client PC

```bash
pipx install Holix-Link
holix-link pair LINK-7K3M-9Q2P --folder ~/Projects/acme --server https://your-gateway.example.com
holix-link install-service
holix-link status
```

### Operator (Telegram / chat on profile `support`)

Ask the agent to read a file — it uses `link_read_file` automatically when links exist:

> Read README.md in the linked folder

---

## Server commands (`holix link`)

| Command | Description |
|---------|-------------|
| `holix link create --profile NAME [--ttl 10m]` | One-time pairing code (admin or profile owner) |
| `holix link list [--profile NAME] [--all]` | Active and revoked links |
| `holix link revoke <link_id>` | Revoke connection |

```bash
holix -p support link create --ttl 15m
holix link list --profile support
holix link revoke link_abc123def456
```

Pairing codes expire (default **10 minutes**, max 1 hour). Data is stored in `~/.holix/gateway/links.db`.

---

## Profile configuration

In `~/.holix/profiles/<name>/config.yaml`:

```yaml
link:
  max_connections: 5
  permissions:
    read: true
    write: true
    mkdir: true
    delete: false
```

| Field | Default | Description |
|-------|---------|-------------|
| `max_connections` | `5` | Max simultaneous links per profile |
| `permissions.read` | `true` | Allow `link_read_file`, `link_list_dir`, `link_stat` |
| `permissions.write` | `true` | Allow `link_write_file` |
| `permissions.mkdir` | `true` | Allow `link_mkdir` |
| `permissions.delete` | `false` | Allow `link_delete` (files only) |

Pair codes can be created by **gateway admin** or **profile owner** (same Telegram bot on the server).

---

## Agent tools

Registered automatically when the profile has active links:

| Tool | Description |
|------|-------------|
| `link_list_dir` | List remote directory |
| `link_read_file` | Read remote file (max 10 MB) |
| `link_write_file` | Write remote file |
| `link_stat` | File or directory metadata |
| `link_mkdir` | Create remote directory |
| `link_delete` | Delete remote file |

If multiple links are connected to one profile, pass `link_id` in tool arguments.

**Requires:** gateway running (Link Relay is in-process) and client daemon online.

---

## Client commands (`holix-link`)

| Command | Description |
|---------|-------------|
| `holix-link wizard` | Interactive pairing |
| `holix-link pair CODE --folder PATH [--server URL]` | Pair with gateway |
| `holix-link daemon --foreground` | Run connection loop |
| `holix-link install-service` | Autostart (systemd / LaunchAgent / Task Scheduler) |
| `holix-link uninstall-service` | Remove autostart |
| `holix-link stop` | Stop background daemon |
| `holix-link status` | Link id, folder, permissions, daemon state |
| `holix-link disconnect` | Remove local credentials |

### Install (all platforms)

```bash
pipx install Holix-Link
# or
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix-Link/main/scripts/install-link.sh | bash
```

Windows: `scripts/install-link.ps1` from the [Holix-Link repo](https://github.com/javded-itres/Holix-Link).

### Data directory

| OS | Path |
|----|------|
| Linux / macOS | `~/.holix-link/` |
| Windows | `%LOCALAPPDATA%\HolixLink\` |

Override: `HOLIX_LINK_HOME`. Gateway URL: `HOLIX_LINK_SERVER` or `--server`.

### Client notifications (opt-in)

In `~/.holix-link/config.json`:

```json
{
  "notifications": {
    "enabled": true,
    "on_read": true,
    "on_write": true,
    "on_delete": true
  }
}
```

### Platform notes

| OS | Folder examples | Autostart |
|----|-----------------|-----------|
| **Linux** | `~/work`, `/home/user/data` | systemd user unit `holix-link.service` |
| **macOS** | `~/Documents/project` | LaunchAgent `ru.holix.link.plist` |
| **Windows** | `C:\Users\me\Projects`, `\\server\share` | Task Scheduler on logon |

UNC and network paths are supported; paths inside the jail use a portable relative form.

---

## HTTP / WebSocket API

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /v1/link/create` | API key | Create pairing code |
| `POST /v1/link/pair` | Public (rate limited) | Exchange code for `link_id` |
| `GET /v1/link/list` | API key | List links |
| `GET /v1/link/{id}` | API key | Link status |
| `POST /v1/link/revoke/{id}` | API key | Revoke link |
| `WS /v1/link/ws` | Device key (first message) | Persistent client session |

Details: [GATEWAY_API.md](GATEWAY_API.md#holix-link-api).

---

## Security

- TLS 1.3 (WSS) for all client traffic
- Server fingerprint shown at pairing; trust with confirmation or `HOLIX_LINK_TRUSTED_FP`
- Workspace jail on client — no path escape, symlink blocked
- Revoke from server or `holix-link disconnect` on client
- Self-hosted relay only (no managed cloud in current release)

See [SECURITY.md](SECURITY.md) and the [design doc](../design/REMOTE_FOLDER_AGENT.md).

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Pairing fails 404 | Code expired or typo; run `holix link create` again |
| Pairing fails 409 | `link.max_connections` reached — revoke old links |
| Agent: link offline | `holix-link status`, daemon running, outbound HTTPS allowed |
| Agent: no link tools | Profile has no active links in `holix link list` |
| `holix doctor` warnings | See link section in doctor output |

```bash
holix link list --profile support
holix gateway status
holix-link status    # on client PC
```

---

## Related

- [GATEWAY.md](GATEWAY.md) — start gateway
- [PROFILES.md](PROFILES.md) — profile isolation
- [Holix-Link on GitHub](https://github.com/javded-itres/Holix-Link)