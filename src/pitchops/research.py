"""End-to-end open-data event analytics, with explicit historical replay scope."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import base64
import requests
import joblib
import numpy as np
import pandas as pd
from .advanced_models import fit_team_models,fit_player_model,predict_team,project_players,motm_probabilities,spatial_model,scorer_backtest,PNUM
from .event_data import load_event_dataset,SOURCE_LOGO
from .cups import simulate_world_cup,simulate_knockout
from .forecast_store import record_forecasts,evaluate_forecasts
from .data import atomic_json
from .storage import latest_dashboard
from .dashboard import render_dashboard

def known_future_fixtures(games,cutoff):
    """Historical replay calendar: future KO entrants only after predecessor stage ends."""
    stages={'Round of 16':'Group Stage','Quarter-finals':'Round of 16','Semi-finals':'Quarter-finals','Final':'Semi-finals','3rd Place Final':'Semi-finals'}
    output=[]
    for row in games[games.date>=cutoff].itertuples():
        prerequisite=stages.get(row.stage)
        known=row.stage=='Group Stage' or (prerequisite is not None and not games[games.stage==prerequisite].empty and games[games.stage==prerequisite].date.max()<cutoff)
        if known:output.append({'fixture_id':'statsbomb:'+str(row.match_id),'date':str(row.date.date()),'kickoff':row.kickoff,'home':row.home,'away':row.away,'stage':row.stage})
    return output

def best_xi(projected,fixtures,cutoff,days,forecasts=None):
    end=cutoff+pd.Timedelta(days=days);totals={};counts={}
    for fixture in fixtures:
        if not cutoff<=pd.Timestamp(fixture['date'])<end:continue
        for side,(home,away) in enumerate([(fixture['home'],fixture['away']),(fixture['away'],fixture['home'])]):
            adjustment=forecasts[fixture['home']+'|'+fixture['away']]['rating_adjust'][side] if forecasts else 0
            for player in projected.get(home,[]):
                pid=player['id'];counts[pid]=counts.get(pid,0)+1
                if pid not in totals:totals[pid]={**player,'projected_index_sum':0,'forecast_matches':0}
                totals[pid]['projected_index_sum']+=float(np.clip(player['rating']+adjustment,3,10))*player['appearance_probability'];totals[pid]['forecast_matches']+=1
    chosen=[]
    for position,n in [('GK',1),('DF',4),('MF',3),('FW',3)]:
        candidates=sorted([p for p in totals.values() if p['position']==position],key=lambda p:-p['projected_index_sum'])
        if len(candidates)<n:return {'status':'unavailable','reason':'Not enough known future fixtures/positions for a complete 4-3-3','players':[]}
        chosen.extend(candidates[:n])
    return {'status':'projection','days':days,'known_fixtures':sum(cutoff<=pd.Timestamp(f['date'])<end for f in fixtures),'players':chosen,'definition':'Expected PitchOps Index over known fixtures only; not prediction of an official award or an entire uncovered season.'}

def source_logo(root):
    path=Path(root)/'statsbomb_source_logo.bin'
    try:
        if not path.exists():
            response=requests.get(SOURCE_LOGO,timeout=(10,30));response.raise_for_status();path.write_bytes(response.content)
        return 'data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode()
    except (OSError,requests.RequestException):return SOURCE_LOGO

def build_research(root,as_of='2022-12-15',simulations=3000):
    root=Path(root);cutoff=pd.Timestamp(as_of)
    print('Research 1/6: normalizing real StatsBomb events',flush=True)
    games,logs,locations=load_event_dataset(root/'data'/'statsbomb')
    past_games=games[games.date<cutoff].reset_index(drop=True);past_logs=logs[logs.date<cutoff].reset_index(drop=True)
    if len(past_games)<30:raise ValueError('Replay cutoff needs at least 30 observed matches')
    print('Research 2/6: temporal team and player model validation',flush=True)
    team_models,team_state,team_report,team_frame=fit_team_models(past_games)
    player_model,player_state,player_report=fit_player_model(past_logs,team_frame,past_games)
    scorer_report=scorer_backtest(past_logs,past_games,team_report.pop('test_goal_predictions'))
    print('Research 3/6: spatial predictive densities',flush=True)
    maps,spatial_report=spatial_model(locations,past_logs,cutoff)
    teams=sorted(set(past_games.home)|set(past_games.away));league=str(past_games.iloc[0].league)
    forecasts={};means={}
    for home in teams:
        for away in teams:
            if home==away:continue
            forecast=predict_team(team_models,team_state,home,away,league,cutoff)
            forecasts[home+'|'+away]=forecast;means[(home,away)]=forecast['goals']
    projected={}
    for team in teams:
        opponent=next(t for t in teams if t!=team)
        # Reference opponent GA=1.3 makes rating adjustment analytically reusable.
        reference_state=dict(team_state);reference_state[(league,opponent)]=[(cutoff,1.3,1.3,1)]
        projected[team]=project_players(past_logs,past_games,player_model,player_state,reference_state,team,opponent,1.0,cutoff)
        for player in projected[team]:player['goal_share']=player.pop('expected_goals')
    rating_slope=0.0
    if player_model['selected']:
        prep=player_model['model'][0];numeric=prep.named_transformers_['numeric'];rating_slope=float(player_model['model'][-1].coef_[PNUM.index('opp_ga')]/numeric.scale_[PNUM.index('opp_ga')])
    print('Research 4/6: matchup player distributions and knockout simulations',flush=True)
    for index,(key,forecast) in enumerate(forecasts.items()):
        home,away=key.split('|');adjustments=[];players=[]
        for team,opponent in [(home,away),(away,home)]:
            history=team_state.get((league,opponent),[]);opp_ga=float(np.mean([r[2] for r in history[-5:]])) if history else 1.3
            adjustment=rating_slope*(opp_ga-1.3);adjustments.append(adjustment)
            players.extend([{**p,'rating':float(np.clip(p['rating']+adjustment,3,10))} for p in projected[team]])
        forecast['rating_adjust']=adjustments
        probabilities=motm_probabilities(players,seed=42+index,samples=1200,rating_sigma=max(player_model['interval']/1.645,.15))
        forecast['motm']=sorted(probabilities,key=lambda p:-p['probability'])[:8]
    cup=simulate_world_cup(games,means,cutoff,simulations=simulations)
    custom_teams=[t for t in ['Argentina','France','Croatia','Morocco'] if t in teams]
    custom_cup={'teams':custom_teams,'table':simulate_knockout(custom_teams,means,simulations=simulations),'definition':'Hypothetical seeded four-team bracket; no claim this is the remaining official draw.'}
    future=known_future_fixtures(games,cutoff)
    xi={str(days):best_xi(projected,future,cutoff,days,forecasts) for days in [7,30,365]}
    print('Research 5/6: forecast journal and replay scoring',flush=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');run_id='events-'+stamp
    entries=[]
    for fixture in future:
        f=forecasts[fixture['home']+'|'+fixture['away']]
        entries.append({**fixture,'as_of':str(cutoff.date()),'mode':'replay','model_run_id':run_id,'probabilities':[f['home_win'],f['draw'],f['away_win']]})
    record_forecasts(root/'artifacts'/'event_research',entries)
    outcomes=[{'fixture_id':'statsbomb:'+str(r.match_id),'kickoff':r.kickoff,'finished':True,'home_goals':r.hg,'away_goals':r.ag} for r in games.itertuples()]
    audit=evaluate_forecasts(root/'artifacts'/'event_research',outcomes,model_run_id=run_id)
    payload,source_view=latest_dashboard(root)
    # Display-only face join is exact name + national team, never a model ID join.
    media_players=payload.get('media',{}).get('players',[])
    def clean(text):return ''.join(c for c in __import__('unicodedata').normalize('NFKD',str(text)).lower() if c.isalnum())
    for team,players in projected.items():
        for player in players:
            matches=[p for p in media_players if clean(p['name'])==clean(player['name']) and clean(p.get('nationality'))==clean(team)]
            if len(matches)==1:
                player['image_url']=matches[0].get('image_url');player['image_data']=matches[0].get('image_data')
    report={'team':team_report,'player':player_report,'scorer':scorer_report,'spatial':spatial_report,'forecast_audit':audit}
    research={'run_id':run_id,'as_of':str(cutoff.date()),'source':'StatsBomb Open Data','source_logo':source_logo(root/'data'/'statsbomb'),'source_url':'https://github.com/hudl/open-data','competition':'FIFA World Cup 2022 historical replay','mode':'historical research replay, not a live 2026 forecast','matches_observed':len(past_games),'matches_total':len(games),'player_match_rows':len(past_logs),'players':sum(len(v) for v in projected.values()),'teams':teams,'forecasts':forecasts,'team_players':projected,'spatial':maps,'report':report,'cup':cup,'custom_cup':custom_cup,'future_fixtures':future,'best_xi':xi,'assumptions':['Neutral venue','Player goals reserve 10% for unmodeled players/own goals','Appearance/minutes are empirical estimates, not confirmed lineups','PitchOps Index is a derived research label, not official ratings','MOTM means highest simulated PitchOps Index, not an official award','Control-duration proxy is not official possession','Heatmaps forecast event locations, not tracking movements']}
    payload['research']=research
    try:code_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):code_commit='uncommitted'
    payload['meta']['research_code_commit']=code_commit
    run_dir=root/'artifacts'/'event_research'/'runs'/run_id;run_dir.mkdir(parents=True,exist_ok=False)
    joblib.dump({'team_models':team_models,'player_model':player_model,'team_state':team_state,'as_of':as_of},run_dir/'models.joblib')
    atomic_json(run_dir/'metrics.json',report)
    manifest=json.loads((root/'data'/'statsbomb'/'event_manifest.json').read_text())
    observed_ids=set(past_games.match_id)
    observed_manifest=[row for row in manifest if row['match_id'] in observed_ids]
    atomic_json(run_dir/'source_manifest.json',observed_manifest)
    atomic_json(run_dir/'model_card.json',{'source':research['source_url'],'as_of':as_of,'code_commit':code_commit,'created_at':stamp,'assumptions':research['assumptions'],'matches_sha256':hashlib.sha256(past_games.to_csv(index=False).encode()).hexdigest(),'player_logs_sha256':hashlib.sha256(past_logs.to_csv(index=False).encode()).hexdigest(),'source_manifest_sha256':hashlib.sha256(json.dumps(observed_manifest,sort_keys=True).encode()).hexdigest()})
    freeze=subprocess.run(['python','-m','pip','freeze'],capture_output=True,text=True,check=True)
    (run_dir/'requirements-lock.txt').write_text(freeze.stdout)
    past_logs.to_csv(run_dir/'player_match_logs.csv',index=False)
    atomic_json(run_dir/'snapshot.json',payload)
    print('Research 6/6: rendering persistent analytics dashboard',flush=True)
    render_dashboard(payload,run_dir/'dashboard.html')
    # Keep the existing model-run identity and link this as a derived dashboard view.
    model_run_id=payload['meta']['run_id'];view_dir=root/'artifacts'/'views'/(model_run_id+'-analytics-'+stamp);view_dir.mkdir(parents=True)
    atomic_json(view_dir/'snapshot.json',payload);render_dashboard(payload,view_dir/'dashboard.html')
    atomic_json(view_dir/'source_run.json',{'model_run_id':model_run_id,'event_run_id':run_id})
    atomic_json(root/'artifacts'/'latest_view.json',{'model_run_id':model_run_id,'view_id':view_dir.name})
    print(json.dumps({'event_run':run_id,'observed_matches':len(past_games),'players':research['players'],'view':str(view_dir),'report':report},ensure_ascii=False,indent=2),flush=True)
    return payload,view_dir
