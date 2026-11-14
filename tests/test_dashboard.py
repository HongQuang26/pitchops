"""Security and immutable-view regressions for the offline dashboard."""
import json
import re
from pathlib import Path

import pytest

from pitchops.dashboard import render_dashboard, refresh_dashboard
from pitchops.data import atomic_json
from pitchops.storage import latest_dashboard


def test_untrusted_json_cannot_close_script_or_expand_template_markers(tmp_path):
    payload = {'name': '</script><img src=x onerror=alert(1)>',
               'markers': ['__PITCHOPS_DATA__', '__PITCHOPS_APP__',
                           '__PITCHOPS_ANALYTICS__', '__PITCHOPS_STYLES__'],
               'unicode': 'Nguyễn Hồng Quang & Đội bóng'}
    output = tmp_path/'dashboard.html'
    render_dashboard(payload, output)
    document = output.read_text()
    serialized = re.search(r'<script>const DATA=(.*?);</script>', document, re.S).group(1)
    assert json.loads(serialized) == payload
    assert '<img src=x' not in document
    assert '<script src=' not in document
    assert '<link rel="stylesheet"' not in document
    assert 'function renderActive()' in document
    assert 'prefers-reduced-motion' in document


def test_nonfinite_values_rejected_instead_of_generating_broken_javascript(tmp_path):
    with pytest.raises(ValueError):
        render_dashboard({'probability': float('nan')}, tmp_path/'dashboard.html')


def saved_snapshot(root):
    model = root/'artifacts'/'runs'/'model-1'
    model.mkdir(parents=True)
    payload = {'meta': {'run_id':'model-1','code_commit':'trained-code'},
               'leagues': {}, 'research': {'run_id':'replay-1'},
               'media': {'players':[{'id':'person-1','name':'A'}]}}
    atomic_json(model/'snapshot.json', payload)
    atomic_json(root/'artifacts'/'latest.json', {'run_id':'model-1'})
    return model, payload


def test_ui_refresh_preserves_model_research_media_and_source_lineage(tmp_path):
    model, original = saved_snapshot(tmp_path)
    model_bytes = (model/'snapshot.json').read_bytes()
    payload, view = refresh_dashboard(tmp_path)
    assert view != model and (view/'dashboard.html').exists()
    assert (model/'snapshot.json').read_bytes() == model_bytes
    assert payload['meta']['code_commit'] == 'trained-code'
    assert payload['research'] == original['research']
    assert payload['media'] == original['media']
    assert json.loads((view/'source_run.json').read_text())['source_view_id'] == model.name
    assert latest_dashboard(tmp_path)[1] == view


def test_failed_ui_render_does_not_promote_partial_view(tmp_path, monkeypatch):
    model, _ = saved_snapshot(tmp_path)
    def fail(*args):
        raise OSError('Disk unavailable')
    monkeypatch.setattr('pitchops.dashboard.render_dashboard', fail)
    with pytest.raises(OSError, match='Disk unavailable'):
        refresh_dashboard(tmp_path)
    assert not (tmp_path/'artifacts'/'latest_view.json').exists()
    assert latest_dashboard(tmp_path)[1] == model
