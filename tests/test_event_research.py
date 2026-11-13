"""Event/parser, replay integrity and tournament tests, run only in Colab."""
import json
from datetime import datetime,timezone,timedelta
import numpy as np
import pandas as pd
import pytest
from pitchops.event_data import parse_match,grid_index,minute90
from pitchops.cups import tie_winner,simulate_knockout,rank_group
from pitchops.forecast_store import record_forecasts,evaluate_forecasts
from pitchops.advanced_models import spatial_model,motm_probabilities,player_features
from pitchops.research import known_future_fixtures,best_xi
from pitchops.data import atomic_json
from pitchops.storage import migrate_workspace,latest_dashboard
from pitchops.schedule import run_if_due
from pitchops.providers import APIFootball,import_player_logs

def match_fixture():
    return {'match_id':1,'match_date':'2022-12-01','kick_off':'15:00:00','home_team':{'home_team_id':1,'home_team_name':'A','home_team_group':'A'},'away_team':{'away_team_id':2,'away_team_name':'B'},'home_score':2,'away_score':2,'competition_stage':{'name':'Quarter-finals'}}

def event(kind,team='A',pid=10,period=1,minute=0,**extra):
    return {'type':{'name':kind},'team':{'name':team},'player':{'id':pid,'name':'P'+str(pid)},'period':period,'minute':minute,**extra}

def test_regulation_parser_separates_extra_time_shootout_and_sub_minutes():
    lineup=[{'player':{'id':10,'name':'P10'},'position':{'name':'Center Forward'},'jersey_number':9}]
    events=[event('Starting XI',tactics={'lineup':lineup}),event('Shot',shot={'outcome':{'name':'Goal'},'statsbomb_xg':.4},location=[120,80]),event('Pass',**{'pass':{'type':{'name':'Throw-in'}},'duration':2,'location':[5,20]}),event('Substitution',period=2,minute=60,substitution={'replacement':{'id':11,'name':'P11'}}),event('Shot',pid=11,period=3,minute=100,shot={'outcome':{'name':'Goal'}}),event('Shot',pid=11,period=5,minute=120,shot={'outcome':{'name':'Goal'}})]
    game,players,maps=parse_match(match_fixture(),events)
    assert game['hg']==1 and game['ag']==0 and game['winner']=='A'
    assert game['home_throwins']==1
    assert {p['provider_id']:p['minutes'] for p in players}=={10:60,11:30}
    assert sum(sum(m['counts']) for m in maps)==2
    assert players[0]['goals']==1 and players[1]['goals']==0
    assert abs(game['home_control']+game['away_control']-1)<1e-12

def test_own_goal_is_counted_once_for_opponent():
    game,_,_=parse_match(match_fixture(),[event('Own Goal Against','B'),event('Own Goal For','A')])
    assert game['hg']==1 and game['ag']==0

def test_substitute_uses_own_event_position_instead_of_outgoing_player():
    events=[event('Substitution',pid=10,period=2,minute=60,position={'name':'Center Forward'},substitution={'replacement':{'id':11,'name':'P11'}}),event('Pass',pid=11,period=2,minute=61,position={'name':'Right Back'})]
    _,players,_=parse_match(match_fixture(),events)
    incoming=next(p for p in players if p['provider_id']==11)
    assert incoming['position']=='DF' and incoming['minutes']==30

@pytest.mark.parametrize('point,expected',[([120,80],95),([0,0],0),([-1,10],None),([121,40],None),(None,None)])
def test_spatial_coordinate_bounds(point,expected):assert grid_index(point)==expected

def test_two_leg_zero_goal_tie_uses_explicit_shootout_and_reverse_means():
    assert tie_winner('A','B',0,0,np.random.default_rng(3),legs=2,reverse_means=(0,0),shootout_home=1)=='A'
    with pytest.raises(ValueError,match='reversed'):tie_winner('A','B',1,1,np.random.default_rng(3),legs=2)

def test_knockout_conserves_titles_repeats_seed_and_freezes_known_winner():
    teams=['A','B','C','D'];means={(h,a):(1.2,1.1) for h in teams for a in teams if h!=a}
    known={frozenset(['A','B']):'A'}
    a=simulate_knockout(teams,means,simulations=200,known_winners=known)
    assert a==simulate_knockout(teams,means,simulations=200,known_winners=known)
    assert abs(sum(r['title'] for r in a)-1)<1e-12
    assert next(r for r in a if r['team']=='B')['title']==0
    with pytest.raises(ValueError):simulate_knockout(['A','A'],means)

def test_group_points_precede_goal_difference():
    order=rank_group(['A','B','C'],[('A','B',1,0),('A','C',1,0),('B','C',10,0)],np.random.default_rng(1))
    assert order==['A','B','C']

def test_replay_cannot_be_reported_as_historical_live_and_journal_is_immutable(tmp_path):
    base={'fixture_id':'one','model_run_id':'model','as_of':'2022-12-01','kickoff':'2022-12-02T15:00:00+03:00','probabilities':[.7,.2,.1],'created_at':'2026-01-01T00:00:00Z'}
    assert record_forecasts(tmp_path,[{**base,'mode':'live'},{**base,'mode':'replay'}])==2
    assert record_forecasts(tmp_path,[{**base,'mode':'replay'}])==0
    with pytest.raises(FileExistsError):record_forecasts(tmp_path,[{**base,'mode':'replay','probabilities':[.1,.2,.7]}])
    report=evaluate_forecasts(tmp_path,[{'fixture_id':'one','kickoff':base['kickoff'],'finished':True,'home_goals':1,'away_goals':0}])
    assert report['live']['n']==0 and report['replay']['n']==1 and report['rejected_invalid_timing']==1
    assert abs(report['replay']['log_loss']+np.log(.7))<1e-10

