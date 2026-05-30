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
FRONTEND_PORT=8711
BACKEND_PORT=8710
VITE_API_BASE_URL=http://<SERVER_IP_OR_HOSTNAME>:8710
CORS_ORIGINS=http://<SERVER_IP_OR_HOSTNAME>:8711,http://lajos-server:8711,http://localhost:8711,http://127.0.0.1:8711
LOCAL_AI_MODE=remote_worker
LOCAL_AI_WORKER_BASE_URL=http://<TAILSCALE_CLIENT_IP_OR_HOSTNAME>:<PORT>
LOCAL_AI_MODEL_NAME=<your-local-vision-model>
```

`CORS_ORIGINS` must include the exact frontend origin users open in the browser. For example, if users open `http://192.168.1.103:8711`, include `http://192.168.1.103:8711`; if you later use a domain, add that domain origin too.

Start the stack:

```bash
docker compose --env-file .env.server up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f cardgrader-backend
curl http://127.0.0.1:8710/api/health
curl http://127.0.0.1:8711/
```

Default published ports:

- Frontend nginx: `http://SERVER_IP:8711`
- Backend API: `http://SERVER_IP:8710`

Persistent server folders:

- `./data:/app/data`
- `./media:/app/media`
- `./catalog:/app/catalog`
- `./logs:/app/logs`

The frontend container serves the Vite production build with nginx and proxies `/api` and `/media` to the backend container. If `VITE_API_BASE_URL` is empty, browser requests use the same host that served the frontend. If `VITE_API_BASE_URL` points directly at the backend, for example `http://192.168.1.103:8710`, make sure `CORS_ORIGINS` includes the frontend URL, for example `http://192.168.1.103:8711`.

### Server CORS Troubleshooting

Symptom: the frontend loads, but dashboard or collection requests show `Failed to fetch`. The browser console shows CORS blocked requests, and backend logs show `OPTIONS` requests returning `400`.

Fix: set `CORS_ORIGINS` in `.env.server` to include the frontend URL users open in the browser, for example:

```text
CORS_ORIGINS=http://192.168.1.103:8711,http://lajos-server:8711
```

Then rebuild and restart:

```bash
docker compose --env-file .env.server down
docker compose --env-file .env.server up -d --build
```

Verify the deployed config, health, and preflight response:

```bash
docker compose --env-file .env.server config | grep -E "CORS_ORIGINS|VITE_API_BASE_URL|published"
curl http://localhost:8710/api/health
curl -i -X OPTIONS "http://192.168.1.103:8710/api/cards" \
  -H "Origin: http://192.168.1.103:8711" \
  -H "Access-Control-Request-Method: GET"
```

Expected: the response does not return `400` and includes `Access-Control-Allow-Origin: http://192.168.1.103:8711`.

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

### Image-Based Card Recognition

Phase 15.5 adds local image-based card recognition for uploaded media.

Workflow:

```text
Upload image -> Kártya felismerése -> Windows AI Worker -> LM Studio -> local catalog matching -> accept candidate
```

The worker endpoint used for recognition is separate from grading:

```text
POST /api/ai/recognize-card
```

The backend endpoint is:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8710/api/media/{media_id}/recognize-card
```

Acceptance endpoint:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8710/api/recognition-attempts/{attempt_id}/accept `
  -ContentType "application/json" `
  -Body '{"catalog_card_id":999,"owned_card_id":321,"create_owned_card":false}'
```

What recognition extracts:

- card name
- card number
- set text/code
- rarity
- language hint
- visible text snippets

The backend stores each attempt in `recognition_attempts`, scores local catalog cards into `recognition_candidates`, and returns the top matches. Matching is weighted toward exact/normalized card number, exact/fuzzy name, set code/name, rarity, and language.

Frontend flow:

- Upload a front image.
- Click `Kártya felismerése`.
- Review top candidates.
- Click `Ez az` to accept and link the current owned card to that catalog card.
- Use `Másikat választok` or `Kézi megadás` to fall back to the collection/manual flow.

Image-first flow from Collection:

