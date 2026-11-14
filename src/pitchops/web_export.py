"""Publish only derived forecasts and public artwork metadata, never ML weights/raw workbooks."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from .data import atomic_json

META_FIELDS = {'run_id','created_at','training_from','training_through','forecast_date',
    'code_commit','view_code_commit','research_code_commit','data_sha256','matches',
    'features','seed','source','calibration','status','python','sklearn','numpy','pandas'}
RESEARCH_FIELDS = {'schema','run_id','as_of','competition','source_url','source_logo',
    'matches_observed','matches_total','teams','players','player_match_rows',
    'team_players','forecasts','spatial','best_xi','cup','custom_cup',
    'future_fixtures','report','assumptions'}


def without_embedded_images(value):
    if isinstance(value,dict):
        return {key:without_embedded_images(item) for key,item in value.items()
                if key != 'image_data' and not key.startswith('_')}
    if isinstance(value,list):
        return [without_embedded_images(item) for item in value]
    return value


def public_projection(payload, gate, auxiliary=None):
    if not gate.get('approved'):
        raise ValueError('Web publication requires an approved quality gate')
    auxiliary = auxiliary or {}
    result = {
        'schema':1,
        'meta':{key:copy.deepcopy(value) for key,value in payload['meta'].items() if key in META_FIELDS},
        'metrics':copy.deepcopy(payload['metrics']),
        'quality':copy.deepcopy(payload.get('quality',{})),
        'drift':copy.deepcopy(payload.get('drift',[])),
        'leagues':{},
        'publication':{'quality_gate':copy.deepcopy(gate), 'scope':'personal/academic research',
                       'raw_match_data':False, 'model_weights':False},
    }
    for code, league in payload['leagues'].items():
        fields = {'name','season','teams','forecasts','race','matches','last_result','sparse_teams','format','fixtures','metrics','meta'}
        result['leagues'][code] = {key:copy.deepcopy(value) for key,value in league.items() if key in fields}
        if 'meta' in league:
            result['leagues'][code]['meta'] = {k:copy.deepcopy(v) for k,v in league['meta'].items() if k in META_FIELDS | {'quality_gate','source_url','excluded','label_scope'}}
    media = payload.get('media') or auxiliary.get('media')
    if media:
        result['media'] = without_embedded_images(media)
        result['media'].setdefault('coverage',{})['embedded_images'] = 0
    research = payload.get('research') or auxiliary.get('research')
    if research:
        result['research'] = without_embedded_images({key:value for key,value in research.items() if key in RESEARCH_FIELDS})
        # A historical cohort keeps its own lineage; new weekly club runs do not re-train it.
        research_code = payload['meta'].get('research_code_commit') or auxiliary.get('meta',{}).get('research_code_commit')
        if research_code:result['meta']['research_code_commit'] = research_code
    json.dumps(result, allow_nan=False)
    return result


def export_web(payload, gate, output, auxiliary=None):
    result = public_projection(payload, gate, auxiliary)
    encoded = json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    if len(encoded)>24_000_000:raise ValueError('Web snapshot exceeds bounded decoded size')
    compressed = gzip.compress(encoded,mtime=0)
    if len(compressed)>8_000_000:raise ValueError('Web snapshot exceeds download size limit')
    output = Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(compressed)
    receipt = {'schema':1,'format':'pitchops-web-gzip-v1','run_id':result['meta']['run_id'],
        'code_commit':result['meta']['code_commit'],'created_at':result['meta']['created_at'],
        'training_through':result['meta']['training_through'],'sha256':hashlib.sha256(compressed).hexdigest(),
        'bytes':len(compressed),'quality_gate':gate}
    atomic_json(output.with_suffix(output.suffix+'.manifest.json'),receipt)
    return result, receipt