def test_spatial_distribution_positive_normalized_and_future_excluded():
    logs=pd.DataFrame([{'player_id':'s:1','position':'FW'}])
    rows=[{'player_id':'s:1','date':'2022-01-01','counts':[1]+[0]*95},{'player_id':'s:1','date':'2022-01-02','counts':[0,2]+[0]*94}]
    maps,report=spatial_model(rows,logs,'2022-01-03')
    after,_=spatial_model(rows+[{'player_id':'s:1','date':'2023-01-01','counts':[999]*96}],logs,'2022-01-03')
    assert maps==after
    density=np.array(maps['s:1']['predicted'])
    assert (density>0).all() and abs(density.sum()-1)<1e-6
    assert report['heldout_events']==2

def test_motm_probability_mass_and_no_appearance_player():
    values=motm_probabilities([{'id':'a','name':'A','team':'T','rating':9,'appearance_probability':0},{'id':'b','name':'B','team':'T','rating':6,'appearance_probability':1}],samples=500)
    assert values[0]['probability']==0 and values[1]['probability']==1

def test_unknown_knockout_entrants_not_exposed_in_replay_calendar():
    games=pd.DataFrame([{'date':pd.Timestamp('2022-12-10'),'stage':'Quarter-finals','match_id':1,'home':'A','away':'B','kickoff':'2022-12-10T12:00:00'},{'date':pd.Timestamp('2022-12-13'),'stage':'Semi-finals','match_id':2,'home':'A','away':'C','kickoff':'2022-12-13T12:00:00'}])
    assert known_future_fixtures(games,pd.Timestamp('2022-12-09'))==[]
    assert len(known_future_fixtures(games,pd.Timestamp('2022-12-11')))==1

def test_analytics_view_survives_drive_remigration(tmp_path):
    source,destination=tmp_path/'source',tmp_path/'drive';run='20261113-base'
    atomic_json(destination/'artifacts'/'runs'/run/'snapshot.json',{'meta':{'run_id':run}})
    atomic_json(destination/'artifacts'/'views'/(run+'-analytics-new')/'snapshot.json',{'meta':{'run_id':run},'research':{'proof':True}})
    migrate_workspace(source,destination)
    assert latest_dashboard(destination)[0]['research']['proof']

def test_failed_scheduled_job_is_retryable_and_success_is_not_repeated(tmp_path):
    now=datetime(2026,11,13,tzinfo=timezone.utc)
    def fail():raise RuntimeError('fail')
    with pytest.raises(RuntimeError):run_if_due(tmp_path,'weekly',fail,now=now)
    assert run_if_due(tmp_path,'weekly',lambda:'ok',now=now)['status']=='completed'
    assert run_if_due(tmp_path,'weekly',fail,now=now+timedelta(days=1))['status']=='not_due'

def test_opt_in_provider_budget_and_cache_keep_api_key_out_of_files(tmp_path,monkeypatch):
    import pitchops.providers as provider
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'errors':{},'response':[{'id':1}]}
    calls=[]
    def get(*args,**kwargs):calls.append(kwargs);return Response()
    monkeypatch.setattr(provider.requests,'get',get)
    api=APIFootball(tmp_path,'test-secret',daily_budget=1)
    assert api.fixtures(39,2026)==[{'id':1}]
    assert api.fixtures(39,2026)==[{'id':1}] and len(calls)==1
    with pytest.raises(RuntimeError,match='budget'):api.statistics(1)
    assert all('test-secret' not in p.read_text() for p in tmp_path.glob('*.json'))

def test_import_rejects_unnamespaced_player_identity(tmp_path):
    path=tmp_path/'players.csv'
    pd.DataFrame([{'player_id':'123','player':'A','team':'T','date':'2026-01-01','minutes':90,'goals':0,'rating':6.5,'rating_source':'vendor','position':'FW'}]).to_csv(path,index=False)
    with pytest.raises(ValueError,match='namespaced'):import_player_logs(path)

def test_scorer_backtest_excludes_future_logs_and_covers_candidate_set():
    from pitchops.advanced_models import scorer_backtest
    games=pd.DataFrame([{'match_id':1,'date':pd.Timestamp('2022-01-01'),'home':'A','away':'B'},{'match_id':2,'date':pd.Timestamp('2022-01-02'),'home':'A','away':'C'}])
    logs=pd.DataFrame([{'match_id':1,'date':pd.Timestamp('2022-01-01'),'team':'A','player_id':'s:1','position':'FW','minutes':90,'goals':0,'xg':.3,'rating':6},{'match_id':2,'date':pd.Timestamp('2022-01-02'),'team':'A','player_id':'s:1','position':'FW','minutes':90,'goals':1,'xg':.5,'rating':7}])
    prediction=[{'match_index':1,'team':'A','mu':1.2}]
    before=scorer_backtest(logs,games,prediction)
    future={**logs.iloc[-1].to_dict(),'match_id':3,'date':pd.Timestamp('2023-01-01'),'goals':99}
    after=scorer_backtest(pd.concat([logs,pd.DataFrame([future])]),games,prediction)
    assert before==after and before['test_player_candidates']==1 and before['actual_appearance_coverage']==1
    assert before['goal_count_nll']>0 and before['appearance_brier']>0