1. Open the Collection page.
2. Click `Kép alapján hozzáadás`.
3. Upload a full, sharp front image of the card.
4. Click `Kártya felismerése`.
5. Review the extracted fields and top catalog candidates.
6. Click `Ez az` on the correct candidate.
7. CardGrader creates the owned card, links the uploaded media to it, and opens the owned-card detail page.
8. Use the Phase 15.6 pricing UI on the detail page to add a manual price or click `Ár frissítése`.

The image-first upload endpoint is:

```text
POST /api/media/upload
```

The frontend then calls:

```text
POST /api/media/{media_id}/recognize-card
POST /api/recognition-attempts/{attempt_id}/accept
```

Recognition troubleshooting:

- Nem látom a `Kártya felismerése` gombot: open Collection and click `Kép alapján hozzáadás`, or open an owned-card detail page with an uploaded front/back image.
- Nincs media rekord: upload the image first; recognition runs against a saved media record.
- No candidates found: use a full, sharp front card image, not a small crop, and check that the card exists in the local catalog.
- AI worker unreachable: check Tailscale, the worker process, Windows Firewall, and `LOCAL_AI_WORKER_BASE_URL`.
- LM Studio unreachable: start the LM Studio local server and verify the worker can reach it.
- For Qwen vision models and JSON-only tasks, disable thinking/reasoning in LM Studio. Otherwise the model may produce reasoning content instead of final JSON.
- Blurry image: upload a sharper front image where the name and collector number are visible.
- Wrong crop/image: use the full front image, not a close-up that hides text.
- Model cannot read small text: try a stronger vision model or a higher quality photo.
- Catalog missing card: create the card manually, then retry later when catalog data is richer.
- No candidates found: lower `CARD_RECOGNITION_MIN_SCORE` or improve extracted text/photo quality.
- Wrong set/card number extracted: accept a different candidate manually or use manual entry.
- Worker unreachable: check Tailscale, worker process, Windows Firewall, and `LOCAL_AI_WORKER_BASE_URL`.
- Shared token mismatch: set the same `AI_WORKER_SHARED_TOKEN` in `.env.server` and `ai-worker/.env`.

### Price History And Valuation

Phase 15.6 adds backend-owned pricing and collection valuation. Price provider logic lives in backend adapters; the frontend only calls CardGrader API endpoints and never contains scraping/source logic.

Server `.env.server` pricing defaults:

```text
PRICE_FETCH_ENABLED=true
PRICE_REFRESH_ENABLED=false
PRICE_REFRESH_INTERVAL_HOURS=24
PRICE_DEFAULT_CURRENCY=HUF
PRICE_RATE_LIMIT_SECONDS=3
PRICE_REQUEST_TIMEOUT_SECONDS=30
PRICE_SOURCES=manual,local_json,poketrace,tcgdex,pokemontcg
PRICE_FETCH_AFTER_RECOGNITION=false
PRICE_FX_EUR_HUF=
PRICE_FX_USD_HUF=
FX_CONVERSION_ENABLED=true
FX_DEFAULT_TARGET_CURRENCY=HUF
FX_PROVIDER=frankfurter
FX_PROVIDER_BASE_URL=https://api.frankfurter.dev/v2
FX_PROVIDER_FALLBACK_BASE_URL=https://api.frankfurter.dev/v1
FX_USER_AGENT=CardGrader/1.0
FX_CACHE_TTL_HOURS=12
FX_TIMEOUT_SECONDS=15
FX_FALLBACK_TO_STATIC_RATES=true
PRICE_PROVIDER_CACHE_TTL_HOURS=24
PRICE_EXTERNAL_FETCH_ENABLED=true
PRICE_PROVIDER_MIN_MATCH_SCORE=70

# UI settings saved in /app/data override env values.
CONFIG_ENCRYPTION_KEY=
ALLOW_UNENCRYPTED_PROVIDER_SECRETS=false

POKETRACE_ENABLED=false
POKETRACE_API_KEY=
POKETRACE_PLAN=free
POKETRACE_MARKET=US
TCGDEX_ENABLED=false
POKEMONTCG_ENABLED=false
POKEMONTCG_API_KEY=
```

#### Online Pricing Provider Strategy

