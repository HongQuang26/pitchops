"""Temporal team/player models and Bayesian event-location forecasts."""
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import PoissonRegressor,Ridge
from sklearn.metrics import mean_absolute_error
from .features import build_features,match_rows,FEATURES,NUMERIC,CATEGORICAL
from .models import score_distribution,evaluate

EXTRA_TARGETS=['throwins','control']
PNUM=['past_rating','past_goals90','past_xg90','past_minutes','past_apps','team_gf','opp_ga','is_home']

def team_features(games):
    frame,state=build_features(games)
    by_id=games.to_dict('index')
    for index,row in frame.iterrows():
        game=by_id[int(row.match_id)];home=row.is_home==1
        frame.loc[index,'throwins']=game['home_throwins'] if home else game['away_throwins']
        frame.loc[index,'control']=game['home_control'] if home else game['away_control']
    return frame,state

def regressor(target):
    preprocessing=ColumnTransformer([('numeric',StandardScaler(),NUMERIC),('identity',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATEGORICAL)])
    estimator=Ridge(alpha=20) if target=='control' else PoissonRegressor(alpha=.8,max_iter=500)
    return make_pipeline(preprocessing,estimator)

def fit_team_models(games):
    frame,state=team_features(games);dates=np.sort(frame.date.unique())
    if len(dates)<8:raise ValueError('At least eight distinct dates are required')
    vdate,tdate=dates[int(len(dates)*.60)],dates[int(len(dates)*.80)]
    development=frame[frame.date<vdate];validation=frame[(frame.date>=vdate)&(frame.date<tdate)]
    before_test=frame[frame.date<tdate];test=frame[frame.date>=tdate]
    models={};report={'validation_from':str(pd.Timestamp(vdate).date()),'test_from':str(pd.Timestamp(tdate).date()),'test_matches':int(test.match_id.nunique()),'targets':{},'status':'exploratory: small historical competition; not a current global forecast'}
    for target in ['goals','corners','shots','throwins','control']:
        candidate=regressor(target).fit(development[FEATURES],development[target])
        base=float(development[target].mean())
        val_pred=candidate.predict(validation[FEATURES]);val_base=np.full(len(validation),base)
        use_model=mean_absolute_error(validation[target],val_pred)<mean_absolute_error(validation[target],val_base)
        fitted=regressor(target).fit(before_test[FEATURES],before_test[target])
        test_pred=fitted.predict(test[FEATURES]) if use_model else np.full(len(test),float(before_test[target].mean()))
        if target=='control':test_pred=np.clip(test_pred,.05,.95)
        report['targets'][target]={'selected':'regularized model' if use_model else 'mean baseline','test_n':len(test),'test_mae':float(mean_absolute_error(test[target],test_pred)),'baseline_mae':float(mean_absolute_error(test[target],np.full(len(test),float(before_test[target].mean()))))}
        models[target]={'model':regressor(target).fit(frame[FEATURES],frame[target]),'selected':use_model,'baseline':float(frame[target].mean())}
        if target=='goals':
            report['outcomes']=evaluate(test,np.maximum(test_pred,.01))
            report['test_goal_predictions']=[{'match_index':int(row.match_id),'team':row.team,'mu':float(mu)} for row,mu in zip(test.itertuples(),test_pred)]
    report['proxy_definition']='Control = share of duration of observed Pass/Carry/Dribble actions, not official possession or ball-in-play tracking.'
    return models,state,report,frame

def predict_team(models,state,home,away,league,date):
    rows=pd.DataFrame(match_rows(home,away,league,pd.Timestamp(date),state))
    rows['is_home']=.5  # neutral venue in the open-data international research cohort
    values={}
    for target,entry in models.items():
        pred=entry['model'].predict(rows[FEATURES]) if entry['selected'] else np.full(2,entry['baseline'])
        values[target]=np.clip(pred,.01,.99).tolist() if target=='control' else np.maximum(pred,.01).tolist()
    total=sum(values['control']);values['control']=[v/total for v in values['control']]
    result=score_distribution(*values['goals']);result.update(values)
    return result

