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

## Local Files

- Database: `data/cardgrader.db`
- Media folders: `media/originals`, `media/resized`, `media/crops`, `media/annotated`, `media/video_frames`, `media/reports`

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