Phase 15.6.2 adds an online provider chain behind backend adapters:

- `poketrace`: primary online provider. Uses `X-API-Key`, captures rate-limit headers, and maps raw plus PSA 7/8/9/10 prices when available.
- `tcgdex`: free raw-price fallback using TCGPlayer/Cardmarket fields where present. Do not expect PSA prices.
- `pokemontcg`: raw-price fallback using Pokémon TCG API TCGPlayer/Cardmarket fields. API key is optional but recommended for better limits.
- `manual` and `local_json`: still work without external accounts.

PokeTrace plan defaults:

- Free: 250 requests/day, 1 request / 2 seconds, eBay + TCGPlayer, raw-focused.
- Pro: 10k/day, 30 requests / 10 seconds, eBay + TCGPlayer + Cardmarket.
- Scale: 100k/day, 60 requests / 10 seconds, eBay + TCGPlayer + Cardmarket.

CardGrader does not scrape public HTML pages, Cardmarket pages, or TCGPlayer pages. External provider calls are rate-limited and cached by provider TTL.

#### Configuring Price Providers From The UI

Open `Beállítások` -> `Árforrások`.

1. Enable PokeTrace, paste the API key, select plan and market, then save.
2. Click `Test` to verify the backend can reach the provider.
3. Enable TCGdex or Pokémon TCG API as raw-price fallbacks if desired.
4. Open a card detail page, choose `Auto/provider chain` or a specific provider, then click `Ár frissítése`.

Provider settings saved from the UI are stored server-side in the SQLite database under `/app/data`, so the Docker `./data:/app/data` volume preserves them across restarts, rebuilds, and git pulls. Database/UI settings override `.env` values until changed or cleared.

Security notes:

- API keys are sent to the backend only during save/update.
- Full API keys are never returned to the frontend; the UI only receives masked values like `pt_****abcd`.
- API keys are never stored in frontend localStorage.
- Set `CONFIG_ENCRYPTION_KEY` to encrypt UI-stored provider secrets. Keep that key stable and backed up; changing it prevents existing encrypted secrets from being decrypted.
- If you intentionally allow trusted-LAN plaintext storage for this local MVP, set `ALLOW_UNENCRYPTED_PROVIDER_SECRETS=true`.
- Do not expose the Settings UI publicly without authentication/admin access.

#### Automatic HUF Conversion

Phase 15.6.3 converts non-HUF provider prices to HUF automatically. The default FX provider is Frankfurter, a free no-key API using central-bank style reference rates. Rates are cached in the backend database under `/app/data`, so the Docker `./data:/app/data` volume preserves them across restarts and rebuilds.

Default env:

```text
FX_CONVERSION_ENABLED=true
FX_DEFAULT_TARGET_CURRENCY=HUF
FX_PROVIDER=frankfurter
FX_PROVIDER_BASE_URL=https://api.frankfurter.dev/v2
FX_PROVIDER_FALLBACK_BASE_URL=https://api.frankfurter.dev/v1
FX_USER_AGENT=CardGrader/1.0
FX_CACHE_TTL_HOURS=12
FX_TIMEOUT_SECONDS=15
FX_FALLBACK_TO_STATIC_RATES=true
PRICE_FX_USD_HUF=
PRICE_FX_EUR_HUF=
```

Frankfurter calls use v2 first:

```text
https://api.frankfurter.dev/v2/rates?base=USD&quotes=HUF
```

If v2 fails, CardGrader tries v1:

```text
https://api.frankfurter.dev/v1/latest?base=USD&symbols=HUF
```

Requests send `User-Agent: CardGrader/1.0` and `Accept: application/json`.

When a provider stores a USD or EUR price, CardGrader fetches or reuses a cached FX rate and fills `converted_currency=HUF` plus the `converted_*` fields in `price_history`. Applied FX metadata is stored in `debug_metadata_json`, including provider, rate, rate date, fetched time, source (`frankfurter_v2`, `frankfurter_v1`, `cache`, `static`, or `identity`), and any warning.