def past_player(history):
    rows=history[-5:]
    minutes=sum(r['minutes'] for r in rows)
    return {'past_rating':float(np.mean([r['rating'] for r in rows])) if rows else 6.2,'past_goals90':float((sum(r['goals'] for r in rows)+1.5)/(minutes+900)*90),'past_xg90':float((sum(r['xg'] for r in rows)+1.5)/(minutes+900)*90),'past_minutes':float(np.mean([r['minutes'] for r in rows])) if rows else 45,'past_apps':len(history)}

def player_features(logs,team_frame,games):
    state=defaultdict(list);rows=[]
    game_indices={int(game.match_id):index for index,game in games.iterrows()}
    team_lookup={(int(r.match_id),r.team):r for r in team_frame.itertuples()}
    for date,batch in logs.groupby('date',sort=True):
        updates=[]
        for row in batch.to_dict('records'):
            feature=past_player(state[row['player_id']]);team=team_lookup[(game_indices[int(row['match_id'])],row['team'])]
            feature.update({'date':date,'match_id':row['match_id'],'player_id':row['player_id'],'position':row['position'],'rating':row['rating'],'minutes':row['minutes'],'team_gf':team.own_gf,'opp_ga':team.opp_ga,'is_home':row['is_home']})
            rows.append(feature);updates.append(row)
        for row in updates:state[row['player_id']].append(row)
    return pd.DataFrame(rows),dict(state)

def player_regressor():
    return make_pipeline(ColumnTransformer([('numeric',StandardScaler(),PNUM),('position',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['position'])]),Ridge(alpha=30))

def fit_player_model(logs,team_frame,games):
    features,state=player_features(logs,team_frame,games);dates=np.sort(features.date.unique())
    vdate,tdate=dates[int(.6*len(dates))],dates[int(.8*len(dates))]
    dev=features[features.date<vdate];val=features[(features.date>=vdate)&(features.date<tdate)]
    pretest=features[features.date<tdate];test=features[features.date>=tdate]
    candidate=player_regressor().fit(dev[PNUM+['position']],dev.rating)
    validation_pred=candidate.predict(val[PNUM+['position']])
    selected=mean_absolute_error(val.rating,validation_pred)<mean_absolute_error(val.rating,val.past_rating)
    residuals=val.rating-(validation_pred if selected else val.past_rating)
    interval=float(np.quantile(np.abs(residuals),.90))
    before_test=player_regressor().fit(pretest[PNUM+['position']],pretest.rating)
    pred=before_test.predict(test[PNUM+['position']]) if selected else test.past_rating.to_numpy()
    report={'label':'PitchOps Index v1, derived from goals/assists/passes/defensive events; NOT official player ratings','selected':'ridge' if selected else 'rolling baseline','test_n':len(test),'test_mae':float(mean_absolute_error(test.rating,pred)),'baseline_mae':float(mean_absolute_error(test.rating,test.past_rating)),'interval_radius':interval,'test_interval_coverage':float((np.abs(test.rating-pred)<=interval).mean()),'conditioning':'Rating evaluation conditions on actual appearances; lineup/appearance calibration is not established.'}
    return {'model':player_regressor().fit(features[PNUM+['position']],features.rating),'selected':selected,'interval':max(interval,.15)},state,report

