"""Snapshot HTML with embedded cached artwork and optional remote image fallbacks."""
import json
import re
from pathlib import Path

def render_dashboard(payload, output):
    template = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    safe = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    assets = {
        '__PITCHOPS_DATA__': safe,
        '__PITCHOPS_STYLES__': Path(__file__).with_name('dashboard.css').read_text(encoding='utf-8'),
        '__PITCHOPS_APP__': Path(__file__).with_name('dashboard.js').read_text(encoding='utf-8'),
        '__PITCHOPS_ANALYTICS__': Path(__file__).with_name('analytics.js').read_text(encoding='utf-8'),
    }
    # A single pass prevents source text containing template markers from being
    # interpreted as another substitution after JSON has been serialized.
    rendered = re.sub('|'.join(map(re.escape, assets)), lambda match: assets[match.group()], template)
    Path(output).write_text(rendered, encoding='utf-8')


def refresh_dashboard(root):
    """Create a new UI view from saved data, without provider HTTP or retraining."""
    import subprocess
    from datetime import datetime, timezone
    from .data import atomic_json
    from .storage import latest_dashboard

    root = Path(root)
    payload, previous = latest_dashboard(root)
    meta = payload['meta']
    model_id = meta['run_id']
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'uncommitted'
    meta.update(view_code_commit=commit, ui_version='0.5', ui_refreshed_at=datetime.now(timezone.utc).isoformat())
    view_id = model_id + '-ui-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    view = root/'artifacts'/'views'/view_id
    view.mkdir(parents=True, exist_ok=False)
    render_dashboard(payload, view/'dashboard.html')
    atomic_json(view/'snapshot.json', payload)
    atomic_json(view/'source_run.json', {'model_run_id':model_id, 'source_view_id':previous.name, 'view_code_commit':commit})
    atomic_json(root/'artifacts'/'latest_view.json', {'model_run_id':model_id, 'view_id':view_id})
    return payload, view
