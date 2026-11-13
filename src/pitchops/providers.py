"""Opt-in licensed provider bridge. Never discovers or purchases credentials.

Coverage is provider/season/plan dependent. This adapter returns namespaced raw
records for explicit mapping, not silent joins to football-data/StatsBomb names.
"""
import hashlib
import json
from pathlib import Path
import time
import requests
from .data import atomic_json

class APIFootball:
    BASE='https://v3.football.api-sports.io'
    ENDPOINTS={'leagues','fixtures','fixtures/statistics','fixtures/players','players/squads','players'}
    def __init__(self,root,api_key,daily_budget=50):
        if not api_key:raise ValueError('Supply your own API_FOOTBALL_KEY in Colab Secrets')
        if not 1<=daily_budget<=100:raise ValueError('Choose an explicit daily request budget from 1 to 100')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self._key=api_key;self.budget=daily_budget

    def get(self,endpoint,params=None,ttl_hours=24):
        if endpoint not in self.ENDPOINTS:raise ValueError('Endpoint not allowed')
        params=params or {}
        if any(str(k).lower() in {'key','api_key','token','x-apisports-key'} for k in params):raise ValueError('Credentials belong in headers, not cache keys')
        identity=json.dumps([endpoint,params],sort_keys=True,separators=(',',':'))
        key=hashlib.sha256(identity.encode()).hexdigest();path=self.root/(key+'.json');now=time.time()
        if path.exists() and now-path.stat().st_mtime<ttl_hours*3600:return json.loads(path.read_text())
        ledger_path=self.root/'request_ledger.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        if sum(now-r['time']<86400 for r in ledger)>=self.budget:raise RuntimeError('API-Football local daily budget reached')
        ledger.append({'time':now,'endpoint':endpoint,'params':params});atomic_json(ledger_path,ledger)
        response=requests.get(self.BASE+'/'+endpoint,params=params,headers={'x-apisports-key':self._key},timeout=(10,60))
        response.raise_for_status();body=response.json()
        if body.get('errors'):raise RuntimeError('Provider rejected request: check your subscription/coverage/quota in the provider console')
        if not isinstance(body.get('response'),list):raise ValueError('Invalid provider response')
        atomic_json(path,body);return body

    def coverage(self,league,season):
        body=self.get('leagues',{'id':int(league),'season':int(season)},ttl_hours=168)
        rows=[]
        for entry in body['response']:
            for item in entry.get('seasons',[]):
                if item.get('year')==int(season):rows.append({'provider':'api-football','league_id':'api-football:'+str(league),'season':season,'name':entry['league']['name'],'logo_url':entry['league'].get('logo'),'coverage':item.get('coverage',{})})
        return rows

    def fixtures(self,league,season,page=None):
        # Fixtures uses no implicit recursive pagination or per-player fanout.
        params={'league':int(league),'season':int(season)}
        if page is not None:raise ValueError('Fixtures endpoint does not take player-style pagination')
        return self.get('fixtures',params)['response']

    def statistics(self,fixture):return self.get('fixtures/statistics',{'fixture':int(fixture)})['response']
    def player_stats(self,fixture):return self.get('fixtures/players',{'fixture':int(fixture)})['response']
    def squad(self,team):return self.get('players/squads',{'team':int(team)},ttl_hours=168)['response']
    def players_page(self,league,season,page=1):
        return self.get('players',{'league':int(league),'season':int(season),'page':int(page)})


def import_player_logs(path):
    """User-controlled CSV path to scorer/XI modules, no network access.

    IDs must be namespaced. Rating source and observation timestamps stay in the
    contract so official provider ratings are not mixed with PitchOps Index.
    """
    import pandas as pd
    frame=pd.read_csv(path,dtype={'player_id':str})
    required={'player_id','player','team','date','minutes','goals','rating','rating_source','position'}
    if not required.issubset(frame):raise ValueError('Missing player columns: '+str(sorted(required-set(frame))))
    if frame.empty or frame[list(required)].isna().any().any():raise ValueError('Empty/incomplete player logs')
    if not frame.player_id.str.contains(':',regex=False).all():raise ValueError('Player IDs must be namespaced')
    frame['date']=pd.to_datetime(frame.date,utc=True).dt.tz_localize(None)
    for name,upper in [('minutes',130),('goals',30),('rating',10)]:
        frame[name]=pd.to_numeric(frame[name],errors='raise')
        if not frame[name].between(0,upper).all():raise ValueError('Invalid '+name)
    if frame.duplicated(['player_id','date','team']).any():raise ValueError('Duplicate player observation')
    return frame.sort_values(['date','player_id']).reset_index(drop=True)