def project_players(logs,games,player_model,player_state,team_state,team_name,opponent,team_goals,as_of):
    cutoff=pd.Timestamp(as_of);past=logs[(logs.date<cutoff)&(logs.team==team_name)]
    team_games=games[(games.date<cutoff)&((games.home==team_name)|(games.away==team_name))].tail(5)
    recent_ids=set(team_games.match_id)
    cohort=past[past.match_id.isin(recent_ids)]
    rows=[];weights=[];prediction_rows=[]
    for pid,history in cohort.groupby('player_id'):
        latest=history.sort_values(['date','match_id']).iloc[-1]
        appearance=(history.match_id.nunique()+1)/(len(team_games)+2)
        conditional_minutes=float(history.minutes.mean());expected_minutes=appearance*conditional_minutes
        feature=past_player(player_state.get(pid,[]))
        league=str(games.iloc[0].league)
        own=team_state.get((league,team_name),[]);other=team_state.get((league,opponent),[])
        feature.update({'position':latest.position,'team_gf':float(np.mean([r[1] for r in own[-5:]])) if own else 1.3,'opp_ga':float(np.mean([r[2] for r in other[-5:]])) if other else 1.3,'is_home':.5})
        prediction_rows.append(feature)
        weight=max(feature['past_xg90'],.015)*expected_minutes/90
        if latest.position=='GK':weight=.0001*expected_minutes/90
        weights.append(weight)
        rows.append({'id':pid,'name':latest.player,'team':team_name,'position':latest.position,'number':str(int(latest.number)) if pd.notna(latest.number) else '', 'appearance_probability':appearance,'expected_minutes':expected_minutes})
    if not rows:return []
    predictions=player_model['model'].predict(pd.DataFrame(prediction_rows)[PNUM+['position']]) if player_model['selected'] else np.array([r['past_rating'] for r in prediction_rows])
    for row,predicted in zip(rows,predictions):
        row.update({'rating':float(np.clip(predicted,3,10)),'rating_low':float(max(3,predicted-player_model['interval'])),'rating_high':float(min(10,predicted+player_model['interval']))})
    # Reserve 10% of team goals for unmodeled/new/bench players and own goals.
    total=sum(weights)
    for row,weight in zip(rows,weights):
        mu=.9*team_goals*weight/total
        conditional=mu/max(row['appearance_probability'],.01)
        row.update({'expected_goals':float(mu),'p_score':float(row['appearance_probability']*(1-np.exp(-conditional))),'p_2plus':float(row['appearance_probability']*(1-np.exp(-conditional)*(1+conditional)))})
    return sorted(rows,key=lambda r:-r['expected_goals'])

def motm_probabilities(players,seed=42,samples=2500,rating_sigma=.35):
    if not players:return []
    rng=np.random.default_rng(seed);mu=np.array([p['rating'] for p in players]);appearance=np.array([p['appearance_probability'] for p in players])
    ratings=rng.normal(mu,rating_sigma,size=(samples,len(players)))
    active=rng.random(ratings.shape)<appearance;ratings[~active]=-np.inf
    valid=active.any(axis=1)
    wins=np.bincount(ratings[valid].argmax(axis=1),minlength=len(players)) if valid.any() else np.zeros(len(players))
    denom=max(1,int(valid.sum()))
    return [{'id':p['id'],'name':p['name'],'team':p['team'],'probability':float(wins[i]/denom)} for i,p in enumerate(players)]

