# CardGrader AI Local Edition

Local-only card collection, pricing, OpenCV preprocessing, and grading precheck MVP.

All data is local. No external AI API or cloud service is used.

## Local Workflow

### Start Backend

```powershell
.\start_cardgrader.bat
```

Backend URLs:

- Backend: http://127.0.0.1:8710
- Health: http://127.0.0.1:8710/api/health
- App info: http://127.0.0.1:8710/api/app/info

### Start Frontend

```powershell
.\start_frontend.bat
```

Frontend URL:

- http://127.0.0.1:5173

The Vite dev server is configured with `strictPort: true`, so it should fail clearly if port 5173 is already in use instead of silently switching ports.

You can also start both dev servers:

```powershell
.\start_all_dev.bat
```

### Manual Frontend Start

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8710"
npm run dev
```

## Health Check

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/health
```

Opening http://127.0.0.1:8710 returns local app metadata.

## Linux Server Docker Deployment

Docker deployment is additive and does not replace the Windows `.bat` development workflow.

Target layout:

- Linux server runs CardGrader backend, frontend, SQLite data, media, catalog files, logs, and future metrics.
- Windows gamer PC runs LM Studio and the local vision model.
- Server and Windows PC communicate only over Tailscale/private networking.
- Local AI is not expected to run inside the server container.

On the Linux server:

```bash
git clone <your-repo-url> CardGrader
cd CardGrader
cp .env.server.example .env.server
mkdir -p data media catalog logs
sudo chown -R "$(id -u):$(id -g)" data media catalog logs
```

Edit `.env.server`:

```text
LOCAL_AI_MODE=remote_worker
LOCAL_AI_WORKER_BASE_URL=http://<TAILSCALE_CLIENT_IP_OR_HOSTNAME>:<PORT>
LOCAL_AI_MODEL_NAME=<your-local-vision-model>
```

Start the stack:

```bash
docker compose --env-file .env.server up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f cardgrader-backend
curl http://127.0.0.1:8710/api/health
curl http://127.0.0.1:8080/
```

Default published ports:

- Frontend nginx: `http://SERVER_IP:8080`
- Backend API: `http://SERVER_IP:8710`

Persistent server folders:

- `./data:/app/data`
- `./media:/app/media`
- `./catalog:/app/catalog`
- `./logs:/app/logs`

The frontend container serves the Vite production build with nginx and proxies `/api` and `/media` to the backend container. In production, `VITE_API_BASE_URL` can stay empty so browser requests use the same host that served the frontend.

### Tailscale And Remote Local AI

The server and Windows gamer PC must be on the same Tailscale tailnet. Use the Windows PC Tailscale IP, for example `100.x.y.z`, or its MagicDNS hostname in `LOCAL_AI_WORKER_BASE_URL`.

LM Studio normally binds to localhost only. Direct remote access from the Linux server works only if LM Studio is explicitly configured to listen on a network/Tailscale interface and firewall rules allow it. The safer long-term path is a small CardGrader AI worker bridge on the Windows PC that exposes only controlled Local AI endpoints to the server over Tailscale.

Keep access private:

- Prefer Tailscale IP/MagicDNS, not public IPs.
- Keep UFW/firewall rules limited to trusted Tailscale traffic where possible.
- Do not add OpenAI, cloud AI, external AI APIs, cloud storage, or AI API keys.

If the remote worker is not reachable, `/api/local-ai/status` and the Settings page show a clear worker error. The backend should keep running.

### Windows AI Worker Bridge

Phase 15.4 adds a lightweight worker under `ai-worker/` for the Windows gamer PC.

Windows startup:

1. Start Tailscale on the Windows PC.
2. Start LM Studio.
3. Load a vision-capable local model.
4. Start the LM Studio local server at `http://127.0.0.1:1234/v1`.
5. Start the worker:

```powershell
cd ai-worker
copy .env.example .env
.\start_worker.bat
```

Check locally on Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Check from the Linux server over Tailscale:

```bash
curl http://WINDOWS-TAILSCALE-IP:8765/health
```

Configure `.env.server` on the Linux server:

```text
LOCAL_AI_MODE=remote_worker
LOCAL_AI_WORKER_BASE_URL=http://WINDOWS-TAILSCALE-IP:8765
LOCAL_AI_TIMEOUT_SECONDS=300
LOCAL_AI_MAX_IMAGES=8
LOCAL_AI_MAX_TOKENS=4096
LOCAL_AI_DISABLE_THINKING=true
AI_WORKER_SHARED_TOKEN=
```

Restart the backend container after changes:

```bash
docker compose --env-file .env.server up -d --build cardgrader-backend
```

Optional shared token:

- Set the same `AI_WORKER_SHARED_TOKEN` in `.env.server` and `ai-worker/.env`.
- The backend sends `Authorization: Bearer <token>`.
- If empty, requests are unauthenticated for the local/Tailscale MVP.

The worker endpoint used by the backend is:

```text
POST /api/ai/grade
```

Images are transferred as base64 JSON payloads. The backend does not send server file paths to the worker.

Common troubleshooting:

- Worker not reachable: check Tailscale, MagicDNS/IP, worker process, and Windows Firewall.
- Windows Firewall blocks port: allow TCP `8765` only on the Tailscale/private network where possible.
- LM Studio not reachable: start the LM Studio server and verify `LM_STUDIO_BASE_URL`.
- Wrong LM Studio port: update `ai-worker/.env`.
- Model does not support images: load a vision-capable model in LM Studio.
- Model returned invalid JSON: disable thinking, use a stronger vision model, reduce image count, or inspect the worker response preview.

## Seed Rowlet Demo

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/demo/seed-rowlet
```

The Rowlet seed endpoint is idempotent. Repeated calls reuse the existing demo card and owned-card records.

## Reset Local Data

Warning: this deletes local SQLite demo data. It does not delete uploaded original media files.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/demo/reset-local-data
```

Deleted tables:

- analysis_assets
- analysis_findings
- analysis_runs
- card_media
- price_observations
- collection_snapshots
- owned_cards
- cards

## Cleanup Generated Media

Warning: this deletes generated media only. It does not delete `media/originals`.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/demo/cleanup-generated-media
```

Cleaned folders:

- media/resized
- media/normalized
- media/crops
- media/annotated
- media/video_frames
- media/reports

## Snapshot Behavior

Dashboard summary cards show live local SQLite data. The value chart only changes when you create a collection snapshot.

Use the Dashboard button:

```text
Snapshot készítése
```

or call:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/collection/snapshot
```

## Media Upload Test

## Custom Card Workflow

Use the frontend collection page for normal local use:

1. Start backend and frontend.
2. Open `http://127.0.0.1:5173/#/collection`.
3. Click `Új kártya hozzáadása`.
4. Fill the card fields and owned copy fields.
5. Submit the form. The new owned card opens automatically.

To add another copy of an existing card:

1. Open the card detail page.
2. Use `Új példány hozzáadása` in the owned copy edit panel.
3. Edit the new copy metadata as needed.

After creating a card you can:

- Upload front/back images from the card detail page.
- Optionally prepare the photo in `Kép szerkesztés`.
- Add manual prices in the price panel.
- Run OpenCV analysis.
- Set manual centering with `Centering beállítása` if you want centering ratios to override the automatic MVP estimate.
- If configured, run Local AI analysis.

The Rowlet demo seed remains available for testing, but it is no longer the main workflow.

The main Card Detail actions are intentionally limited to the normal grading flow:

- `Kép feltöltése`
- `OpenCV elemzés`
- `Centering beállítása`
- `Local AI elemzés`
- `Ár mentése`
- `Adatok szerkesztése`
- `Új példány hozzáadása`

Developer and troubleshooting actions such as Local AI dry-run, single-image debug, raw report/debug assets, demo/test actions, reset, cleanup, and annotation regeneration are grouped under collapsed `Fejlesztői / Debug eszközök` sections by default.

Long-running local work such as OpenCV analysis, Local AI analysis, report refresh, centering save, media upload, and snapshot creation shows a centered blurred loading overlay. These states are local-only; there are no external API calls, cloud calls, or API keys.

Missing latest price is normal for cards where no manual price has been recorded yet. The UI shows `Még nincs ár` / `Még nincs ár rögzítve.` and the manual price form remains usable.

Normal grading preparation flow:

```text
Upload -> optional image editing -> optional manual crop -> Centering setup -> OpenCV analysis -> Local AI analysis -> Report
```

Image editing is non-destructive. Original uploads remain under `media/originals`; saved edits and manual crops are stored as new derived media records under `media/derived`.

## Media Upload Test

1. Seed Rowlet:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/demo/seed-rowlet
```

2. Upload an image to an owned card ID:

```powershell
curl.exe -X POST http://127.0.0.1:8710/api/owned-cards/1/media `
  -F "label=front" `
  -F "file=@C:\path\to\rowlet-front.jpg"
```

3. List media:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/owned-cards/1/media
```

## OpenCV Analysis Test

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/owned-cards/1/analyze/opencv
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/analysis-runs/1/score
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/analysis-runs/1/report
```

