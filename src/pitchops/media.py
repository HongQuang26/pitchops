"""Verified provider IDs, team badges and player cutouts for research dashboards.

Artwork is cosmetic metadata, never a training feature. No fuzzy player joins.
API keys remain server-side; remote images are optional and have local fallbacks.
"""
from __future__ import annotations
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlencode, urlparse, quote
import requests
from .data import atomic_json

LEAGUE_IDS = {'E0': '4328', 'D1': '4331', 'I1': '4332', 'F1': '4334', 'SP1': '4335'}
ALIASES = {
    'Man City': ['Manchester City'], 'Man United': ['Manchester United'],
    "Nott'm Forest": ['Nottingham Forest'], 'Wolves': ['Wolverhampton Wanderers'],
    'Tottenham': ['Tottenham Hotspur'], 'Newcastle': ['Newcastle United'],
    'West Ham': ['West Ham United'], 'Leeds': ['Leeds United'],
    'Brighton': ['Brighton and Hove Albion', 'Brighton & Hove Albion'],
    'Hull': ['Hull City'], 'Coventry': ['Coventry City'], 'Ipswich': ['Ipswich Town'],
    'Bayern Munich': ['Bayern München', 'FC Bayern München', 'Bayern Munich'],
    'Dortmund': ['Borussia Dortmund'], 'Ein Frankfurt': ['Eintracht Frankfurt'],
    "M'gladbach": ['Borussia Mönchengladbach', 'Borussia Monchengladbach'],
    'FC Koln': ['1. FC Köln', 'FC Cologne', 'FC Köln'],
    'Leverkusen': ['Bayer Leverkusen', 'Bayer 04 Leverkusen'],
    'Mainz': ['Mainz 05', '1. FSV Mainz 05'], 'Schalke 04': ['FC Schalke 04'],
    'Elversberg': ['SV Elversberg'], 'Paderborn': ['SC Paderborn 07'],
    'St Pauli': ['FC St. Pauli'], 'RB Leipzig': ['RasenBallsport Leipzig'],
    'Ath Madrid': ['Atletico Madrid', 'Atlético de Madrid'],
    'Ath Bilbao': ['Athletic Bilbao', 'Athletic Club'], 'Betis': ['Real Betis'],
    'Sociedad': ['Real Sociedad'], 'Celta': ['Celta Vigo', 'RC Celta de Vigo'],
    'Vallecano': ['Rayo Vallecano'], 'Alaves': ['Deportivo Alavés'],
    'Espanol': ['Espanyol', 'RCD Espanyol'], 'Barcelona': ['FC Barcelona'],
    'Paris SG': ['Paris Saint-Germain', 'Paris Saint Germain'],
    'St Etienne': ['Saint-Etienne', 'AS Saint-Étienne'],
    'Inter': ['Inter Milan', 'Internazionale'], 'Milan': ['AC Milan'],
    'Verona': ['Hellas Verona'], 'Roma': ['AS Roma'],
    'Stuttgart': ['VfB Stuttgart'], 'Union Berlin': ['1. FC Union Berlin'],
    'Werder Bremen': ['SV Werder Bremen'], 'Sunderland': ['Sunderland AFC'],
    'Monaco': ['AS Monaco'], 'Nice': ['OGC Nice'],
    'Rennes': ['Stade Rennais FC', 'Stade Rennes'],
    'Strasbourg': ['RC Strasbourg Alsace'], 'Troyes': ['ESTAC Troyes'],
    'Lazio': ['SS Lazio'], 'Lecce': ['US Lecce'], 'Monza': ['AC Monza'],
    'Napoli': ['SSC Napoli'], 'Parma': ['Parma Calcio 1913'],
    'Sassuolo': ['US Sassuolo', 'US Sassuolo Calcio'], 'Udinese': ['Udinese Calcio'],
    'La Coruna': ['Deportivo La Coruña', 'RC Deportivo La Coruña', 'Deportivo de La Coruña'],
    'Osasuna': ['CA Osasuna'], 'Santander': ['Racing Santander', 'Racing de Santander'],
}
ALIASES['Betis'] += ['Real Betis Balompie', 'Real Betis Balompié']
IMAGE_HOSTS = {'r2.thesportsdb.com', 'www.thesportsdb.com', 'raw.githubusercontent.com'}

