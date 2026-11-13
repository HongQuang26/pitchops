"""Persistent workspace migration with verified copies and preserved quota logs."""
import hashlib
import json
import shutil
from pathlib import Path
from .data import atomic_json

def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def migrate_workspace(source, destination):
    """Copy an existing Colab workspace to Drive; retain the source as a backup.

    Identical files are skipped. Mutable caches preserve the newer copy and
    provider ledgers are merged. Conflicting immutable run artifacts fail closed.
    Run with one writer; Google Drive is not a distributed transactional database.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if source == destination:
        return {"copied": 0, "verified": 0, "skipped": 0, "source": str(source), "destination": str(destination)}
    if source in destination.parents or destination in source.parents:
        raise ValueError('Workspaces must not be nested')
    report = {"copied": 0, "verified": 0, "skipped": 0, "source": str(source), "destination": str(destination)}
    if source.exists():
        for src in sorted(source.rglob('*')):
            if not src.is_file() or src.name.endswith('.tmp'):
                continue
            rel = src.relative_to(source)
            if rel.as_posix() in {'artifacts/latest.json','artifacts/latest_view.json','migration_report.json','drive_write_check.txt'}:
                continue
            dst = destination / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                if file_hash(src) == file_hash(dst):
                    report['skipped'] += 1
                    continue
                if 'data' in rel.parts and src.suffix == '.json':
                    try:
                        left, right = json.loads(src.read_text()), json.loads(dst.read_text())
                        if isinstance(left, list) and isinstance(right, list) and all(isinstance(x, dict) and 'time' in x for x in left + right):
                            merged = {json.dumps(x, sort_keys=True): x for x in right + left}
                            atomic_json(dst, sorted(merged.values(), key=lambda x: x['time']))
                            report['verified'] += 1
                            continue
                    except (ValueError, OSError):
                        pass
                if rel.parts[0] == 'data':
                    if dst.stat().st_mtime >= src.stat().st_mtime:
                        report['skipped'] += 1
                        continue
                else:
                    raise FileExistsError(f'Conflicting immutable artifact: {rel}')
            tmp = dst.with_name(dst.name + '.migration.tmp')
            shutil.copy2(src, tmp)
            if file_hash(src) != file_hash(tmp):
                tmp.unlink(missing_ok=True)
                raise IOError(f'Copy verification failed: {rel}')
            tmp.replace(dst)
            report['copied'] += 1
            report['verified'] += 1
    runs = sorted((destination / 'artifacts' / 'runs').glob('*/snapshot.json'))
    if runs:
        latest = runs[-1]
        atomic_json(destination / 'artifacts' / 'latest.json', {"run_id": latest.parent.name, "snapshot": str(latest)})
        views = sorted((destination/'artifacts'/'views').glob(latest.parent.name+'-media-*/snapshot.json'))
        if views:
            atomic_json(destination/'artifacts'/'latest_view.json', {'model_run_id':latest.parent.name,'view_id':views[-1].parent.name})
    atomic_json(destination / 'migration_report.json', report)
    return report

def latest_run(root):
    root = Path(root)
    pointer = json.loads((root / 'artifacts' / 'latest.json').read_text())
    # Resolve relative to the current workspace, not a previous Colab mount.
    run_dir = root / 'artifacts' / 'runs' / pointer['run_id']
    payload = json.loads((run_dir / 'snapshot.json').read_text())
    return payload, run_dir

def verify_persistence(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    probe = root / 'drive_write_check.txt'
    probe.write_text('PitchOps persistence check passed\n', encoding='utf-8')
    if probe.read_text() != 'PitchOps persistence check passed\n':
        raise IOError('Drive write/read verification failed')
    return {"workspace": str(root), "write_read_verified": True, "latest_exists": (root / 'artifacts' / 'latest.json').is_file()}

def latest_dashboard(root):
    payload, run_dir = latest_run(root)
    path = Path(root)/'artifacts'/'latest_view.json'
    if path.exists():
        view = json.loads(path.read_text())
        if view.get('model_run_id') == run_dir.name:
            view_dir = Path(root)/'artifacts'/'views'/view['view_id']
            if (view_dir/'snapshot.json').exists():
                return json.loads((view_dir/'snapshot.json').read_text()), view_dir
    return payload, run_dir