OpenCV preprocessing currently keeps the reliable parts only: resized front/back images and image quality metrics. Automatic corner/edge crops are preserved for debugging, but they are hidden under `Auto crop / debug / unreliable` and labeled `Auto crop - nem használt gradinghez`. They are not used in the normal grading or Local AI flow.

## Manual Centering

The card detail page includes `Centering beállítása`.

- Red guide lines mark the outer card edges.
- Blue guide lines mark the inner artwork/border boundaries.
- Drag the guide lines or their circular handles until they match the card.
- Mouse wheel zooms. Hold Space and drag, or use middle mouse drag, to pan.
- Front and back have separate persistent measurements.
- Save, close, reopen, and page refresh restore the latest saved guide positions for each side.
- Reset lines only changes the current editor draft until `Save measurement` is pressed.
- `Copy to front/back` copies current line percentages to the other side as an unsaved helper.
- The editor calculates L/R and T/B ratios live, for example `54/46` and `58/42`.
- Saved manual centering measurements are stored locally with raw pixel coordinates and normalized line percentages for future grading logic.
- Manual centering overrides the automatic OpenCV centering estimate in scoring/reporting.

Normalized or tightly cropped card images are best for accuracy, but the editor falls back to the resized front/back image when normalized images are unavailable.

Centering reference:

- Gem Mint 10: 55/45 or better
- Mint 9: 60/40 or better
- NM-MT 8.5: 65/35 or better
- NM-MT 8: 70/30 or better
- EX-MT 7.5: 75/25 or better
- Below 7: worse than 75/25

## Image Editing And Derived Media

Use `Kép szerkesztés` on Card Detail before analysis when the uploaded photo needs preparation.

Available local tools:

- brightness
- contrast
- saturation
- sharpness
- gamma
- exposure
- rotation
- manual crop rectangle with draggable corners/edges
- optional crop aspect-ratio lock
- crop presets: full card, close-up, square

Saving creates a new derived media record, for example `front_adjusted`, `front_crop_manual`, or `back_adjusted`. The original upload is preserved. OpenCV treats the newest `front*` and `back*` image records as the current analysis input, then still emits canonical `front_resized` and `back_resized` assets for Local AI.

## Local AI Setup

Local AI is optional and disabled by default. No API key is used, no cloud AI is called, and the model must stay self-hosted.

CardGrader now separates the app host from the Local AI host:

- `LOCAL_AI_MODE=disabled` disables Local AI.
- `LOCAL_AI_MODE=server_local` keeps the current dev workflow where the backend talks directly to LM Studio on the same machine.
- `LOCAL_AI_MODE=remote_worker` prepares the server-hosted architecture where the backend contacts a gamer PC Local AI worker over Tailscale.

The legacy `LOCAL_AI_ENABLED=true` still maps to `server_local` when `LOCAL_AI_MODE` is not set.

Detailed LM Studio workflow:

1. Install and start LM Studio.
2. Download/load a vision-capable local model.
3. Start the LM Studio local server.
4. Confirm the server URL is:

```text
http://127.0.0.1:1234/v1
```

5. Create/edit backend `.env` or set these environment variables before starting the backend:

```powershell
$env:LOCAL_AI_MODE="server_local"
$env:LOCAL_AI_PROVIDER="lmstudio"
$env:LOCAL_AI_BASE_URL="http://127.0.0.1:1234/v1"
$env:LOCAL_AI_MODEL_NAME="<your-local-vision-model>"
$env:LOCAL_AI_TIMEOUT_SECONDS="120"
$env:LOCAL_AI_MAX_IMAGES="1"
$env:LOCAL_AI_MAX_TOKENS="4096"
$env:LOCAL_AI_DISABLE_THINKING="true"
.\start_cardgrader.bat
```

6. Restart the backend after changing Local AI settings.
7. Open the Settings page.
8. Click `Local AI kapcsolat tesztelése`.
9. Run OpenCV analysis first.
10. Run Local AI analysis from the Card Detail page.

Allowed `server_local` base URLs:

- `http://127.0.0.1:1234/v1`
- `http://localhost:1234/v1`
- `http://127.0.0.1:11434`
- `http://localhost:11434`
- `http://127.0.0.1:8080/v1`
- `http://localhost:8080/v1`

Run OpenCV analysis first, then run Local AI analysis from the Card Detail page.

### Server-hosted app with gamer PC AI worker

Planned hosted layout:

