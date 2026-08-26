#!/usr/bin/env bash
#
# One-shot installer: populates the shared volume with
#   /data/site/    -> Avian Visitors static frontend (index.html, apt.js, css…)
#   /data/assets/illustrations/*.png -> bird illustrations from packs
#   /data/site/dims.json + masks.json -> collage layout tables (generated)
#
# It fetches the AV frontend + the build_masks tool from the upstream repo
# with a partial/sparse clone (no multi-GB blob download), overlays any
# illustration packs you configure, applies the British taxonomy patch, and
# regenerates the collage tables.
#
# IDEMPOTENT + CHEAP ON RE-RUN: once the volume is populated, subsequent runs
# (every `docker compose up`) skip the frontend fetch, pack download, and mask
# rebuild — they take ~1s. To refresh:
#   FORCE_PACKS=true    docker compose run --rm installer   # add/refresh packs
#   FORCE_FRONTEND=true docker compose run --rm installer   # refresh the UI
#
set -euo pipefail

DATA=/data
SITE="$DATA/site"
ASSETS="$DATA/assets/illustrations"

AV_REPO="${AV_REPO:-https://github.com/Twarner491/AvianVisitors.git}"
AV_REF="${AV_REF:-avian-visitors}"
PACKS="${PACKS:-}"
INCLUDE_BASE_PACK="${INCLUDE_BASE_PACK:-false}"
FORCE_FRONTEND="${FORCE_FRONTEND:-false}"
FORCE_PACKS="${FORCE_PACKS:-false}"
GENERATE_ENABLED="${GENERATE_ENABLED:-false}"
ADAPTER_UID="${ADAPTER_UID:-10001}"
SITE_TITLE="${SITE_TITLE:-Avian Visitors}"
GEN="$DATA/gen"

log() { printf '[installer] %s\n' "$*"; }

mkdir -p "$SITE" "$ASSETS"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# --------------------------------------------------------------------------
# Decide whether the heavy work is needed. Skip it when the volume already
# holds a frontend + collage tables + at least one illustration, unless a
# FORCE flag asks for a refresh.
# --------------------------------------------------------------------------
have_assets=false
[ -n "$(find "$ASSETS" -name '*.png' -print -quit 2>/dev/null)" ] && have_assets=true

if [ -f "$SITE/index.html" ] && [ -f "$SITE/dims.json" ] && [ "$have_assets" = "true" ] \
   && [ "$FORCE_FRONTEND" != "true" ] && [ "$FORCE_PACKS" != "true" ]; then
  log "Already installed — skipping frontend fetch, pack download, and mask rebuild."
  log "  (FORCE_PACKS=true to add/refresh packs; FORCE_FRONTEND=true to refresh the UI.)"
else
  # ---- 1. Avian Visitors frontend + build_masks tool (sparse, blobless) ----
  if [ "$FORCE_FRONTEND" = "true" ] || [ ! -f "$SITE/index.html" ]; then
    log "Fetching Avian Visitors frontend + tools ($AV_REF)…"
    git clone --filter=blob:none --no-checkout --depth 1 --branch "$AV_REF" \
      "$AV_REPO" "$work/av"
    git -C "$work/av" sparse-checkout init --cone
    paths="avian/frontend avian/scripts"
    [ "$INCLUDE_BASE_PACK" = "true" ] && paths="$paths avian/assets/illustrations"
    # shellcheck disable=SC2086
    git -C "$work/av" sparse-checkout set $paths
    git -C "$work/av" checkout
    log "Installing frontend into $SITE"
    cp -a "$work/av/avian/frontend/." "$SITE/"
    if [ "$INCLUDE_BASE_PACK" = "true" ]; then
      log "Installing bundled base illustration pack (AvianVisitors, ~333 species)…"
      cp -an "$work/av/avian/assets/illustrations/." "$ASSETS/" 2>/dev/null || true
    fi
  else
    log "Frontend present; fetching build_masks tool only…"
    git clone --filter=blob:none --no-checkout --depth 1 --branch "$AV_REF" \
      "$AV_REPO" "$work/av"
    git -C "$work/av" sparse-checkout init --cone
    git -C "$work/av" sparse-checkout set avian/scripts
    git -C "$work/av" checkout
  fi
  BUILD_MASKS="$work/av/avian/scripts/build_masks.py"

  # ---- 2. Illustration packs ----
  # A pack is any git repo of <slug>.png (perched) + optional <slug>-2.png
  # (flight). We look in illustrations/, then avian/assets/illustrations/,
  # then the repo root.
  install_pack() {
    local repo="$1" dir src count
    dir="$work/pack-$(printf '%s' "$repo" | md5sum | cut -c1-10)"
    log "Cloning pack: $repo"
    if ! git clone --depth 1 "$repo" "$dir" 2>/dev/null; then
      log "WARNING: failed to clone $repo — skipping"
      return 0
    fi
    if   [ -d "$dir/illustrations" ]; then src="$dir/illustrations"
    elif [ -d "$dir/avian/assets/illustrations" ]; then src="$dir/avian/assets/illustrations"
    else src="$dir"
    fi
    count="$(find "$src" -maxdepth 3 -type f -name '*.png' | wc -l | tr -d ' ')"
    log "  found $count PNGs under $(basename "$src")/ — copying"
    find "$src" -maxdepth 3 -type f -name '*.png' -exec cp -f {} "$ASSETS/" \;
  }
  if [ -n "$PACKS" ]; then
    for repo in $PACKS; do install_pack "$repo"; done
  else
    log "No PACKS configured."
  fi

  # ---- 3. Regenerate collage tables (dims.json + masks.json) ----
  total="$(find "$ASSETS" -type f -name '*.png' | wc -l | tr -d ' ')"
  log "Total illustrations installed: $total"
  if [ "$total" -gt 0 ]; then
    log "Building dims.json + masks.json from installed illustrations…"
    python3 "$BUILD_MASKS" --illustrations "$ASSETS" --frontend "$SITE"
    log "Collage tables written to $SITE/dims.json and $SITE/masks.json"
  else
    log "No illustrations installed; keeping AvianVisitors' default collage tables."
    log "TIP: set PACKS or INCLUDE_BASE_PACK=true to populate illustrations."
  fi