If Frankfurter is unavailable and `PRICE_FX_USD_HUF` or `PRICE_FX_EUR_HUF` is configured, CardGrader uses that static fallback. If neither a provider rate nor a static rate is available, the original USD/EUR price remains stored, HUF converted fields stay null, and valuation warns instead of faking a conversion.

If Frankfurter returns HTTP 403, HTML, or a Cloudflare-style 1010 response, the backend reports `fx_provider_blocked` with the requested URL, HTTP status, content type, and a short response preview. The frontend shows a Hungarian troubleshooting message instead of only displaying `error code: 1010`:

```text
Frankfurter blokkolta az árfolyam lekérést vagy inkompatibilis endpointot használtunk. Ellenőrizd az FX endpointot és User-Agent beállítást.
```

If static fallback rates are configured, the UI reports:

```text
Frankfurter sikertelen, statikus árfolyam használva.
```

FX endpoints:

```bash
curl http://localhost:8710/api/fx/rates

curl -X POST http://localhost:8710/api/fx/refresh \
  -H "Content-Type: application/json" \
  -d '{"currencies":["USD","EUR"],"target_currency":"HUF","force":true}'
```

Frontend behavior:

- Card detail shows original USD/EUR and approximate converted HUF when conversion exists.
- If conversion is missing, card detail shows that the foreign-currency price exists but HUF conversion is missing.
- Dashboard valuation uses converted HUF values and shows missing FX warnings.
- Settings shows cached USD->HUF and EUR->HUF rates with a refresh button.

Manual prices work without external providers:

```bash
curl -X POST http://localhost:8710/api/prices/manual \
  -H "Content-Type: application/json" \
  -d '{"card_id":1,"owned_card_id":1,"raw_price":1200,"market_price":1200,"psa_7":2500,"psa_8":3500,"psa_9":7000,"psa_10":24000,"currency":"HUF","confidence":"manual","condition_hint":"raw near mint"}'
```

Fetch configured sources for one card:

```bash
curl -X POST http://localhost:8710/api/prices/fetch/1 \
  -H "Content-Type: application/json" \
  -d '{"owned_card_id":1,"sources":["manual","local_json"],"force":false}'
```

Read latest, history, and valuation:

```bash
docker compose --env-file .env.server config | grep -E "PRICE_|CORS_ORIGINS|VITE_API_BASE_URL|published"
docker compose --env-file .env.server config | grep -E "POKETRACE|TCGDEX|POKEMONTCG|PRICE_SOURCES|FX_"
curl http://localhost:8710/api/health
curl http://localhost:8710/api/fx/rates
curl http://localhost:8710/api/prices/providers/status
curl http://localhost:8710/api/prices/latest/1
curl http://localhost:8710/api/owned-cards/1/prices/market-latest
curl http://localhost:8710/api/prices/history/1
curl http://localhost:8710/api/collection/valuation
```

Refresh prices:

```bash
curl -X POST http://localhost:8710/api/prices/refresh-owned
curl -X POST http://localhost:8710/api/prices/refresh-all
```

`local_json` reads optional local files such as `data/prices/1.json`, `catalog/prices/1.json`, `data/prices/prices.json`, or `catalog/prices.json`. A per-card file can look like:

```json
{
  "source_card_id": "local-rowlet-090",
  "prices": {
    "raw_price": 1200,
    "market_price": 1200,
    "psa_7": 2500,
    "psa_8": 3500,
    "psa_9": 7000,
    "psa_10": 24000,
    "currency": "HUF"
  },
  "confidence": "medium",
  "condition_hint": "raw near mint"
}
```

Collection valuation prefers the latest online/card-level market row from `poketrace`, `tcgdex`, `pokemontcg`, or `local_json`. Manual owned-card prices remain visible as acquisition/manual context and are used only as a fallback when no market price exists. Raw owned cards use market/raw price. Graded owned cards try a matching PSA grade when the owned copy text includes a PSA grade, then fall back to the nearest lower grade or raw price. Missing prices are counted and do not break valuation. HUF prices are copied into converted HUF fields; USD/EUR and other supported currencies are converted through cached FX rates when available. Foreign-currency prices without HUF conversion are excluded from HUF valuation and counted as missing FX.

Frontend behavior:

- Card detail separates `Aktuális piaci ár` from `Saját / manuális ár`, so an older manual owned-card row does not hide a newer PokeTrace market price.
- Card detail can fetch configured sources with `Ár frissítése`.
- Card detail can add a manual price with `Manuális ár hozzáadása`.
- Card detail shows provider result details, match score, candidate alternatives when matching is uncertain, and a simple raw/market plus PSA 10 price history chart with source filters.
- Dashboard shows total valuation, missing price count, 24h/7d change when history exists, and latest price refresh time.

Pricing troubleshooting:

- No source configured: set `PRICE_SOURCES=manual,local_json,poketrace,tcgdex,pokemontcg` and enable/configure the providers you want.
- PokeTrace API key missing: open `Beállítások` -> `Árforrások`, or set `POKETRACE_API_KEY` in `.env.server`.
- PokeTrace rate limited: wait for `Retry-After`/daily reset; CardGrader captures PokeTrace rate-limit headers in `debug_metadata_json`.
- PokeTrace no reliable match: check local card name, set, and card number before storing an online price.
- Provider matched the wrong card: use the candidate debug list on the owned-card detail page and click `Ezt használd ehhez a kártyához`; this stores a backend `price_provider_card_mappings` row for future exact provider fetches.
- No price found: add a manual price or create a matching local JSON price file.
- Provider timeout: increase `PRICE_REQUEST_TIMEOUT_SECONDS` and keep external providers rate-limited.
- Unsupported currency: use `HUF`, `EUR`, or `USD`.
- Missing price history: call `POST /api/prices/manual` or `POST /api/prices/fetch/{card_id}`.
- No price after card recognition: recognition does not force price fetching by default. Open the owned card and click `Ár frissítése`, or set `PRICE_FETCH_AFTER_RECOGNITION=true` for conservative backend-triggered fetching.

External data sources must be used respectfully and rate-limited. Do not bypass anti-bot systems, do not commit secrets, and do not put scraping logic in the frontend.

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
- price_history
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

In `remote_worker` mode, the backend sends selected OpenCV images as base64 to the Windows worker at `/api/ai/grade`. The worker then calls localhost LM Studio and returns structured JSON. The backend validates the returned issue areas before saving findings.

By default Local AI sends only:

- `front_resized`
- `back_resized`, when available

Front-only analysis uses only `front_resized`. Back-only analysis uses only `back_resized`. Single-image debug and front/back-only passes are marked as `Részleges elemzés`, are not treated as final grading, and do not show final PSA probability output. Aggregate review combines saved JSON findings from the front/back passes and does not send images.

AI grading guardrails:

- Prompts do not include example defects such as `back_top_left_corner` whitening or an example `8.5` grade.
- The prompt includes `allowed_areas`, and every model finding must refer to one of those provided areas.
- If the model reports a defect for an unprovided area, such as a back corner when only `front_resized` was sent, the backend removes that issue and stores `model_reported_issue_for_unprovided_area`.
- If only one image or an incomplete image set is sent, the backend stores `limited_image_set` and caps confidence.
- If a repeated/template-like issue phrase appears, the backend stores `repeated_template_issue_warning`.
- Every AI request stores image payload metadata in `analysis_runs.image_payload_json`: owned/card ids, asset id, label, relative path, dimensions, MIME type, file size, SHA256, and a short hash. Base64 image content is never stored in this metadata.
- The remote AI worker verifies image hashes and returns `received_image_count`, `received_image_labels`, `received_image_hashes`, and `received_image_dimensions`.
- If a new run for another owned card uses the same image hash as a previous unrelated run, the backend stores `possible_stale_image_payload`.
- The frontend shows these warnings and a partial-analysis badge instead of presenting the run as full grading.

Remote worker grading prioritizes available assets in this order:

1. front full
2. back full
3. front corners
4. back corners
5. edge/surface crops

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

## Phase 16 Smart Preprocessing And Two-Phase AI Grading

Phase 16 adds optional OpenCV preprocessing and a two-phase AI grading pipeline. It is feature-flagged so the legacy upload, OpenCV, and Local AI flows remain available.

### Feature Flags

