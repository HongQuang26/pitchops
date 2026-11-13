"""Weekly check-on-open orchestration, with persisted success/failure receipts.

This is intentionally not an always-on scheduler. It is invoked by Colab; no
heartbeat, account automation, token in GitHub, or hidden paid infrastructure.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
from .data import atomic_json

def run_if_due(root,task,job,interval_days=7,now=None,force=False):
    if not task or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in task):raise ValueError('Safe task name required')
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
    receipt=Path(root)/'artifacts'/'schedule'/(task+'.json')
    state=json.loads(receipt.read_text()) if receipt.exists() else {}
    last=state.get('last_success')
    if not force and last and (now-datetime.fromisoformat(last)).total_seconds()<interval_days*86400:
        return {'status':'not_due','last_success':last}
    state.update({'started_at':now.isoformat(),'status':'running'})
    atomic_json(receipt,state)
    try:
        result=job()
    except Exception as exc:
        state.update({'status':'failed','error_type':type(exc).__name__});atomic_json(receipt,state);raise
    state.update({'status':'completed','last_success':now.isoformat()});state.pop('error_type',None);atomic_json(receipt,state)
    return {'status':'completed','last_success':state['last_success'],'result':result}
