"""Independent UCL collection, temporal model and 36-team competition forecast.

ESPN's public scoreboard is an undocumented, best-effort source. Calendar-year
requests keep collection bounded (four requests per weekly run, no match fanout).
Provider IDs are retained; names are never fuzzy-joined to domestic teams.
"""
from collections import Counter
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

import joblib
import numpy as np
import pandas as pd
import requests

from .data import atomic_json
from .features import build_features, match_rows
from .models import predict_rows, score_distribution, train_and_evaluate
from .cups import tie_winner

SOURCE = 'https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard'
RULES = 'https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-19-Draw-system-knockout-phase-Online'
STAGES = {'league-phase', 'group-stage', 'round-of-16', 'quarterfinals',
          'semifinals', 'final', 'knockout-round-playoffs'}


def fetch_calendar(cache, year, now=None):
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    path = cache / f'ucl-espn-{year}.bin'
    receipt = path.with_suffix('.json')
    now = time.time() if now is None else now
    # Reuse successful inspections made in the owner's Colab as well.
    age = now - path.stat().st_mtime if path.exists() else float('inf')
    current_year = datetime.fromtimestamp(now, timezone.utc).year
    if path.exists() and (year < current_year or age < 6 * 86400):
        raw = path.read_bytes()
    else:
        previous = json.loads(receipt.read_text()) if receipt.exists() else {}
        if now - previous.get('attempted_at', 0) < 3600:
            raise RuntimeError('UCL source cooldown; keep previous approved projection')
        url = f'{SOURCE}?dates={int(year)}&limit=1000'
        atomic_json(receipt, {'url': url, 'attempted_at': now})
        with requests.get(url, timeout=(15, 60), stream=True,
                          headers={'User-Agent': 'PitchOps/0.7 personal academic research'}) as response:
            response.raise_for_status(); chunks = []; size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 8_000_000: raise ValueError('UCL source exceeds download bound')
                chunks.append(chunk)
        raw = b''.join(chunks)
        body = json.loads(raw)
        if not isinstance(body.get('events'), list) or len(body['events']) >= 1000:
            raise ValueError('UCL source missing or possibly truncated')
        temporary = path.with_suffix('.tmp'); temporary.write_bytes(raw); temporary.replace(path)
        atomic_json(receipt, {'url': url, 'attempted_at': now, 'retrieved_at': now,
                              'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    body = json.loads(raw)
    if not isinstance(body.get('events'), list) or len(body['events']) >= 1000:
        raise ValueError('Invalid or truncated cached UCL response')
    return body


def normalize_events(bodies, as_of):
    cutoff = pd.Timestamp(as_of, tz='UTC') if pd.Timestamp(as_of).tzinfo is None else pd.Timestamp(as_of).tz_convert('UTC')
    seen = {}; teams = {}; rows = []; fixtures = []; excluded = Counter()
    for body in bodies:
        for event in body['events']:
            identity = str(event['id'])
            if identity in seen:
                if seen[identity] != event: raise ValueError('Conflicting duplicate UCL fixture ID')
                continue
            seen[identity] = event
            stage = event.get('season', {}).get('slug')
            if stage not in STAGES: continue
            competition = event['competitions'][0]
            sides = {item['homeAway']: item for item in competition['competitors']}
            if set(sides) != {'home', 'away'}: raise ValueError('Invalid UCL home/away identity')
            home, away = sides['home'], sides['away']
            if home['id'] == away['id']: raise ValueError('UCL self fixture')
            for side in [home, away]:
                team = side['team']; key = str(team['id'])
                # One canonical current display name per source ID, checked below.
                teams[key] = {'id': key, 'name': team['displayName'], 'image_url': team.get('logo'),
                              'source_url': 'https://www.espn.com/soccer/team/_/id/' + key,
                              'credit': 'ESPN / respective rights holders'}
            when = pd.Timestamp(event['date']).tz_convert('UTC')
            status = competition.get('status', event.get('status', {}))
            finished = bool(status.get('type', {}).get('completed')) and when < cutoff
            regulation = status.get('period') == 2 and status.get('type', {}).get('name') == 'STATUS_FULL_TIME'
            goals = [int(home['score']), int(away['score'])] if finished else None
            if goals and (min(goals) < 0 or max(goals) > 30): raise ValueError('Invalid UCL score')
            season = int(event['season']['year'])
            fixture = {'id': identity, 'date': str(when.isoformat()), 'season': season,
                       'stage': stage, 'home_id': str(home['id']), 'away_id': str(away['id']),
                       'status': 'completed' if finished else status.get('type', {}).get('state', 'pre'),
                       'score': goals, 'regulation': regulation,
                       'venue': competition.get('venue', {}).get('fullName')}
            fixtures.append(fixture)
            if not finished: continue
            if not regulation:
                excluded['extra_time_or_unverified_regulation'] += 1; continue
            row = {'id': identity, 'date': when.tz_localize(None).normalize(),
                   'league': 'UCL', 'season': str(season), 'home': str(home['id']),
                   'away': str(away['id']), 'hg': goals[0], 'ag': goals[1]}
            for side, prefix in [(home, 'h'), (away, 'a')]:
                stats = {v['name']: v.get('displayValue') for v in side.get('statistics', [])}
                for suffix, field in [('c', 'wonCorners'), ('s', 'totalShots')]:
                    value = stats.get(field)
                    row[prefix + suffix] = float(value) if value is not None else float('nan')
                    if value is not None and not 0 <= float(value) <= 100: raise ValueError('Invalid UCL count label')
            rows.append(row)
    names = [t['name'] for t in teams.values()]
    if len(names) != len(set(names)): raise ValueError('Ambiguous UCL source display names')
    for fixture in fixtures:
        fixture.update(home=teams[fixture['home_id']]['name'], away=teams[fixture['away_id']]['name'])
    frame = pd.DataFrame(rows).sort_values(['date', 'id']).reset_index(drop=True) if rows else pd.DataFrame()
    return frame, sorted(fixtures, key=lambda f: (f['date'], f['id'])), teams, dict(excluded)


def validate_league_phase(fixtures):
    phase = [f for f in fixtures if f['stage'] == 'league-phase']
    teams = sorted({f[k] for f in phase for k in ['home', 'away']})
    if len(teams) != 36 or len(phase) != 144:
        raise ValueError('UCL requires all 36 teams and 144 published league-phase fixtures')
    if len({f['id'] for f in phase}) != 144: raise ValueError('Duplicate UCL fixture ID')
    if len({frozenset([f['home'], f['away']]) for f in phase}) != 144:
        raise ValueError('UCL league-phase opponents must be distinct')
    for team in teams:
        if sum(f['home'] == team for f in phase) != 4 or sum(f['away'] == team for f in phase) != 4:
            raise ValueError('UCL needs four home and four away games per team')
    return teams, phase


def simulate_champions(fixtures, forecasts, simulations=5000, seed=42):
    """League-phase outlook only, with a legal random future knockout draw.

    Once a concrete knockout fixture is published, withhold this pre-draw race
    rather than ignore the draw/results. Match forecasts/calendar remain usable.
    """
    if not 1 <= simulations <= 20000: raise ValueError('UCL simulations outside supported bounds')
    teams, phase = validate_league_phase(fixtures); n = len(teams)
    if any(f['stage'] != 'league-phase' for f in fixtures):
        return {'status': 'awaiting_knockout_conditioning', 'simulations': 0, 'table': [],
                'reason': 'Đã có lịch vòng knock-out. Tạm dừng xác suất mùa giải trước bốc thăm; dự báo trận và lịch vẫn dùng được.'}
    index = {t: i for i, t in enumerate(teams)}; rng = np.random.default_rng(seed)
    # points, GD, GF, away GF, wins, away wins; opponent totals calculated below.
    base = np.zeros((n, 6), dtype=int); played = np.zeros(n, dtype=int)
    values = np.zeros((simulations, n, 6), dtype=int); adjacency = np.zeros((n, n), dtype=int)
    remaining = 0
    def add(target, h, a, hg, ag):
        target[..., h, 0] += 3 * (hg > ag) + (hg == ag); target[..., a, 0] += 3 * (ag > hg) + (hg == ag)
        target[..., h, 1] += hg-ag; target[..., a, 1] += ag-hg
        target[..., h, 2] += hg; target[..., a, 2] += ag; target[..., a, 3] += ag
        target[..., h, 4] += hg > ag; target[..., a, 4] += ag > hg; target[..., a, 5] += ag > hg
    for f in phase:
        h, a = index[f['home']], index[f['away']]; adjacency[h, a] = adjacency[a, h] = 1
        if f['status'] == 'completed':
            if not f['regulation']: raise ValueError('League phase must have verified 90-minute scores')
            add(base, h, a, *f['score']); played[h] += 1; played[a] += 1
        else:
            remaining += 1; mu = forecasts[f['home']+'|'+f['away']]['goals']
            add(values, h, a, rng.poisson(mu[0], simulations), rng.poisson(mu[1], simulations))
    values += base
    opponent = values[:, :, :3].transpose(0, 2, 1) @ adjacency.T
    # lexsort's last key is primary; random is only the unresolved final fallback.
    keys = [rng.random((simulations, n)), -opponent[:, 2], -opponent[:, 1], -opponent[:, 0]]
    keys += [-values[:, :, i] for i in [5, 4, 3, 2, 1, 0]]
    order = np.lexsort(tuple(keys), axis=1)
    counts = {k: np.zeros(n) for k in ['top8', 'top24', 'round16', 'quarterfinal', 'semifinal', 'final', 'title']}
    means = {(h, a): forecasts[h+'|'+a]['goals'] for h in teams for a in teams if h != a}
    def win(a, b, slot_a, slot_b, final=False):
        if final:
            mu = ((means[(a,b)][0]+means[(b,a)][1])/2, (means[(a,b)][1]+means[(b,a)][0])/2)
            return tie_winner(a, b, *mu, rng)
        # Better inherited league-phase slot hosts second leg; no away-goal rule.
        first, second = (b, a) if slot_a < slot_b else (a, b)
        return tie_winner(first, second, *means[(first, second)], rng, legs=2, reverse_means=means[(second, first)])
    for ranked in order:
        counts['top8'][ranked[:8]] += 1; counts['top24'][ranked[:24]] += 1
        slots = {}
        for high, low, direct in [(9,23,7), (11,21,5), (13,19,3), (15,17,1)]:
            seeded = rng.permutation([high,high+1]); unseeded = rng.permutation([low,low+1]); direct_pair = rng.permutation([direct,direct+1])
            for hs, ls, ds in zip(seeded, unseeded, direct_pair):
                a, b = teams[ranked[hs-1]], teams[ranked[ls-1]]
                opponent_name = win(a, b, hs, ls)
                top = teams[ranked[ds-1]]
                counts['round16'][index[top]] += 1; counts['round16'][index[opponent_name]] += 1
                slots[int(ds)] = (win(top, opponent_name, int(ds), min(hs,ls)), int(ds))
        # Opposite halves for each adjacent seeded rank pair (Annex B).
        alive = [slots[x] for x in [1,7,5,3,4,6,8,2]]
        for team, _ in alive: counts['quarterfinal'][index[team]] += 1
        for target in ['semifinal', 'final', 'title']:
            following = []
            for j in range(0, len(alive), 2):
                (a,sa),(b,sb) = alive[j:j+2]
                winner = win(a,b,sa,sb,final=target=='title')
                following.append((winner,min(sa,sb))); counts[target][index[winner]] += 1
            alive = following
    rows = [{'team': t, 'played': int(played[i]), 'points': int(base[i,0]), 'gd': int(base[i,1]),
             'expected_points': float(values[:,i,0].mean()),
             'points_p10': float(np.quantile(values[:,i,0], .1)), 'points_p90': float(np.quantile(values[:,i,0], .9)),
             **{k: float(v[i]/simulations) for k,v in counts.items()}} for i,t in enumerate(teams)]
    rows.sort(key=lambda r: -r['title'])
    return {'status':'ready', 'format':'ucl-league-phase-36', 'simulations':simulations,
            'remaining_matches':remaining, 'table':rows, 'rules_url':RULES,
            'assumptions': ['144 trận vòng phân hạng theo lịch nguồn; 8 đối thủ, 4 sân nhà/4 sân khách.',
                'Top 8 vào thẳng vòng 16; hạng 9–24 đá playoff, hạng 25–36 bị loại.',
                'Mô phỏng bốc thăm hợp lệ theo cặp thứ hạng và nhánh cố định; chưa phải kết quả bốc thăm chính thức.',
                'Phân hạng: điểm, hiệu số, bàn thắng, bàn sân khách, số thắng, thắng sân khách, tổng điểm/hiệu số/bàn của đối thủ; hòa tiếp thì ngẫu nhiên do thiếu điểm kỷ luật/hệ số CLB.',
                'Hai lượt từ playoff đến bán kết, không luật bàn sân khách. Slot hạt giống được kế thừa; chung kết sân trung lập.',
                'Hiệp phụ Poisson 1/3 kỳ vọng 90 phút, luân lưu 50/50; sức mạnh cố định.']}


def run_champions(root, as_of=None, simulations=5000):
    root = Path(root); cutoff = pd.Timestamp(as_of or datetime.now(timezone.utc).date()).normalize()
    start_year = cutoff.year if cutoff.month >= 7 else cutoff.year-1
    bodies = [fetch_calendar(root/'data'/'bronze', year) for year in range(start_year-2, start_year+2)]
    matches, fixtures, identities, excluded = normalize_events(bodies, cutoff)
    if len(matches) < 300: raise ValueError('Too few verified UCL regulation-time training matches')
    current = [f for f in fixtures if f['season'] == start_year]
    teams, _ = validate_league_phase(current)
    features, state = build_features(matches)
    models, report = train_and_evaluate(features)
    gate = {'test_matches':report['test']['matches'], 'test_log_loss':report['test']['log_loss'],
            'baseline_log_loss':report['test_baseline']['log_loss']}
    gate['approved'] = bool(gate['test_matches'] >= 60 and np.isfinite(gate['test_log_loss'])
                            and gate['test_log_loss'] <= gate['baseline_log_loss'] * 1.05)
    if not gate['approved']: raise ValueError('Independent UCL temporal quality gate rejected candidate')
    by_name = {v['name']:k for k,v in identities.items()}
    pairs = [(h,a) for h in teams for a in teams if h != a]
    frame = pd.DataFrame([r for h,a in pairs for r in match_rows(by_name[h],by_name[a],'UCL',cutoff,state)])
    predictions = predict_rows(models, frame); lookup = {}
    for i,(home,away) in enumerate(pairs):
        mu = predictions['goals'][2*i:2*i+2]; result = score_distribution(*mu); result['goals'] = mu
        for target in ['corners','shots']: result[target] = predictions[target][2*i:2*i+2] if predictions[target] else None
        lookup[home+'|'+away] = result
    race = simulate_champions(current, lookup, simulations=simulations)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    canonical = matches.to_csv(index=False).encode(); digest = hashlib.sha256(canonical).hexdigest()
    try: commit = subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError): commit = 'uncommitted'
    meta = {'run_id':'ucl-'+stamp, 'created_at':datetime.now(timezone.utc).isoformat(),
            'training_from':str(matches.date.min().date()), 'training_through':str(matches.date.max().date()),
            'forecast_date':str(cutoff.date()), 'matches':len(matches), 'source':'ESPN public scoreboard',
            'source_url':SOURCE, 'code_commit':commit, 'data_sha256':digest, 'quality_gate':gate,
            'excluded':excluded, 'label_scope':'Verified regulation-time FT only; extra-time/shootout games excluded from training.'}
    observed = [f for f in current if f['status']=='completed']
    league = {'name':'UEFA Champions League', 'season':f'{start_year%100:02d}{(start_year+1)%100:02d}',
              'format':'ucl-league-phase-36', 'teams':teams, 'forecasts':lookup, 'race':race,
              'fixtures':current, 'metrics':report, 'meta':meta, 'matches':len(observed),
              'last_result':max((f['date'][:10] for f in observed),default=None),
              'sparse_teams':[t for t in teams if len(state.get(('UCL',by_name[t]),[]))<5]}
    media = {'leagues':{'UCL':{'image_url':bodies[-2]['leagues'][0].get('logos',[{}])[0].get('href')}},
             'teams':{'UCL|'+t:identities[by_name[t]] for t in teams}}
    run_dir = root/'artifacts'/'ucl'/meta['run_id']; run_dir.mkdir(parents=True,exist_ok=False)
    joblib.dump({'models':models,'state':state,'meta':meta},run_dir/'model.joblib')
    atomic_json(run_dir/'projection.json',{'league':league,'media':media})
    atomic_json(root/'artifacts'/'ucl'/'latest.json',{'run_id':meta['run_id']})
    return league, media, run_dir


def attach_champions(payload, root, **kwargs):
    """Train independently and attach projections; the caller owns publication."""
    league, artwork, directory = run_champions(root, **kwargs)
    payload['leagues']['UCL'] = league
    media = payload.setdefault('media', {})
    for key in ['leagues','teams']: media.setdefault(key, {}).update(artwork[key])
    return directory


def enrich_champions(root, **kwargs):
    """Save an immutable dashboard view while preserving the domestic champion."""
    from .storage import latest_dashboard
    from .dashboard import render_dashboard
    root = Path(root); payload, previous = latest_dashboard(root)
    payload = copy.deepcopy(payload)
    attach_champions(payload, root, **kwargs)
    model_id = payload['meta']['run_id']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    view_id = model_id+'-ucl-'+stamp; view = root/'artifacts'/'views'/view_id
    view.mkdir(parents=True, exist_ok=False)
    render_dashboard(payload, view/'dashboard.html')
    atomic_json(view/'snapshot.json', payload)
    atomic_json(view/'source_run.json', {'model_run_id':model_id, 'source_view_id':previous.name,
                                       'ucl_run_id':payload['leagues']['UCL']['meta']['run_id']})
    atomic_json(root/'artifacts'/'latest_view.json', {'model_run_id':model_id,'view_id':view_id})
    return payload, view