def normalized(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', value)

def names_for(name):
    variants = [name, *ALIASES.get(name, [])]
    return {normalized(x) for value in variants for x in [value, 'FC '+value, value+' FC', value+' CF']}

def safe_image_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname not in IMAGE_HOSTS or parsed.username or parsed.password:
        return None
    return value

def resolve_team(name, records):
    wanted = names_for(name)
    matches = []
    for record in records:
        alternatives = [record.get('strTeam', ''), *str(record.get('strTeamAlternate') or '').split(',')]
        if wanted.intersection(normalized(x) for x in alternatives if x.strip()):
            matches.append(record)
    unique = {str(row['idTeam']): row for row in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None

class MetadataClient:
    def __init__(self, root, api_key=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get('SPORTSDB_API_KEY', '123')
        self.last_request = 0.0

    def get(self, endpoint, params=None, ttl_days=7):
        # Public method identity is the cache key; a premium key is never saved.
        identity = endpoint + '?' + urlencode(params or {}, doseq=True)
        path = self.root / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
        if path.exists() and time.time()-path.stat().st_mtime < ttl_days*86400:
            return json.loads(path.read_text())
        delay = 2.1 - (time.monotonic()-self.last_request)
        if delay > 0:
            time.sleep(delay)  # <= 30 requests/min; no keepalive or long blocking sleep
        if endpoint.startswith('https://api.github.com/'):
            url = endpoint
        else:
            if not re.fullmatch(r'[a-z_]+\.php', endpoint):
                raise ValueError('Invalid metadata endpoint')
            url = f'https://www.thesportsdb.com/api/v1/json/{self.api_key}/{endpoint}'
        self.last_request = time.monotonic()
        response = requests.get(url, params=params, timeout=(10, 35), headers={'User-Agent': 'PitchOps academic dashboard/0.2'})
        if response.status_code != 200:
            if path.exists():
                return json.loads(path.read_text())
            raise RuntimeError(f'Metadata endpoint unavailable: HTTP {response.status_code}; no bypass/retry')
        result = response.json()
        atomic_json(path, result)
        return result

def logo_from_index(name, tree):
    matches = [row['path'] for row in tree if row.get('type') == 'blob' and row['path'].startswith('logos/') and row['path'].lower().endswith('.png') and normalized(Path(row['path']).stem) in names_for(name)]
    return matches[0] if len(matches) == 1 else None

def player_record(row, league, team_name):
    # Namespaced provider ID prevents accidental cross-provider face matching.
    return {'id': 'thesportsdb:' + str(row['idPlayer']), 'provider_id': str(row['idPlayer']), 'name': row.get('strPlayer') or 'Unknown', 'team': team_name, 'league': league, 'position': row.get('strPosition') or 'Unknown', 'number': row.get('strNumber') or '', 'nationality': row.get('strNationality') or '', 'height': row.get('strHeight') or '', 'born': row.get('dateBorn') or '', 'image_url': safe_image_url(row.get('strCutout')) or safe_image_url(row.get('strThumb')), 'image_kind': 'cutout' if safe_image_url(row.get('strCutout')) else 'portrait', 'source_url': 'https://www.thesportsdb.com/player/' + str(row['idPlayer']), 'credit': row.get('strCreativeCommonsAttribution') or 'TheSportsDB; rights remain with the original image owner', 'creative_commons_flag': row.get('strCreativeCommons') or 'Unknown', 'external_ids': {'espn': row.get('idESPN'), 'wikidata': row.get('idWikidata'), 'api_football': row.get('idAPIfootball')}}

def is_player_position(value):
    return not bool(re.search(r'manager|coach|president|director|owner|staff|physio', str(value or ''), flags=re.I))

def cached_image(url, root):
    url = safe_image_url(url)
    if not url:
        return None
    # Use the provider's documented small preview, without editing artwork.
    preview = url + '/small' if urlparse(url).hostname.endswith('thesportsdb.com') else url
    key = hashlib.sha256(preview.encode()).hexdigest()
    path, meta = Path(root)/(key+'.bin'), Path(root)/(key+'.json')
    try:
        if path.exists() and meta.exists():
            mime = json.loads(meta.read_text())['mime']
            blob = path.read_bytes()
        else:
            with requests.get(preview, stream=True, timeout=(10,25), allow_redirects=False) as response:
                if response.status_code != 200:
                    return None
                mime = response.headers.get('Content-Type','').split(';')[0]
                if mime not in {'image/png','image/jpeg','image/webp'}:
                    return None
                blob = b''
                for block in response.iter_content(32768):
                    blob += block
                    if len(blob) > 400_000:
                        return None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            atomic_json(meta, {'url': preview, 'mime': mime, 'sha256': hashlib.sha256(blob).hexdigest()})
        return 'data:'+mime+';base64,'+base64.b64encode(blob).decode()
    except (requests.RequestException, OSError, ValueError):
        return None

def sync_media(root, payload, api_key=None, max_rosters=50, embed_images=True, max_embed_players=48, refresh_rosters=True):
    root = Path(root)
    client = MetadataClient(root/'api', api_key)
    catalog = {'source': 'TheSportsDB', 'retrieved_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), 'leagues': {}, 'teams': {}, 'players': [], 'warnings': [], 'coverage': {}, 'partial_rosters': True, 'credits': [{'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com', 'terms': 'https://www.thesportsdb.com/docs_terms_of_use.php'}, {'name': 'Football Logos by luukhopman', 'url': 'https://github.com/luukhopman/football-logos', 'terms': 'Third-party club trademarks; no blanket image licence claimed'}]}
    roster_jobs = []
    if not refresh_rosters and (root/'catalog.json').exists():
        previous = json.loads((root/'catalog.json').read_text())
        catalog['players'] = [p for p in previous.get('players',[]) if is_player_position(p.get('position'))]
        catalog['player_directory_updated_at'] = previous.get('player_directory_updated_at',previous.get('retrieved_at'))
    for code, league in payload['leagues'].items():
        try:
            details = client.get('lookupleague.php', {'id': LEAGUE_IDS[code]}, ttl_days=30).get('leagues') or []
            if not details:
                continue
            info = details[0]
            catalog['leagues'][code] = {'id': LEAGUE_IDS[code], 'name': info.get('strLeague',league['name']), 'image_url': safe_image_url(info.get('strBadge')) or safe_image_url(info.get('strLogo')), 'source_url': 'https://www.thesportsdb.com/league/'+LEAGUE_IDS[code]}
            records = client.get('search_all_teams.php', {'l': info['strLeague'].replace(' ','_')}).get('teams') or []
            for team_name in league['teams']:
                record = resolve_team(team_name, records)
                item = {'name': team_name, 'league': code, 'image_url': None, 'provider_id': None, 'source_url': None, 'resolution': 'unresolved'}
                if record:
                    item.update({'provider_id': str(record['idTeam']), 'image_url': safe_image_url(record.get('strBadge') or record.get('strTeamBadge')), 'source_url': 'https://www.thesportsdb.com/team/'+str(record['idTeam']), 'resolution': 'exact alias within league'})
                    roster_jobs.append((code, team_name, str(record['idTeam'])))
                catalog['teams'][code+'|'+team_name] = item
            print(f'Media metadata: {league["name"]}, {len(records)} provider team records', flush=True)
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            catalog['warnings'].append(f'{code}: metadata unavailable ({type(exc).__name__})')
    unresolved = [x for x in catalog['teams'].values() if not x.get('image_url')]
    if unresolved:
        try:
            repo = client.get('https://api.github.com/repos/luukhopman/football-logos/git/trees/master', {'recursive': '1'}, ttl_days=30)
            revision = client.get('https://api.github.com/repos/luukhopman/football-logos/commits/master', ttl_days=30)['sha']
            catalog['logo_repo_commit'] = revision
            if repo.get('truncated'):
                raise ValueError('Incomplete logo index')
            for item in unresolved:
                path = logo_from_index(item['name'], repo.get('tree', []))
                if path:
                    item.update({'image_url': 'https://raw.githubusercontent.com/luukhopman/football-logos/'+revision+'/'+quote(path), 'source_url': 'https://github.com/luukhopman/football-logos', 'resolution': 'unique exact logo filename; no player identity join'})
        except (requests.RequestException, RuntimeError, ValueError, KeyError):
            catalog['warnings'].append('Secondary logo index unavailable; initial placeholders retained')
    # Prioritize popular clubs but never fabricate IDs for unmatched teams.
    priority = {'Arsenal':0,'Man City':1,'Barcelona':2,'Bayern Munich':3,'Paris SG':4,'Milan':5,'Chelsea':6,'Aston Villa':7}
    roster_jobs.sort(key=lambda x:(priority.get(x[1],100),x[0],x[1]))
    for i,(league, team, team_id) in enumerate(roster_jobs[:max_rosters] if refresh_rosters else []):
        try:
            rows = client.get('lookup_all_players.php', {'id':team_id}).get('player') or []
            # Exclude managers/other sports and records belonging to another team.
            rows = [r for r in rows if r.get('idPlayer') and str(r.get('idTeam')) == team_id and r.get('strSport') == 'Soccer' and is_player_position(r.get('strPosition'))]
            catalog['players'].extend(player_record(r,league,team) for r in rows)
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            catalog['warnings'].append(team+': roster unavailable ('+reason+')')
        if i%10 == 0:
            print(f'Media rosters: {i+1}/{min(len(roster_jobs),max_rosters)}', flush=True)
    unique = {p['id']: p for p in catalog['players']}
    catalog['players'] = sorted(unique.values(), key=lambda p:(p['league'],p['team'],p['name']))
    faces = sorted([p for p in catalog['players'] if p['image_url']], key=lambda p:(priority.get(p['team'],100),p['name']))[:max_embed_players]
    image_items = [*catalog['leagues'].values(), *catalog['teams'].values(), *faces]
    if embed_images:
        with ThreadPoolExecutor(max_workers=5) as pool:
            cached = list(pool.map(lambda x: cached_image(x.get('image_url'), root/'images'), image_items))
        for item, data_uri in zip(image_items,cached):
            if data_uri:
                item['image_data'] = data_uri
    catalog['coverage'] = {'league_logos': sum(bool(x.get('image_url')) for x in catalog['leagues'].values()), 'team_logos':sum(bool(x.get('image_url')) for x in catalog['teams'].values()), 'total_teams':sum(len(x['teams']) for x in payload['leagues'].values()), 'players':len(catalog['players']), 'player_faces':sum(bool(x.get('image_url')) for x in catalog['players']), 'embedded_images':sum(bool(x.get('image_data')) for x in image_items), 'rosters_requested':min(len(roster_jobs),max_rosters) if refresh_rosters else 0, 'free_api_limit_note':'The free provider caps teams/players returned per call. This is a partial directory, not verified full squads.'}
    atomic_json(root/'catalog.json', catalog)
    return catalog

def enrich_dashboard(root, api_key=None, max_rosters=50, embed_images=True, refresh_rosters=True):
    from .storage import latest_run
    from .dashboard import render_dashboard
    payload, model_run_dir = latest_run(root)
    catalog = sync_media(Path(root)/'data'/'media', payload, api_key, max_rosters, embed_images, refresh_rosters=refresh_rosters)
    payload['media'] = catalog
    payload.setdefault('meta',{})['media_updated_at'] = catalog['retrieved_at']
    payload['meta']['model_run_directory'] = str(model_run_dir)
    payload['meta']['workspace'] = str(Path(root))
    payload['meta']['persistent_drive'] = str(Path(root)).startswith('/content/drive/MyDrive/')
    import subprocess
    try:
        payload['meta']['view_code_commit'] = subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        payload['meta']['view_code_commit'] = 'uncommitted'
    from datetime import datetime, timezone
    view_id = model_run_dir.name+'-media-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir = Path(root)/'artifacts'/'views'/view_id
    run_dir.mkdir(parents=True, exist_ok=False)
    atomic_json(run_dir/'snapshot.json', payload)
    render_dashboard(payload,run_dir/'dashboard.html')
    atomic_json(run_dir/'media_coverage.json', catalog['coverage'])
    atomic_json(run_dir/'source_run.json', {'model_run_id':model_run_dir.name, 'media_updated_at':catalog['retrieved_at']})
    atomic_json(Path(root)/'artifacts'/'latest_view.json', {'model_run_id':model_run_dir.name, 'view_id':view_id})
    print(json.dumps(catalog['coverage'],ensure_ascii=False,indent=2),flush=True)
    return payload, run_dir
