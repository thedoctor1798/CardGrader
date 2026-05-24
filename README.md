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
- Add manual prices in the price panel.
- Run OpenCV analysis.
- Set manual centering with `Centering beallitasa` if you want centering ratios to override the automatic MVP estimate.
- If configured, run Local AI analysis.

The Rowlet demo seed remains available for testing, but it is no longer the main workflow.

The main UI now keeps the normal grading workflow visible: add a card, upload front/back images, run OpenCV, run Local AI, review the report, and save manual prices. Developer and troubleshooting actions such as dry-run, single-image debug, and demo seed are grouped under collapsed `Fejlesztői / Debug eszközök` sections.

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

OpenCV preprocessing currently keeps the reliable parts only: resized front/back images and image quality metrics. Automatic corner/edge crops and automatic normalized card extraction are disabled from the normal grading and Local AI flow because they were unreliable without manual verification. Local AI uses full front/back resized images by default.

## Manual Centering

The card detail page includes `Centering beallitasa`.

- Red guide lines mark the outer card edges.
- Blue guide lines mark the inner artwork/border boundaries.
- Drag the guide lines visually until they match the card.
- The editor calculates L/R and T/B ratios live, for example `54/46` and `58/42`.
- Saved manual centering measurements are stored locally and override the automatic OpenCV centering estimate in scoring/reporting.

Normalized or tightly cropped card images are best for accuracy, but the editor falls back to the resized front/back image when normalized images are unavailable.

Centering reference:

- Gem Mint 10: 55/45 or better
- Mint 9: 60/40 or better
- NM-MT 8.5: 65/35 or better
- NM-MT 8: 70/30 or better
- EX-MT 7.5: 75/25 or better
- Below 7: worse than 75/25

## Local AI Setup

Local AI is optional and disabled by default. Only localhost model servers are allowed. No API key is used.

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
$env:LOCAL_AI_ENABLED="true"
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

Allowed local base URLs:

- `http://127.0.0.1:1234/v1`
- `http://localhost:1234/v1`
- `http://127.0.0.1:11434`
- `http://localhost:11434`
- `http://127.0.0.1:8080/v1`
- `http://localhost:8080/v1`

Run OpenCV analysis first, then run Local AI analysis from the Card Detail page.

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
- Only localhost model servers are allowed. Remote API hosts, LAN IPs, public IPs, and domain names are rejected.

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

Do not commit local database or media files.

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
