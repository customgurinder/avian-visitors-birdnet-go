# Avian Visitors for BirdNET-Go

Run the [Avian Visitors](https://github.com/Twarner491/AvianVisitors) bird
collage and stats UI on top of an existing **[BirdNET-Go](https://github.com/tphakala/birdnet-go)**
instance — no BirdNET-Pi required.

Avian Visitors is normally an overlay on BirdNET-Pi: its frontend talks to a
small PHP API that reads BirdNET-Pi's `birds.db`. This project replaces that
PHP layer with a lightweight **adapter** that speaks the exact same contract
to the frontend, but sources its data from **BirdNET-Go's REST API** instead.
The AV frontend runs completely unmodified.

```
┌──────────────────────┐   /avian/api/*.php    ┌───────────────┐  /api/v2/*   ┌──────────────┐
│  AV frontend (nginx) │ ────────────────────▶ │   adapter      │ ───────────▶ │  BirdNET-Go  │
│  collage + stats     │ ◀──── same JSON ────── │  (translates)  │ ◀─────────── │  (your box)  │
└──────────────────────┘                        └───────────────┘              └──────────────┘
```

## What you get

- The **collage of recently heard birds** (the headline feature) and the full
  **stats views** (life list, first detections, daily/hourly trends, activity
  rhythm, calendar), driven by your BirdNET-Go detections.
- **Pluggable regional illustration packs** — bundle illustrations for your
  region and add more repos any time (see [Illustration packs](#illustration-packs)).
- **Per-detection audio and spectrograms**, proxied from BirdNET-Go.

Station administration (BirdNET-Pi's settings/tools panels) is intentionally
**not** included — this is a visualization-only deployment. Manage your station
through BirdNET-Go's own UI.

---

## Prerequisites

- A **standalone Docker** host (not Swarm) running Portainer.
- A **GitHub account** (the included CI builds and publishes the images).
- A running BirdNET-Go instance reachable over HTTP from the Docker host.

## Deploying on Portainer (pre-built images)

The three images are built and published to GHCR by GitHub Actions, then pulled
by your Portainer stack — nothing is built on the Docker host.

### 1. Publish the images

Push this repo to GitHub. The workflow
[`.github/workflows/build-images.yml`](.github/workflows/build-images.yml) runs
on push to `main` (or a `v*` tag, or manually via **Actions → Run workflow**)
and publishes three multi-arch (amd64 + arm64) images to GHCR:

```
ghcr.io/<owner>/avian-visitors-birdnet-go-adapter
ghcr.io/<owner>/avian-visitors-birdnet-go-installer
ghcr.io/<owner>/avian-visitors-birdnet-go-web
```

First run takes ~5–10 min (arm64 is emulated). `<owner>` is your GitHub
username/org, lowercased.

### 2. Make the packages pullable

A **private repo is fine** — but its GHCR packages default to private, so choose one:

- **Public packages** (simplest): GitHub → each of the 3 packages → *Package
  settings → Change visibility → Public*. The repo itself can stay private.
- **Keep them private**: in Portainer, **Registries → Add registry → Custom**,
  URL `ghcr.io`, username = your GitHub user, password = a PAT with
  `read:packages`. Portainer then pulls them with those creds.

### 3. Deploy the stack

In Portainer: **Stacks → Add stack → Web editor**, paste
[`docker-compose.yml`](docker-compose.yml), and set environment variables:

| Name | Example | Notes |
|------|---------|-------|
| `AV_IMAGE_BASE` | `ghcr.io/<owner>/avian-visitors-birdnet-go` | Your GHCR path (lowercase owner). |
| `AV_IMAGE_TAG` | `latest` | Or a specific tag. |
| `AV_BIRDNETGO_URL` | `http://192.168.1.50:8080` | **Required.** Reachable from the Docker host. |
| `AV_DATA_DIR` | `/volume1/docker/avian-visitors` | **Absolute host path** for all data — otherwise it lands in Portainer's internal stack folder. See [Storage](#storage). |
| `AV_WEB_PORT` | `8090` | Host port for the UI. |
| `TZ` | `Europe/London` | Correct day boundaries. |
| `AV_PACKS` | `https://github.com/lloydalexporter/AvianAssets_GB-ENG.git` | Illustration pack(s). |
| `AV_INCLUDE_BASE_PACK` | `false` | Also add AV's base pack. |
| `AV_BIRDNETGO_API_TOKEN` | *(blank)* | Only if your API needs auth. |

**Deploy**, then open `http://<docker-host>:<AV_WEB_PORT>`. The one-shot `installer`
runs first (fetches the AV frontend, downloads your packs, builds the collage
tables into `AV_DATA_DIR` — a few minutes for ~1,400 GB-ENG files), then `adapter`
and `web` start. Redeploys are fast (the installer skips the heavy work once the
data dir is populated).

### Portainer notes

- The **`installer` shows `Exited (0)`** — normal; it's a one-shot that populates
  the data dir and quits. `adapter` + `web` keep running.
- **BirdNET-Go reachability:** `localhost` won't work from inside a container.
  Use the host's LAN IP, or attach the stack to BirdNET-Go's Docker network and
  use `http://birdnet-go:8080` (see [Networking](#networking)).
- **Updating:** push to GitHub → CI rebuilds → in Portainer use **Pull and
  redeploy** on the stack.
- **Adding/refreshing packs:** change `AV_PACKS`, set **`AV_FORCE_PACKS=true`** for one
  redeploy, then remove it. Once the data dir is populated the installer skips
  the pack download + mask rebuild, so this flag is what forces a refresh
  (`AV_FORCE_FRONTEND=true` likewise refreshes the AV frontend).

> Building locally instead of via CI isn't part of this setup, but the
> Dockerfiles are still here — `docker build ./adapter` (and `./installer`,
> `./web`) works if you ever need it.

---

## Configuration

Every variable this app reads is **prefixed `AV_`** so it never clashes with
BirdNET-Go's own variables when both run in the same stack or share one `.env`.
Inside the containers the app still uses unprefixed names — you only ever set
the `AV_` ones. The single exception is **`TZ`**, which is intentionally shared
(both apps want the same timezone).

All configuration is via environment variables in `.env`. Full list in
[.env.example](.env.example); the essentials:

| Variable | Default | Purpose |
|----------|---------|---------|
| `AV_BIRDNETGO_URL` | — | Full base URL of BirdNET-Go incl. port, e.g. `http://192.168.1.50:8080`. **Required** (or use the HOST/PORT trio below). |
| `AV_BIRDNETGO_HOST` / `AV_BIRDNETGO_PORT` / `AV_BIRDNETGO_SCHEME` | — / `8080` / `http` | Used only when `AV_BIRDNETGO_URL` is empty. |
| `AV_BIRDNETGO_API_TOKEN` | — | Bearer token, if your BirdNET-Go API requires auth. |
| `AV_DATA_DIR` | `./data` | Host directory holding all data (bind-mounted). Set an absolute path (e.g. on your NAS) to persist + back it up. See [Storage](#storage). |
| `AV_WEB_PORT` | `8090` | Host port for the collage UI. |
| `TZ` | `UTC` | IANA timezone for correct "today"/day boundaries, e.g. `Europe/London`. |
| `AV_PACKS` | — | Space-separated git repos of illustration packs. |
| `AV_INCLUDE_BASE_PACK` | `false` | Also install AV's bundled ~333-species (mostly N. American) pack. |
| `AV_LOG_LEVEL` | `INFO` | Set `DEBUG` to log every upstream call, cache hit, and timing. |
| `AV_HTTP_TIMEOUT` | `10` | Upstream request timeout (seconds). |
| `AV_CACHE_TTL` | `30` | Seconds to cache upstream responses. |
| `AV_MAX_DETECTIONS` | `5000` | Cap on rows pulled for windowed/stats views. Raise for busy stations. |
| `AV_CALENDAR_MAX_DAYS` | `365` | How far back the stats calendar scans. |

---

## Networking

The adapter (in Docker) must be able to reach `AV_BIRDNETGO_URL`. Three common cases:

1. **BirdNET-Go on another machine** — use its LAN address:
   `AV_BIRDNETGO_URL=http://192.168.1.50:8080`. Nothing else needed.

2. **BirdNET-Go in Docker on the same host, port published** — use the host's
   LAN IP (not `localhost`, which is the adapter container itself):
   `AV_BIRDNETGO_URL=http://192.168.1.50:8080`.

3. **Attach to BirdNET-Go's Docker network** — reference it by service name.
   Add to `docker-compose.yml`:

   ```yaml
   services:
     adapter:
       networks: [default, birdnet]
   networks:
     birdnet:
       external: true
       name: <birdnet-go's docker network>
   ```
   then `AV_BIRDNETGO_URL=http://birdnet-go:8080`.

Because the adapter **proxies** audio/spectrogram bytes (rather than
redirecting the browser), your browser only ever needs to reach this stack —
never BirdNET-Go directly. So option 3 works even with BirdNET-Go fully
firewalled off from clients.

### Running in the same stack as BirdNET-Go

You can drop these services into BirdNET-Go's own `docker-compose.yml`. Because
every variable here is `AV_`-prefixed, there's no collision with BirdNET-Go's
env — the two sets sit side by side and it's obvious which is which:

```yaml
services:
  birdnet-go:
    image: ghcr.io/tphakala/birdnet-go:nightly
    # …BirdNET-Go's own config…

  installer:   # from this project (paste all three services)
    image: ${AV_IMAGE_BASE}-installer:${AV_IMAGE_TAG:-latest}
    # …
  adapter:
    image: ${AV_IMAGE_BASE}-adapter:${AV_IMAGE_TAG:-latest}
    # …
  web:
    image: ${AV_IMAGE_BASE}-web:${AV_IMAGE_TAG:-latest}
    ports: ["${AV_WEB_PORT:-8090}:80"]
    # …
```

They share the compose network, so set `AV_BIRDNETGO_URL=http://birdnet-go:8080`
(the service name). In your `.env`, BirdNET-Go's variables and the `AV_*` ones
coexist without clashing; `TZ` is shared by both on purpose.

---

## Display preferences (menu)

AV's client-side view preferences normally live in an admin settings panel that
this deployment disables, so the installer re-exposes them as a small block in
the **menu dropdown** (top-right "menu" button), reachable from every view and
saved per-browser (each visitor chooses their own):

- **theme** — auto / light / dark (auto follows the device)
- **bird names** — show/hide species names on the collage
- **atlas** — *heard* (species in the selected time window) or *full* (your
  whole life list)

The dead "Live audio" button is hidden (it targeted BirdNET-Pi's `/stream`;
BirdNET-Go serves live audio over HLS instead — not wired here). These are
applied by [`installer/patch_theme_toggle.py`](installer/patch_theme_toggle.py),
idempotently, on every install.

## Storage

All data lives under **one host directory you choose**, `AV_DATA_DIR` (bind-mounted
into all three services). Set it in `.env`:

```env
AV_DATA_DIR=/volume1/docker/avian-visitors   # or leave ./data (next to the compose file)
```

Because it's a plain folder on your host/NAS — not a Docker-managed volume —
your NAS backs it up like anything else, and **everything persists across
`docker compose down` and rebuilds**, including any Gemini-generated art. The
directory is created automatically on first run.

```
$AV_DATA_DIR/
├── site/                    frontend + generated dims.json/masks.json
├── assets/illustrations/    all pack PNGs + generated art (+ raw/ for Gemini)
└── gen/                     generation scripts + refs (only if enabled)
```

What it does **not** contain: your detections, audio, or database — those stay
in BirdNET-Go. So this folder is safe to back up or delete; the installer
rebuilds everything except Gemini-generated art (which is why keeping it on your
NAS matters). Typical size ~600 MB with the GB-ENG pack.

**Permissions note:** the adapter runs as UID `10001`. When generation is
enabled, the installer `chown`s the writable dirs to that UID. On a local disk
this just works; on some NAS shares `chown` is restricted — if generation can't
write, make `$AV_DATA_DIR` writable by UID 10001, set `AV_ADAPTER_UID` to your share's
owner, or run the adapter as that user. Read-only serving (the default) works
regardless.

---

## Illustration packs

The collage draws each bird as an illustration, keyed by the **slugified
scientific name**: `Turdus migratorius` → `turdus-migratorius.png` (perched)
and `turdus-migratorius-2.png` (flight, optional).

A **pack** is any git repo containing PNGs with that naming. The installer
looks for them in `illustrations/`, then `avian/assets/illustrations/`, then
the repo root. Example packs:

- `https://github.com/lloydalexporter/AvianAssets_GB-ENG.git` — Great Britain / England (~725 species)
- `https://github.com/Twarner491/AvianVisitors.git` — the bundled base set (via `AV_INCLUDE_BASE_PACK=true`)

### Adding one or more packs

Set `AV_PACKS` in `.env` (space-separated, order = overlay priority; later wins):

```env
AV_PACKS=https://github.com/lloydalexporter/AvianAssets_GB-ENG.git https://github.com/you/my-local-birds.git
```

then:

```bash
AV_FORCE_PACKS=true docker compose run --rm installer   # clone packs, rebuild collage tables
docker compose restart web adapter
```

`AV_FORCE_PACKS=true` is required to refresh once the data dir already exists —
otherwise the installer skips the (expensive) pack download and mask rebuild.
The installer merges every pack's PNGs into one illustration set and
regenerates `dims.json` + `masks.json` (the silhouette/aspect tables the
collage needs) automatically with AV's own `build_masks.py`. Species your
BirdNET-Go detects that no pack covers fall back to a neutral silhouette.

### British taxonomy overlay (Atlas stamps + family labels)

AV decides each species' Atlas **stamp style** and its **family label** from a
hard-coded genus→family table in `stamps.js` that is North-America-centric. So
out of the box, most GB birds show a generic silhouette stamp and "Family:
Other". The installer applies [`patch_stamps.py`](installer/patch_stamps.py),
a British-birds overlay (keyed by true Linnaean family) that gives GB genera
the **correct family** (e.g. Robin → Muscicapidae, Starling → Sturnidae) and a
proper family stamp template. It's idempotent and re-applied on every install.

To extend it (add genera or change a family→template choice), edit the `GB`
table in `patch_stamps.py` and re-run the installer. Families with no natural
AV template are mapped to the closest existing style.

### On-demand illustration generation (optional, Gemini)

For a species with **no installed illustration**, the detail modal's "generate
image" button can render one on demand via Google Gemini — perched + flight,
with an instant chroma cutout — then rebuild the collage tables so the bird
appears. It reuses AvianVisitors' own generation scripts.

**Off by default.** To enable, set in `.env`:

```env
AV_GENERATE_ENABLED=true
AV_GEMINI_API_KEY=your-key      # https://aistudio.google.com/apikey (billing required)
# AV_GENERATE_HOURLY_CAP=6      # cost brake (default 6)
```

then redeploy the stack (Portainer **Pull and redeploy**, or `docker compose up
-d`). The installer stages the generation scripts + style references into the
data dir; the adapter spawns them
on demand and reports progress to the modal. Generated art is chroma-cut (no
heavy ML models) and saved into your illustration set, so it persists.

Rarely needed if your `AV_PACKS` already cover your region — a British station with
the GB-ENG pack has few gaps. Note: image generation incurs Gemini API cost per
render, hence the hourly cap.

### Making your own pack

Create a repo with an `illustrations/` folder of `<slug>.png` (and optional
`<slug>-2.png`) files, push it, and add its URL to `AV_PACKS`. That's it. To
generate styled illustrations for your region from scratch, see AV's
[scripts pipeline](https://github.com/Twarner491/AvianVisitors/tree/avian-visitors/avian/scripts).

---

## How it works (endpoint mapping)

The adapter implements the AV `birdnet-api.php` actions against BirdNET-Go:

| AV action | BirdNET-Go source |
|-----------|-------------------|
| `recent` (collage) | `GET /api/v2/detections` over the time window, grouped by species |
| `stats` | `GET /api/v2/analytics/species/summary` (all-time / today / week) + recent rows for last-hour |
| `lifelist` | `GET /api/v2/analytics/species/summary` (all-time) |
| `firstseen` | species summary, sorted by first-heard |
| `species` | `GET /api/v2/detections?species=…` + summary |
| `timeseries` / `hourly` / `rhythm` / `calendar` | windowed `GET /api/v2/detections`, bucketed adapter-side |
| `cutout.php` | local illustration from installed packs (neutral silhouette fallback) |
| `recording.php` | proxied `GET /api/v2/audio/:id` (resolves species → best clip) |
| `spectrogram.php` | proxied `GET /api/v2/spectrogram/:id` |

Upstream responses are cached for `AV_CACHE_TTL` seconds.

---

## Operating

```bash
docker compose logs -f adapter        # adapter logs (set AV_LOG_LEVEL=DEBUG for detail)
docker compose ps                     # service status
curl "http://localhost:8090/avian/api/birdnet-api.php?action=stats"   # smoke test
```

The adapter exposes `/healthz` (liveness) and `/readyz` (checks BirdNET-Go is
reachable) on its internal port.

### Troubleshooting

- **Collage empty / "cannot reach BirdNET-Go"** — check `AV_BIRDNETGO_URL` is
  reachable *from the container*: `docker compose exec adapter python -c "import urllib.request,os; print(urllib.request.urlopen(os.environ.get('BIRDNETGO_URL','')+'/api/v2/ping').read())"`. See [Networking](#networking).
- **Birds show as grey silhouettes** — no illustration for that species; add a
  pack that covers it (or `AV_INCLUDE_BASE_PACK=true`).
- **Wrong "today" counts** — set `TZ` to your local timezone.
- **Stats charts look truncated on a busy station** — raise `AV_MAX_DETECTIONS`.
- **401/403 from BirdNET-Go** — set `AV_BIRDNETGO_API_TOKEN`.

---

## Development

```bash
cd adapter
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest            # pure-logic tests (no network)
uvicorn app.main:app --reload --port 9000   # needs AV_BIRDNETGO_URL set
```

---

## Credits & license

- **Avian Visitors** by Teddy Warner — frontend, illustrations, collage tooling.
  Fetched at deploy time, not redistributed here.
- **BirdNET-Go** by Tomi Hakala.
- Both are **CC-BY-NC-SA-4.0** (non-commercial), inherited from BirdNET-Pi /
  Cornell. This adapter is provided for personal, non-commercial use under the
  same terms. Illustration packs carry their own authors' licenses.
