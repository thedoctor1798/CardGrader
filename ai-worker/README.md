# CardGrader AI Worker

Lightweight Windows bridge for CardGrader remote Local AI mode.

Architecture:

```text
Linux CardGrader backend -> Tailscale -> Windows AI Worker -> localhost LM Studio
```

LM Studio can stay bound to `127.0.0.1` because only this worker talks to it locally. Do not expose this worker publicly through Cloudflare, NPM, a public reverse proxy, or the open internet.

## Setup

1. Install LM Studio on the Windows gamer PC.
2. Load a vision-capable local model.
3. Start the LM Studio local server, usually `http://127.0.0.1:1234/v1`.
4. Copy `.env.example` to `.env` and adjust values if needed.
5. Start the worker:

```powershell
.\start_worker.bat
```

Health check on Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Health check from the Linux server over Tailscale:

```bash
curl http://WINDOWS-TAILSCALE-IP:8765/health
```

## Security

- Run this only on trusted private networks or Tailscale.
- Prefer a Windows Firewall rule that allows port `8765` only from the Tailscale network/interface.
- Keep LM Studio on localhost when possible.
- If you set `AI_WORKER_SHARED_TOKEN`, the Linux backend must send `Authorization: Bearer <token>`.
- No cloud AI, external AI API, or AI API key is used.

## Troubleshooting

- `lm_studio_reachable=false`: start LM Studio server or check `LM_STUDIO_BASE_URL`.
- Worker unreachable from Linux: check Tailscale, Windows Firewall, and the worker host/port.
- Invalid JSON: use a stronger vision model, disable thinking, or lower image count.
- Image errors: increase `AI_WORKER_MAX_IMAGE_SIZE_MB` or send fewer/smaller crops.