- Server hosts the backend API, frontend, database, media storage, card catalog, price history, and metrics exporter.
- Gamer PC hosts LM Studio or another local vision LLM.
- A small Local AI worker/bridge runs on the gamer PC and exposes a private HTTP endpoint over Tailscale.
- The server calls only that Tailscale worker URL. It does not need a GPU and does not call external AI APIs.

Server `.env` example:

```text
LOCAL_AI_MODE=remote_worker
LOCAL_AI_WORKER_BASE_URL=http://WINDOWS-TAILSCALE-IP:8765
LOCAL_AI_MODEL_NAME=<your-local-vision-model>
LOCAL_AI_TIMEOUT_SECONDS=180
LOCAL_AI_MAX_IMAGES=1
LOCAL_AI_MAX_TOKENS=4096
LOCAL_AI_DISABLE_THINKING=true
```

Gamer PC responsibilities:

- Run LM Studio locally, usually on `http://127.0.0.1:1234/v1`.
- Run the CardGrader Local AI worker/bridge from `ai-worker/`.
- Advertise only the worker endpoint through Tailscale/private networking.

In `remote_worker` mode, the backend sends selected OpenCV images as base64 to the Windows worker at `/api/ai/grade`. The worker then calls localhost LM Studio and returns structured JSON.

By default Local AI sends only:

- `front_resized`
- `back_resized`, when available

Front-only analysis uses only `front_resized`. Back-only analysis uses only `back_resized`. Aggregate review combines saved JSON findings from the front/back passes and does not send images. Unreliable OpenCV corner/edge crops are excluded unless you explicitly use debug tooling.

Useful debug endpoints:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/local-ai/status
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/local-ai/config
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/local-ai/test-connection
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/owned-cards/1/analyze/local-ai-dry-run
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/owned-cards/1/analyze/local-ai-debug-single-image
```

Local AI debug files are saved under:

```text
media/reports/{analysis_run_id}/local_ai_raw_response.txt
media/reports/{analysis_run_id}/local_ai_parsed.json
```

Local AI troubleshooting:

- If Local AI is disabled, check `.env` or environment variables and restart the backend.
- If LM Studio is unreachable, check that the LM Studio local server is running.
- If the model is missing, copy the exact model id/name from LM Studio or `/models`.
- If JSON parsing fails, inspect `local_ai_raw_response.txt` under `media/reports`.
- In `server_local` mode, `LOCAL_AI_BASE_URL` must be localhost.
- In `remote_worker` mode, `LOCAL_AI_WORKER_BASE_URL` should be a private self-hosted worker URL, typically a Tailscale `100.x.y.z` address. Do not point it at cloud AI or public API services.

Recommended LM Studio Qwen settings:

- Enable Thinking: OFF
- Preserve Thinking: OFF
- Temperature: `0` or `0.1`
- Limit Response Length: OFF
- Structured Output: OFF for now
- Use `LOCAL_AI_DISABLE_THINKING=true` so CardGrader adds `/no_think` to the prompt.

Do not rely on LM Studio Structured Output yet; CardGrader keeps backend parsing robust locally.

## Switching LM Studio Models

1. Download/load the new model in LM Studio.
2. Verify the exact model id:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:1234/v1/models
```

3. Copy the exact `id`, for example `qwen/qwen3.6-27b`.
4. Edit `backend/.env`:

```text
LOCAL_AI_MODEL_NAME=qwen/qwen3.6-27b
LOCAL_AI_MAX_IMAGES=1
LOCAL_AI_MAX_TOKENS=4096
LOCAL_AI_DISABLE_THINKING=true
```

5. Restart the backend.
6. Test config and connection:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/local-ai/config
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/local-ai/test-connection
```

7. Run single-image debug before full Local AI analysis.

## Local Files

- Database: `data/cardgrader.db`
- Media folders: `media/originals`, `media/resized`, `media/normalized`, `media/crops`, `media/annotated`, `media/video_frames`, `media/reports`
- Catalog files: `catalog/`
- Logs: `logs/`
- Linux server env example: `.env.server.example`
- Windows local backend env example: `backend/.env.local.example`

Do not commit local database or media files.

Do not commit `.env`, `.env.*`, `backend/.env`, local SQLite databases, uploaded media, generated media, catalog imports, logs, or Local AI debug report files. Example env files are safe to commit.

## Troubleshooting

### Frontend shows "Failed to fetch"

Check that the backend is running:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8710/api/health
```

If this fails, start the backend:

```powershell
.\start_cardgrader.bat
```

### Vite says port 5173 is in use

Close the old frontend terminal, or stop local Node dev servers:

```powershell
taskkill /IM node.exe /F
```

Then start the frontend again:

```powershell
.\start_frontend.bat
```
