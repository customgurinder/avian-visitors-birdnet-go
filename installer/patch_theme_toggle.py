#!/usr/bin/env python3
"""Add a display-preferences block to AvianVisitors' menu dropdown, and hide
the dead "Live audio" button.

AV's client-side view preferences (theme, collage labels, full-vs-heard atlas)
normally live in the admin "settings" panel — which this visualization-only
deployment disables. This injects them as compact rows into the menu dropdown
(`.menu-sheet`, opened by the top-right "menu" button), just above the
"built by" credit, reachable from every view:

  * theme       auto / light / dark   -> localStorage bird:theme:v2
  * bird names  off / on              -> localStorage bird:labels
  * atlas       heard / full          -> localStorage bird:atlasAlwaysAll:v1

Each is per-browser and drives AV's own state: theme + atlas dispatch a
`storage` event (AV's global listener re-resolves + repaints); labels dispatch
a `resize` (AV re-renders the collage). No edits to apt.js.

It also hides `#liveAudio` — AV's "LISTEN" button targets BirdNET-Pi's `/stream`
mic feed, which this deployment doesn't serve (BirdNET-Go offers HLS instead),
so the button would be dead. Removing it avoids a broken control.

Idempotent and update-safe: an existing block (between the markers) is removed
and re-injected. Anchors on the menu credit; skips if not found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

START = "<!-- AVIAN-THEME-TOGGLE:start -->"
END = "<!-- AVIAN-THEME-TOGGLE:end -->"
ANCHOR = '<p class="built-by">'

# Plain string (NOT an f-string / .format) so CSS/JS braces stay literal.
SNIPPET = """<!-- AVIAN-THEME-TOGGLE:start -->
<style>
#liveAudio{display:none!important}
#avian-menu-prefs{display:flex;flex-direction:column;gap:6px;margin:8px 0 4px;
  font:600 11px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;letter-spacing:.04em;color:inherit}
#avian-menu-prefs .pref-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
#avian-menu-prefs .lbl{opacity:.6;text-transform:lowercase}
#avian-menu-prefs .seg{display:inline-flex;border-radius:999px;overflow:hidden;
  background:rgba(128,128,128,.16)}
#avian-menu-prefs button{appearance:none;-webkit-appearance:none;border:0;margin:0;
  background:transparent;color:inherit;padding:6px 10px;cursor:pointer;
  text-transform:lowercase;opacity:.65}
#avian-menu-prefs button:hover{opacity:.9}
#avian-menu-prefs button[aria-current="true"]{opacity:1;background:rgba(128,128,128,.28)}
</style>
<div id="avian-menu-prefs" role="group" aria-label="Display preferences">
  <div class="pref-row" data-pref="theme">
    <span class="lbl">theme</span>
    <span class="seg"><button type="button" data-val="auto">auto</button><button type="button" data-val="light">light</button><button type="button" data-val="dark">dark</button></span>
  </div>
  <div class="pref-row" data-pref="labels">
    <span class="lbl">bird names</span>
    <span class="seg"><button type="button" data-val="off">off</button><button type="button" data-val="on">on</button></span>
  </div>
  <div class="pref-row" data-pref="atlas">
    <span class="lbl">atlas</span>
    <span class="seg"><button type="button" data-val="off">heard</button><button type="button" data-val="on">full</button></span>
  </div>
</div>
<script>
(function(){
  var box=document.getElementById('avian-menu-prefs');
  if(!box) return;
  var THEME='bird:theme:v2', LABELS='bird:labels', ATLAS='bird:atlasAlwaysAll:v1';
  function ls(k,d){try{var v=localStorage.getItem(k);return v==null?d:v;}catch(e){return d;}}
  function sysDark(){try{return !!(window.matchMedia&&
    window.matchMedia('(prefers-color-scheme: dark)').matches);}catch(e){return false;}}
  function cur(pref){
    if(pref==='theme'){var v=ls(THEME,'auto');return (v==='light'||v==='dark')?v:'auto';}
    if(pref==='labels'){return ls(LABELS,'on')==='off'?'off':'on';}
    return ls(ATLAS,'off')==='on'?'on':'off';
  }
  function paintTheme(v){document.documentElement.setAttribute('data-theme',
    (v==='light'||v==='dark')?v:(sysDark()?'dark':'light'));}
  function mark(row,v){var b=row.querySelectorAll('button[data-val]'),i;
    for(i=0;i<b.length;i++){b[i].setAttribute('aria-current',
      b[i].getAttribute('data-val')===v?'true':'false');}}
  function apply(pref,v){
    if(pref==='theme'){
      try{localStorage.setItem(THEME,v);}catch(e){}
      try{window.dispatchEvent(new StorageEvent('storage',{key:THEME,newValue:v}));}catch(e){}
      paintTheme(v);
    }else if(pref==='labels'){
      try{localStorage.setItem(LABELS,v);}catch(e){}
      try{window.dispatchEvent(new Event('resize'));}catch(e){}
    }else{
      try{localStorage.setItem(ATLAS,v);}catch(e){}
      try{window.dispatchEvent(new StorageEvent('storage',{key:ATLAS,newValue:v}));}catch(e){}
    }
  }
  var rows=box.querySelectorAll('.pref-row'),i;
  for(i=0;i<rows.length;i++){(function(row){
    var pref=row.getAttribute('data-pref');
    mark(row,cur(pref));
    var b=row.querySelectorAll('button[data-val]'),j;
    for(j=0;j<b.length;j++){(function(btn){
      btn.addEventListener('click',function(){var v=btn.getAttribute('data-val');apply(pref,v);mark(row,v);});
    })(b[j]);}
  })(rows[i]);}
  try{window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){
    if(cur('theme')==='auto')paintTheme('auto');});}catch(e){}
  paintTheme(cur('theme'));
})();
</script>
<!-- AVIAN-THEME-TOGGLE:end -->
"""


def _strip_existing(src: str) -> str:
    return re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", src, flags=re.S)


def patch(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    had = START in src
    src = _strip_existing(src)

    idx = src.find(ANCHOR)
    if idx < 0:
        if had:
            path.write_text(src, encoding="utf-8")
            print(f"[patch_theme_toggle] removed stale block; menu anchor not found in {path}")
            return 0
        print(f"[patch_theme_toggle] WARNING: menu credit anchor not found in {path}; skipping")
        return 0
    out = src[:idx] + SNIPPET + src[idx:]
    path.write_text(out, encoding="utf-8")
    print(f"[patch_theme_toggle] {'updated' if had else 'injected'} menu preferences in {path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_theme_toggle.py <path-to-index.html>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"[patch_theme_toggle] not found: {p}; skipping")
        return 0
    return patch(p)


if __name__ == "__main__":
    raise SystemExit(main())
