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

Notes:
- Database: `data/cardgrader.db`
- Media folders are created under `media/` (`originals`, `resized`, `crops`, `annotated`, `video_frames`, `reports`).
- No external AI or network calls are made by the MVP.
