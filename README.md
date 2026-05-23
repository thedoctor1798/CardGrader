# CardGrader AI Local Edition — Backend

This repository contains the local-only backend skeleton for CardGrader AI Local Edition.

Quick start (Windows):

1. Create a Python 3.12 venv and activate it.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

2. Start the app:

```powershell
.\start_cardgrader.bat
```

The backend will run on http://localhost:8710 and expose a health endpoint at `/api/health`.

Frontend quick start:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8710"
npm run dev
```

The frontend will run on http://127.0.0.1:5173 and talks only to the local backend.

Notes:
- Database: `data/cardgrader.db`
- Media folders are created under `media/` (`originals`, `resized`, `crops`, `annotated`, `video_frames`, `reports`).
- No external AI or network calls are made by the MVP.

Manual media upload test:

1. Seed the Rowlet demo row:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8710/api/demo/seed-rowlet
```

2. Upload an image to the owned card ID returned by the seed response:

```powershell
curl.exe -X POST http://localhost:8710/api/owned-cards/1/media `
  -F "label=front" `
  -F "file=@C:\path\to\rowlet-front.jpg"
```

3. List media for that owned card:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8710/api/owned-cards/1/media
```

Manual OpenCV analysis test:

1. Seed Rowlet if needed:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8710/api/demo/seed-rowlet
```

2. Upload a front image if needed:

```powershell
curl.exe -X POST http://localhost:8710/api/owned-cards/1/media `
  -F "label=front" `
  -F "file=@C:\path\to\rowlet-front.jpg"
```

3. Run local OpenCV analysis:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8710/api/owned-cards/1/analyze/opencv
```

4. Get an analysis run:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8710/api/analysis-runs/1
```

5. List analysis runs for an owned card:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8710/api/owned-cards/1/analysis-runs
```
