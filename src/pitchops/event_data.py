"""Normalize StatsBomb events into 90-minute match, player and spatial datasets.

Possession is an explicitly named controlled-action-duration proxy. Player
ratings are a transparent PitchOps index, not ratings supplied by StatsBomb.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .data import atomic_json
from .events import StatsBomb

COUNT_FIELDS = ['goals','shots','xg','assists','key_passes','passes','completed_passes','tackles','interceptions','recoveries','saves','turnovers','yellow','red']
GRID_SHAPE = (8,12)
SOURCE_LOGO = 'https://raw.githubusercontent.com/hudl/public-images/master/statsbomb_logo_email_new.jpg'

def position_group(position):
    text=str(position or '').lower()
    if 'goalkeeper' in text:return 'GK'
    if 'back' in text or 'defender' in text:return 'DF'
    if 'midfield' in text:return 'MF'
    if 'wing' in text or 'forward' in text or 'striker' in text:return 'FW'
    return 'MF'

def minute90(event):
    period=int(event.get('period',1))
    minute=float(event.get('minute',0))+float(event.get('second',0))/60
    if period==1:return min(max(minute,0),45)
    if period==2:return min(max(minute,45),90)
    return 90.0

def grid_index(location):
    if not isinstance(location,list) or len(location)!=2:return None
    x,y=location
    if not np.isfinite(x) or not np.isfinite(y) or not 0<=x<=120 or not 0<=y<=80:return None
    return min(int(y/10),7)*12+min(int(x/10),11)

def pitchops_rating(row):
    """Versioned, derived research label; not an official vendor/player award."""
    mins=max(float(row['minutes']),20)
    scale=90/mins
    score=6+0.80*row['goals']+0.45*row['assists']+0.08*row['key_passes']
    score+=0.007*row['completed_passes']*scale+0.045*(row['tackles']+row['interceptions'])*scale
    score+=0.055*row['saves']*scale-0.025*row['turnovers']*scale-0.16*row['yellow']-0.70*row['red']
    return float(np.clip(score,3,10))

def parse_match(match,events):
    mid=int(match['match_id']);date=pd.Timestamp(match['match_date'])
    home=match['home_team']['home_team_name'];away=match['away_team']['away_team_name']
    teams={int(match['home_team']['home_team_id']):home,int(match['away_team']['away_team_id']):away}
    players={};stats={name:defaultdict(float) for name in [home,away]};spatial=defaultdict(lambda:np.zeros(96,dtype=int))
    def ensure(pid,name,team,position='Unknown',number=None,start=0):
        key=int(pid)
        if key not in players:
            players[key]={'player_id':'statsbomb:'+str(key),'provider_id':key,'player':name,'team':team,'position':position_group(position),'position_name':position,'number':number,'start':start,'end':90.0,'started':False,**{field:0.0 for field in COUNT_FIELDS}}
        return players[key]
    for event in events:
        if event.get('type',{}).get('name')=='Starting XI':
            team=event['team']['name']
            for entry in event.get('tactics',{}).get('lineup',[]):
                p=entry['player'];row=ensure(p['id'],p['name'],team,entry.get('position',{}).get('name','Unknown'),entry.get('jersey_number'))
                row['started']=True
    own_against=any(e.get('type',{}).get('name')=='Own Goal Against' and e.get('period',1)<=2 for e in events)
    shootout={home:0,away:0}
    for event in events:
        kind=event.get('type',{}).get('name');team=event.get('team',{}).get('name')
        if team not in stats:continue
        period=int(event.get('period',1));person=event.get('player');row=None
        if period==5 and kind=='Shot' and event.get('shot',{}).get('outcome',{}).get('name')=='Goal':shootout[team]+=1
        if period>2:continue
        if person:
            row=ensure(person['id'],person['name'],team,event.get('position',{}).get('name','Unknown'),start=0)
        if kind=='Substitution':
            moment=minute90(event)
            if row:row['end']=min(row['end'],moment)
            replacement=event.get('substitution',{}).get('replacement')
            if replacement:
                new=ensure(replacement['id'],replacement['name'],team,row['position_name'] if row else 'Unknown',start=moment)
                new['start']=moment
        if kind=='Shot':
            shot=event.get('shot',{});goal=shot.get('outcome',{}).get('name')=='Goal'
            stats[team]['shots']+=1;stats[team]['goals']+=int(goal)
            if shot.get('outcome',{}).get('name') in {'Goal','Saved','Saved to Post'}:stats[team]['shots_on_target']+=1
            if row:row['shots']+=1;row['goals']+=int(goal);row['xg']+=float(shot.get('statsbomb_xg') or 0)
        if kind=='Own Goal Against':
            other=away if team==home else home;stats[other]['goals']+=1
        if kind=='Own Goal For' and not own_against:stats[team]['goals']+=1
        if kind=='Pass':
            data=event.get('pass',{});restart=data.get('type',{}).get('name')
            stats[team]['corners']+=int(restart=='Corner');stats[team]['throwins']+=int(restart=='Throw-in')
            if row:
                row['passes']+=1;row['completed_passes']+=int(not data.get('outcome'))
                row['assists']+=int(bool(data.get('goal_assist')));row['key_passes']+=int(bool(data.get('shot_assist')))
        if kind in {'Pass','Carry','Dribble'}:
            stats[team]['control_duration']+=max(0,min(float(event.get('duration') or 0),15))
        if row:
            if kind=='Duel' and event.get('duel',{}).get('type',{}).get('name')=='Tackle':row['tackles']+=1
            if kind=='Interception':row['interceptions']+=1
            if kind=='Ball Recovery' and not event.get('ball_recovery',{}).get('recovery_failure'):row['recoveries']+=1
            if kind=='Goal Keeper' and 'Saved' in event.get('goalkeeper',{}).get('type',{}).get('name',''):row['saves']+=1
            if kind in {'Dispossessed','Miscontrol'}:row['turnovers']+=1
            card=(event.get('foul_committed',{}).get('card') or event.get('bad_behaviour',{}).get('card') or {}).get('name','')
            if 'Yellow' in card:row['yellow']+=1
            if card in {'Red Card','Second Yellow'}:row['red']+=1;row['end']=min(row['end'],minute90(event))
            if kind in {'Pass','Carry','Ball Receipt*','Dribble','Shot'}:
                cell=grid_index(event.get('location'))
                if cell is not None:spatial[row['player_id']][cell]+=1
    total=stats[home]['control_duration']+stats[away]['control_duration']
    records=[]
    for row in players.values():
        row.update({'match_id':mid,'date':date,'opponent':away if row['team']==home else home,'is_home':int(row['team']==home),'minutes':max(0,min(row.pop('end')-row.pop('start'),90))})
        if row['minutes']<=0:continue
        row['rating']=pitchops_rating(row);records.append(row)
    stage=match.get('competition_stage',{}).get('name','Unknown')
    official_h,official_a=int(match['home_score']),int(match['away_score'])
    winner=home if official_h>official_a else (away if official_a>official_h else (home if shootout[home]>shootout[away] else (away if shootout[away]>shootout[home] else None)))
    game={'match_id':mid,'date':date,'home':home,'away':away,'hg':stats[home]['goals'],'ag':stats[away]['goals'],'hc':stats[home]['corners'],'ac':stats[away]['corners'],'hs':stats[home]['shots'],'as':stats[away]['shots'],'hst':stats[home]['shots_on_target'],'ast':stats[away]['shots_on_target'],'home_throwins':stats[home]['throwins'],'away_throwins':stats[away]['throwins'],'home_control':stats[home]['control_duration']/total if total else .5,'away_control':stats[away]['control_duration']/total if total else .5,'stage':stage,'official_hg':official_h,'official_ag':official_a,'winner':winner,'group_home':match['home_team'].get('home_team_group'),'group_away':match['away_team'].get('away_team_group'),'league':'SB43_106','season':'2022'}
    spatial_rows=[{'match_id':mid,'date':date,'player_id':pid,'counts':counts.tolist()} for pid,counts in spatial.items()]
    game['kickoff']=str(date.date())+'T'+match.get('kick_off','00:00:00')
    game['league']='SB'+str(match.get('competition',{}).get('competition_id',43))+'_'+str(match.get('season',{}).get('season_id',106))
    game['season']=str(match.get('season',{}).get('season_name','2022'))
    return game,records,spatial_rows

def load_event_dataset(root,competition_id=43,season_id=106,max_matches=80):
    root=Path(root);provider=StatsBomb(root/'bronze')
    # Reuse the previous top-level cache when it already holds the same provider.
    if any(root.glob('*.bin')):provider=StatsBomb(root)
    matches=provider.matches(competition_id,season_id).sort_values(['match_date','match_id'])
    if len(matches)>max_matches:raise ValueError('Competition exceeds configured event budget; choose a bounded competition or import files')
    games=[];players=[];locations=[];manifest=[]
    for index,match in enumerate(matches.to_dict('records')):
        events=provider._json('events/'+str(match['match_id']))
        game,logs,spatial=parse_match(match,events)
        games.append(game);players.extend(logs);locations.extend(spatial)
        manifest.append({'match_id':int(match['match_id']),'event_count':len(events),'sha256':hashlib.sha256(json.dumps(events,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
        if index%8==0:print(f'Normalized events {index+1}/{len(matches)}',flush=True)
    game_df=pd.DataFrame(games).sort_values(['date','match_id']).reset_index(drop=True)
    player_df=pd.DataFrame(players).sort_values(['date','match_id','player_id']).reset_index(drop=True)
    if player_df.duplicated(['match_id','player_id']).any():raise ValueError('Duplicate player match records')
    atomic_json(root/'event_manifest.json',manifest)
    return game_df,player_df,locations
