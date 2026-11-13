"""Snapshot HTML with embedded cached artwork and optional remote image fallbacks."""
import json
from pathlib import Path

def render_dashboard(payload, output):
    template = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    safe = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    analytics = Path(__file__).with_name('analytics.js').read_text(encoding='utf-8')
    Path(output).write_text(template.replace("__PITCHOPS_DATA__", safe).replace('__PITCHOPS_ANALYTICS__', analytics), encoding="utf-8")
