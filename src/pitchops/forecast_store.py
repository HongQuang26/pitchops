"""Immutable forecast journal, delayed outcomes and honest replay/live separation."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .data import atomic_json

def utc_naive(value):
    value=pd.Timestamp(value)
    return value.tz_convert('UTC').tz_localize(None) if value.tzinfo else value

def record_forecasts(root,records):
    directory=Path(root)/'forecasts';directory.mkdir(parents=True,exist_ok=True)
    written=0
    for record in records:
        record=dict(record);record.setdefault('created_at',datetime.now(timezone.utc).isoformat())
        if record.get('mode') not in {'live','replay'}:raise ValueError('Forecast mode must be live or replay')
        probs=np.array(record['probabilities'],dtype=float)
        if len(probs)!=3 or not np.isfinite(probs).all() or (probs<0).any() or abs(probs.sum()-1)>1e-6:raise ValueError('Invalid outcome distribution')
        if utc_naive(record['as_of'])>=utc_naive(record['kickoff']):raise ValueError('Forecast cutoff must precede kickoff')
        identity='|'.join(str(record.get(k,'')) for k in ['fixture_id','model_run_id','as_of','mode'])
        path=directory/(hashlib.sha256(identity.encode()).hexdigest()+'.json')
        if path.exists():
            existing=json.loads(path.read_text())
            if existing['probabilities']!=record['probabilities']:raise FileExistsError('Refusing to rewrite an existing forecast')
            continue
        atomic_json(path,record);written+=1
    return written

def evaluate_forecasts(root,results,model_run_id=None):
    results={str(r['fixture_id']):r for r in results};groups={'live':[],'replay':[]};pending=0;rejected=0
    for path in (Path(root)/'forecasts').glob('*.json'):
        forecast=json.loads(path.read_text());result=results.get(str(forecast['fixture_id']))
        if model_run_id is not None and forecast.get('model_run_id')!=model_run_id:continue
        if not result or not result.get('finished'):pending+=1;continue
        cutoff=utc_naive(forecast['as_of']);kickoff=utc_naive(result['kickoff'])
        if cutoff>=kickoff:rejected+=1;continue
        if forecast['mode']=='live':
            created=pd.Timestamp(forecast['created_at'])
            if created.tzinfo:created=created.tz_convert('UTC').tz_localize(None)
            when=kickoff.tz_convert('UTC').tz_localize(None) if kickoff.tzinfo else kickoff
            if created>=when:rejected+=1;continue
        truth=0 if result['home_goals']>result['away_goals'] else (2 if result['home_goals']<result['away_goals'] else 1)
        probabilities=np.array(forecast['probabilities'],dtype=float)
        groups[forecast['mode']].append({'log_loss':float(-np.log(max(probabilities[truth],1e-12))),'brier':float(((probabilities-np.eye(3)[truth])**2).sum()),'correct':int(probabilities.argmax()==truth)})
    report={'pending':pending,'rejected_invalid_timing':rejected}
    for mode,rows in groups.items():
        report[mode]={'n':len(rows),'log_loss':float(np.mean([r['log_loss'] for r in rows])) if rows else None,'brier':float(np.mean([r['brier'] for r in rows])) if rows else None,'accuracy':float(np.mean([r['correct'] for r in rows])) if rows else None}
    atomic_json(Path(root)/'forecast_report.json',report)
    return report