def scorer_backtest(logs,games,test_predictions):
    """Heldout team means + player history strictly before each test date.

    Evaluate the recent-player candidate set, including non-appearances; report
    actual-player coverage separately. No final-refit team model is used here.
    """
    rows=[];covered=0;actual_total=0
    for prediction in test_predictions:
        game=games.loc[prediction['match_index']];team=prediction['team'];date=game.date
        history=logs[(logs.team==team)&(logs.date<date)]
        recent=games[(games.date<date)&((games.home==team)|(games.away==team))].tail(5)
        cohort=history[history.match_id.isin(recent.match_id)]
        candidates=[]
        for pid,group in cohort.groupby('player_id'):
            values=past_player(group.to_dict('records'));latest=group.iloc[-1]
            appearance=(group.match_id.nunique()+1)/(len(recent)+2)
            minutes=appearance*float(group.minutes.mean())
            weight=max(values['past_xg90'],.015)*minutes/90
            if latest.position=='GK':weight=.0001*minutes/90
            candidates.append((pid,appearance,weight))
        total=sum(p[2] for p in candidates)
        actual=logs[(logs.match_id==game.match_id)&(logs.team==team)]
        labels={r.player_id:int(r.goals) for r in actual.itertuples()}
        covered+=sum(pid in {p[0] for p in candidates} for pid in labels);actual_total+=len(labels)
        for pid,appearance,weight in candidates:
            mu=.9*prediction['mu']*weight/max(total,1e-12);conditional=mu/appearance;goals=labels.get(pid,0)
            pscore=appearance*(1-np.exp(-conditional))
            probability=(1-appearance)+appearance*np.exp(-conditional) if goals==0 else appearance*poisson.pmf(goals,conditional)
            rows.append({'mae':abs(goals-mu),'nll':-np.log(max(probability,1e-12)),'score_brier':(pscore-int(goals>0))**2,'appearance_brier':(appearance-int(pid in labels))**2,'score_probability':pscore,'scored':int(goals>0)})
    return {'test_player_candidates':len(rows),'actual_appearance_coverage':covered/max(actual_total,1),'goal_count_mae':float(np.mean([r['mae'] for r in rows])) if rows else None,'goal_count_nll':float(np.mean([r['nll'] for r in rows])) if rows else None,'scorer_brier':float(np.mean([r['score_brier'] for r in rows])) if rows else None,'appearance_brier':float(np.mean([r['appearance_brier'] for r in rows])) if rows else None,'mean_score_probability':float(np.mean([r['score_probability'] for r in rows])) if rows else None,'observed_score_rate':float(np.mean([r['scored'] for r in rows])) if rows else None,'definition':'Test recent-player candidate set, including non-appearances; team means from pre-test fit, updated historical features only; unseen entrants excluded and coverage reported. No calibration fitted.'}

def spatial_model(locations,logs,as_of):
    cutoff=pd.Timestamp(as_of);positions=dict(zip(logs.player_id,logs.position))
    prior={p:np.ones(96)*.25 for p in ['GK','DF','MF','FW']};counts=defaultdict(lambda:np.zeros(96))
    available=[row for row in locations if pd.Timestamp(row['date'])<cutoff]
    dates=sorted({pd.Timestamp(row['date']) for row in available});split=dates[int(len(dates)*.7)]
    train_player=defaultdict(lambda:np.zeros(96));train_position={p:np.ones(96)*.25 for p in prior}
    for row in available:
        pid=row['player_id'];vector=np.array(row['counts'],dtype=float);position=positions.get(pid,'MF')
        counts[pid]+=vector;prior[position]+=vector
        if pd.Timestamp(row['date'])<split:train_player[pid]+=vector;train_position[position]+=vector
    loss=0.0;n=0
    for row in available:
        if pd.Timestamp(row['date'])<split:continue
        pid=row['player_id'];base=train_position[positions.get(pid,'MF')];base=base/base.sum()
        density=(train_player[pid]+50*base)/(train_player[pid].sum()+50)
        observed=np.array(row['counts']);loss-=float((observed*np.log(density.clip(1e-12))).sum());n+=int(observed.sum())
    maps={}
    for pid,vector in counts.items():
        base=prior[positions.get(pid,'MF')];base=base/base.sum()
        density=(vector+50*base)/(vector.sum()+50)
        maps[pid]={'predicted':density.reshape(8,12).round(8).tolist(),'observed':vector.reshape(8,12).astype(int).tolist(),'events':int(vector.sum())}
    report={'grid':[12,8],'heldout_events':n,'heldout_log_loss':loss/n if n else None,'uniform_log_loss':float(np.log(96)),'definition':'Bayesian next-event location density with position prior; not continuous player tracking or a tactical movement simulation.'}
    return maps,report
