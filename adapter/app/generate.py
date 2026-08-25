"""On-demand illustration generation — the real generate.php.

Reuses AvianVisitors' own scripts (generate_one.py + pregen.py + build_masks.py)
verbatim, which the installer stages into the shared volume at
GEN_DIR/avian/scripts with an `avian/` layout wired to the live assets:

    GEN_DIR/avian/scripts/            (AV scripts, run with this Python)
    GEN_DIR/avian/assets/illustrations -> /data/assets/illustrations  (symlink)
    GEN_DIR/avian/assets/references     (Wikipedia ref cache + style refs)
    GEN_DIR/avian/frontend            -> /data/site                   (symlink)

We spawn `generate_one.py --sci --com` (Gemini render → instant chroma cutout →
build_masks --add). It writes progress to
/data/assets/illustrations/.generate.state.json, which the status endpoint
reads. Off unless GENERATE_ENABLED=true and GEMINI_API_KEY is set.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .config import Settings
from .logging_conf import get_logger

log = get_logger("generate")

# Binomial/trinomial, same guard AV uses before a value reaches a subprocess.
_SCI_RE = re.compile(r"^[A-Za-z]{2,40}(?:[ ][a-z]{2,40}){1,3}$")
_STALE_SECONDS = 15 * 60


class Generator:
    def __init__(self, settings: Settings, common_name_lookup):
        self.enabled = settings.generate_enabled and bool(settings.gemini_api_key)
        self.key = settings.gemini_api_key or ""
        self.cap = settings.generate_hourly_cap
        self.gen_dir = Path(settings.gen_dir)
        self.scripts = self.gen_dir / "avian" / "scripts"
        self.illus = Path(settings.assets_dir)
        self.state_file = self.illus / ".generate.state.json"
        self.lock_file = self.gen_dir / "generation.lock"
        self.starts_file = self.gen_dir / "starts.json"
        self.log_file = self.gen_dir / "generate.log"
        self._common_name_lookup = common_name_lookup  # async fn(sci) -> str|None

    def available(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "image generation not configured (set GEMINI_API_KEY and GENERATE_ENABLED=true)"
        if not (self.scripts / "generate_one.py").is_file():
            return False, "generation not installed — set GENERATE_ENABLED=true and re-run the installer"
        return True, ""

    def status(self) -> dict:
        try:
            state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {"running": False}
        if not isinstance(state, dict):
            return {"running": False}
        if state.get("running") and (time.time() - int(state.get("at", 0)) > _STALE_SECONDS):
            state["running"] = False
            state.setdefault("error", "generation timed out")
        return state

    def _recent_starts(self) -> int:
        try:
            starts = json.loads(self.starts_file.read_text())
        except (OSError, ValueError):
            starts = []
        cutoff = time.time() - 3600
        return len([t for t in starts if isinstance(t, (int, float)) and t >= cutoff])

    def _record_start(self) -> None:
        try:
            starts = json.loads(self.starts_file.read_text())
            if not isinstance(starts, list):
                starts = []
        except (OSError, ValueError):
            starts = []
        cutoff = time.time() - 3600
        starts = [t for t in starts if isinstance(t, (int, float)) and t >= cutoff]
        starts.append(time.time())
        try:
            self.starts_file.write_text(json.dumps(starts))
        except OSError:
            pass

    def _write_initial_state(self, sci: str, com: str) -> None:
        try:
            self.state_file.write_text(
                json.dumps({"running": True, "sci": sci, "com": com, "step": "starting",
                            "at": int(time.time())}) + "\n"
            )
        except OSError:
            pass

    async def start(self, sci: str, force: bool = False) -> tuple[int, dict]:
        ok, why = self.available()
        if not ok:
            return 503, {"error": why}
        sci = (sci or "").strip()
        if not _SCI_RE.match(sci):
            return 400, {"error": "invalid sci"}

        st = self.status()
        if st.get("running"):
            return 200, {"ok": True, "running": True, "sci": st.get("sci")}
        if self._recent_starts() >= self.cap:
            return 429, {"error": f"hourly generation cap ({self.cap}) reached"}

        com = ""
        try:
            com = (await self._common_name_lookup(sci)) or ""
        except Exception as exc:  # noqa: BLE001 - best-effort; sci is a fine fallback
            log.debug("common-name lookup failed for %s: %s", sci, exc)
        com = com or sci

        self.gen_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_file.touch(exist_ok=True)
        except OSError as exc:
            log.error("cannot create generation lock %s: %s", self.lock_file, exc)
            return 500, {"error": "generation lock unavailable (check volume permissions)"}

        self._write_initial_state(sci, com)
        env = {
            **os.environ,
            "GEMINI_API_KEY": self.key,
            "AVIAN_GENERATION_LOCK": str(self.lock_file),
        }
        cmd = [sys.executable, str(self.scripts / "generate_one.py"), "--sci", sci, "--com", com]
        if force:
            cmd.append("--force")
        log.info("starting generation for %s (%s)", sci, com)
        try:
            logf = open(self.log_file, "ab")  # noqa: SIM115 - handed to the child
            subprocess.Popen(  # noqa: S603 - args are validated/constructed, not shell
                cmd, cwd=str(self.scripts), env=env, stdout=logf, stderr=logf,
                start_new_session=True,
            )
        except OSError as exc:
            log.error("failed to spawn generator: %s", exc)
            return 500, {"error": f"failed to start generation: {exc}"}
        self._record_start()
        return 200, {"ok": True, "running": True, "sci": sci, "com": com}
