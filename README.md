# Avian Visitors for BirdNET-Go

Run the [Avian Visitors](https://github.com/Twarner491/AvianVisitors) bird
collage and stats UI on top of an existing **[BirdNET-Go](https://github.com/tphakala/birdnet-go)**
instance — no BirdNET-Pi required.

> **Built on the [Avian Visitors](https://github.com/Twarner491/AvianVisitors) project by Tim Warner.**
> All the UI, design, and visualizations are theirs — this project simply
> **adapts** Avian Visitors to run against **BirdNET-Go** instead of BirdNET-Pi.
> I built it because I already run BirdNET-Go and wanted its collage and stats
> without switching stacks. The Avian Visitors frontend is used **unmodified**;
> if you enjoy this, please star and support the [upstream project](https://github.com/Twarner491/AvianVisitors).

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

- A Docker host with **Docker Compose v2** (`docker compose`). Standalone Docker,
  not Swarm.
- A running **BirdNET-Go** instance reachable over HTTP from that host.
- The images published to a registry — see [Publishing the images](#publishing-the-images).
  (One-time; you can make them public so any host just pulls them.)

## Deploy (Docker Compose)

On your Docker host:

```bash
git clone https://github.com/<owner>/avian-visitors-birdnet-go.git
cd avian-visitors-birdnet-go
cp .env.example .env
nano .env          # set AV_IMAGE_BASE, AV_BIRDNETGO_URL, AV_DATA_DIR (absolute), AV_PACKS, TZ

docker compose up -d
```

Then open **`http://<host>:8090`** (or your `AV_WEB_PORT`).

Minimum you must set in `.env`:

| Variable | Example | Notes |
|----------|---------|-------|
| `AV_IMAGE_BASE` | `ghcr.io/<owner>/avian-visitors-birdnet-go` | Where the images live (lowercase owner). |
| `AV_BIRDNETGO_URL` | `http://192.168.1.50:8080` | Your BirdNET-Go, reachable from the host. |
| `AV_DATA_DIR` | `/srv/avian-visitors` | **Absolute host path** for all data (see [Storage](#storage)). |
| `AV_PACKS` | `https://github.com/lloydalexporter/AvianAssets_GB-ENG.git` | Illustration pack(s). |
| `TZ` | `Europe/London` | Correct "today" boundaries. |

Full list in [.env.example](.env.example) and [Configuration](#configuration).

**What happens on first `up`:** the one-shot `installer` runs first — it fetches
the Avian Visitors frontend, downloads your illustration pack(s), and builds the
collage tables into `AV_DATA_DIR` (a few minutes; ~1,400 files for GB-ENG). Then
`adapter` and `web` start. Later `up`s are instant — the installer skips the
heavy work once the data dir is populated. (`installer` ending in `Exited (0)`
is expected; it's a job, not a service.)

The images are published **public**, so any host can pull them with no login.
(If you keep them private instead, log in on the host first so Compose can pull:)

```bash
echo <GHCR_PAT> | docker login ghcr.io -u <github-user> --password-stdin
```

### Everyday operations

```bash
docker compose logs -f adapter          # follow adapter logs
docker compose pull && docker compose up -d   # update to newer images
docker compose down                     # stop (AV_DATA_DIR is a bind mount → your data stays)
```

**Add or change illustration packs:** edit `AV_PACKS` in `.env`, then force one
refresh (the installer otherwise skips the pack download once populated):

```bash
AV_FORCE_PACKS=true docker compose up -d
```

`AV_FORCE_FRONTEND=true` likewise re-fetches the AV frontend (e.g. after an AV
upgrade).

## Deploy with Portainer (optional)

Prefer a UI? It's the same compose file:

- **Stacks → Add stack → Web editor**, paste [`docker-compose.yml`](docker-compose.yml),
  add the environment variables from the table above (Portainer's env fields
  replace the `.env` file), and **Deploy**.
- Use an **absolute `AV_DATA_DIR`** — a relative path lands inside Portainer's
  internal stack folder, not where you want it.
- Private images: **Registries → Add registry → Custom**, `ghcr.io`, your GitHub
  user + a `read:packages` PAT.
- Update via the stack's **Pull and redeploy**.

## Publishing the images

The images are built and pushed to GHCR by GitHub Actions —
[`.github/workflows/build-images.yml`](.github/workflows/build-images.yml) — on
every push to `main` (also on `v*` tags, or manually via **Actions → Run
workflow**). It produces three **multi-arch (amd64 + arm64)** images:

```
ghcr.io/<owner>/avian-visitors-birdnet-go-adapter
ghcr.io/<owner>/avian-visitors-birdnet-go-installer
ghcr.io/<owner>/avian-visitors-birdnet-go-web
```

Push this repo to GitHub and the first build runs automatically (~5–10 min; arm64
is emulated). GHCR packages start **private** even for a public repo, so after
the first build set each package **Public** (GitHub → package → *Package settings
→ Change visibility → Public*) so any host pulls without a login — that's the
setup these instructions assume. Prefer to keep them private? Leave them as-is
and `docker login ghcr.io` on the host / add a Portainer registry credential.
`<owner>` is your GitHub username/org, lowercased.

> No CI? The `Dockerfile`s are here too — `docker build ./adapter` (and
> `./installer`, `./web`), tag them as `${AV_IMAGE_BASE}-<service>`, and push to any
> registry you like.

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

**Permissions note:** the adapter runs, by default, as the image's non-root
user (UID `10001`). On a local disk this just works. On a NAS whose data
dataset is owned by a specific user (e.g. TrueNAS's `apps` user, UID `568`),
UID 10001 usually can't read the bind-mounted data — set `AV_ADAPTER_USER` to
the dataset's owner so the (still non-root) adapter matches it:

```env
AV_ADAPTER_USER=568:568
```

`web` intentionally stays root (nginx binds port 80). Read-only serving (the
default) works with this alone.

The one-shot **installer** runs as root by default (`AV_INSTALLER_USER=0:0`) so
it can write the data dir and set ownership on any host. On a NAS you can
instead run it as the dataset's owner so the files it installs are owned by that
user natively:

```env
AV_INSTALLER_USER=568:568
```

If you **enable generation**, note it runs *inside the adapter* (the adapter
spawns the generator as its own user; the installer only stages the scripts).
So the writable dirs must be owned by the adapter's UID: set `AV_ADAPTER_UID`
to the same value as `AV_ADAPTER_USER`'s UID — e.g. `AV_ADAPTER_UID=568` — and
the installer will `chown` them to match (when it runs as root; when it runs as
that same non-root user the files are already owned correctly). On shares where
`chown` is restricted, make `$AV_DATA_DIR` writable by that UID out-of-band.

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

then redeploy (`docker compose up -d`, or Portainer **Pull and redeploy**). The
installer stages the generation scripts + style references into the data dir;
the adapter spawns them
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

Day-to-day commands (logs, update, stop) are under
[Everyday operations](#everyday-operations). Quick health checks:

```bash
curl "http://localhost:8090/avian/api/birdnet-api.php?action=stats"   # data smoke test
docker compose logs adapter | tail            # set AV_LOG_LEVEL=DEBUG in .env for detail
```

The adapter also exposes `/healthz` (liveness) and `/readyz` (checks BirdNET-Go
is reachable) on its internal port.

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