fi

# --------------------------------------------------------------------------
# Always apply the British taxonomy patch — it's an instant, idempotent text
# edit of stamps.js (GB genus->family + Atlas stamp styles). Runs even on the
# fast/skip path so a freshly-added patch still lands without a full refresh.
# --------------------------------------------------------------------------
if [ -f /usr/local/bin/patch_stamps.py ] && [ -f "$SITE/stamps.js" ]; then
  log "Applying GB taxonomy patch to stamps.js"
  python3 /usr/local/bin/patch_stamps.py "$SITE/stamps.js" || true
fi

# Add a standalone auto/light/dark theme toggle (AV's own toggle lives in the
# disabled admin menu). Instant, idempotent edit of index.html.
if [ -f /usr/local/bin/patch_theme_toggle.py ] && [ -f "$SITE/index.html" ]; then
  log "Adding theme toggle to index.html"
  python3 /usr/local/bin/patch_theme_toggle.py "$SITE/index.html" || true
fi

# Set the browser-tab title (upstream ships "your birds"). Instant, idempotent
# edit; SITE_TITLE controls the value (default "Avian Visitors").
if [ -f /usr/local/bin/patch_title.py ] && [ -f "$SITE/index.html" ]; then
  log "Setting browser-tab title to '$SITE_TITLE'"
  SITE_TITLE="$SITE_TITLE" python3 /usr/local/bin/patch_title.py "$SITE/index.html" || true
fi

# --------------------------------------------------------------------------
# Optional: stage AV's on-demand generation scripts so the adapter can render
# missing species via Gemini. Sets up an `avian/` layout whose asset/frontend
# dirs symlink to the live volume, then hands write access to the adapter user.
# --------------------------------------------------------------------------
if [ "$GENERATE_ENABLED" = "true" ]; then
  if [ ! -f "$GEN/avian/scripts/generate_one.py" ] || [ "$FORCE_FRONTEND" = "true" ]; then
    log "Staging on-demand generation scripts + references…"
    git clone --filter=blob:none --no-checkout --depth 1 --branch "$AV_REF" \
      "$AV_REPO" "$work/avgen" 2>/dev/null || git clone --depth 1 --branch "$AV_REF" "$AV_REPO" "$work/avgen"
    git -C "$work/avgen" sparse-checkout init --cone 2>/dev/null || true
    git -C "$work/avgen" sparse-checkout set avian/scripts avian/assets/references 2>/dev/null || true
    git -C "$work/avgen" checkout 2>/dev/null || true
    mkdir -p "$GEN/avian/assets"
    cp -a "$work/avgen/avian/scripts" "$GEN/avian/scripts"
    if [ -d "$work/avgen/avian/assets/references" ]; then
      cp -a "$work/avgen/avian/assets/references" "$GEN/avian/assets/references"
    else
      mkdir -p "$GEN/avian/assets/references"
    fi
    # Wire the reused scripts' relative paths to the live volume.
    ln -sfn "$ASSETS" "$GEN/avian/assets/illustrations"
    ln -sfn "$SITE"   "$GEN/avian/frontend"
    log "Generation staged at $GEN/avian/scripts"
  else
    log "Generation scripts already staged (FORCE_FRONTEND=true to refresh)."
  fi
  # The adapter runs as a non-root user; give it ownership of the dirs the
  # generator writes (new PNGs, raw/, state, collage tables, lock/log).
  log "Granting adapter (uid $ADAPTER_UID) write access to generation dirs…"
  chown -R "$ADAPTER_UID":"$ADAPTER_UID" "$GEN" "$ASSETS" "$SITE" 2>/dev/null || \
    chmod -R a+rwX "$GEN" "$ASSETS" "$SITE" 2>/dev/null || true
fi

log "Done."