Set these in `backend/.env`, the project root `.env`, or your Docker environment:

```env
ENABLE_IMAGE_PREPROCESSING=true
ENABLE_CENTERING_DETECTION=true
ENABLE_MANUAL_CENTERING_CORRECTION=true
ENABLE_TWO_PHASE_AI_GRADING=true
SEND_DIAGNOSTIC_IMAGES_TO_AI=true

AI_MAX_CONTEXT_TOKENS=10000
AI_PHASE_A_MAX_OUTPUT_TOKENS=1500
AI_PHASE_B_MAX_OUTPUT_TOKENS=2500
```

If a provider cannot use the requested token values, CardGrader logs a warning and uses the safest lower configured value instead of failing grading only for that reason.

### Diagnostic Images

When preprocessing is enabled, uploaded front/back card images generate files under:

```text
media/processed/<owned_card_id>/<side>/
```

Each side can include:

- `original_normalized.jpg`: EXIF-corrected, resized original for AI/reference.
- `grayscale_clahe.jpg`: grayscale local contrast view for text, borders, and faint defects.
- `sobel_edges.jpg`: line/edge emphasis for scratches, whitening, and print lines.
- `emboss_surface.jpg`: embossed grayscale surface view for dents, impressions, and texture.
- `highpass_texture.jpg`: high-frequency detail view for fine scratches and irregularities.
- `canny_edges.jpg`: contour/debug edge map for boundary detection.
- `perspective_corrected.jpg`: card crop warped from final corners.
- `centering_debug.jpg`: overlay of final centering guides, ratios, confidence, and boundary source.
- `analysis.json`: structured preprocessing, boundary, centering, paths, timings, and warnings.

The original upload is never overwritten. If preprocessing fails, the error is logged, `analysis.json` stores a warning, and normal grading can continue with the original images.

### Boundary And Manual Correction

Automatic boundary detection uses OpenCV grayscale blur, Canny edges, external contours, rectangular approximation, trading-card aspect ratio checks, and confidence scoring. The frontend Phase 16 panel lets you open a corner editor for each processed side. Drag the four corner points to correct the detected boundary, then save. CardGrader stores both auto and manual corners and uses `final_corners` for perspective correction and centering.

If detection fails, the system marks the boundary as `fallback` and uses the full normalized image so the flow does not block. Manual correction can still be saved when enabled.

### Deterministic Centering

Centering is calculated from `perspective_corrected.jpg` first. OpenCV finds likely inner border guides from edge projections and stores left/right/top/bottom border widths, horizontal and vertical ratios, side percentages, confidence, and warnings. AI may comment on centering, but the OpenCV JSON is the primary source.

### Two-Phase AI Grading

The card detail page includes one `Start AI Grading` button. Internally:

1. Phase A receives original color images, normalized originals, deterministic centering JSON, final boundary data, and card metadata. It returns internal working notes only.
2. Phase B receives Phase A notes, deterministic centering JSON, original images, and diagnostic views when `SEND_DIAGNOSTIC_IMAGES_TO_AI=true`. It returns the final user-facing JSON grade estimate.

Phase B can be retried without rerunning Phase A. Developer details in the panel expose Phase A notes, model parameters, warnings, and raw stored JSON.

The Windows AI worker now also exposes:

```text
POST /api/ai/vision-json
```

Use the updated worker for Phase 16 remote-worker grading. The older `/api/ai/grade` endpoint remains for the legacy flow.

### Phase 16 Troubleshooting

- Bad contour detection: use the corner editor and save manual corners. Try a clearer full-card image with visible card edges.
- Blurry images: retake the photo; OpenCV centering and AI defect confidence both drop when edges are soft.
- Reflective holo cards: diagnostic images can exaggerate reflections. Confirm severe findings against the original color image.
- Processed images exaggerate defects: emboss, high-pass, and Sobel are discovery aids, not proof. Phase B is prompted to confirm important defects when possible.
- Token/context limits: lower `AI_PHASE_A_MAX_OUTPUT_TOKENS` or `AI_PHASE_B_MAX_OUTPUT_TOKENS`, or raise your local worker/server max token config if the model truncates JSON.
