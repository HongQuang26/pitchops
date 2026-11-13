"""Meaningful leakage, probability, quality and simulation invariants."""
import numpy as np
import pandas as pd
import pytest
from pitchops.data import validate_matches, CachedHTTP
from pitchops.features import build_features, FEATURES
from pitchops.models import score_distribution, train_and_evaluate
from pitchops.simulation import simulate_league
from pitchops.players import scorer_projection

def toy(n=80):
    rows=[]
    for i in range(n):
        rows.append(dict(league="E0",season=str(2400+i//2),date=pd.Timestamp("2024-01-01")+pd.Timedelta(days=i),home="A" if i%2==0 else "B",away="B" if i%2==0 else "A",hg=i%4,ag=(i+1)%3,hc=5,ac=4,hs=10,**{"as":8}))
    return pd.DataFrame(rows)

def test_future_goals_do_not_change_past_features():
    data=toy();original,_=build_features(data)
    changed=data.copy();changed.loc[40:,"hg"]=50
    after,_=build_features(changed)
    pd.testing.assert_frame_equal(original[original.match_id<40][FEATURES],after[after.match_id<40][FEATURES])

def test_same_day_results_are_not_features():
    data=toy(2);data.loc[1,"date"]=data.loc[0,"date"]
    frame,_=build_features(data)
    assert frame.own_games.eq(0).all()

@pytest.mark.parametrize("home,away",[(.01,.01),(1.5,.8),(5,7)])
def test_probability_mass_and_orientation(home,away):
    d=score_distribution(home,away)
    assert abs(d["home_win"]+d["draw"]+d["away_win"]-1)<1e-10
    assert d["home_win"]>d["away_win"] if home>away else d["home_win"]<=d["away_win"]+1e-10

def test_duplicate_quality_gate():
    data=toy(1)
    with pytest.raises(ValueError,match="Duplicate"):
        validate_matches(pd.concat([data,data]))

def test_negative_labels_rejected():
    data=toy(1);data.loc[0,"hg"]=-1
    with pytest.raises(ValueError,match="Invalid"):
        validate_matches(data)

def test_sparse_membership_cannot_produce_title_odds():
    result=simulate_league(toy(2),"E0","2400",{}, {}, simulations=100)
    assert result["status"]=="unavailable"

def test_future_player_results_are_excluded():
    df=pd.DataFrame([dict(player_id=1,player="A",team="T",date="2024-01-01",minutes=90,goals=1),dict(player_id=1,player="A",team="T",date="2025-01-01",minutes=90,goals=100)])
    a=scorer_projection(df,"2024-06-01",{1:90})
    b=scorer_projection(df.iloc[:1],"2024-06-01",{1:90})
    assert a==b

def test_cached_provider_budget_blocks_new_requests(tmp_path):
    import json,time
    (tmp_path/"www.football-data.co.uk.json").write_text(json.dumps([{"time":time.time(),"url":"a"},{"time":time.time(),"url":"b"}]))
    with pytest.raises(RuntimeError,match="budget"):
        CachedHTTP(tmp_path).get("https://www.football-data.co.uk/new.xlsx")

def test_completed_season_preserves_known_champion():
    teams=[f"T{i:02d}" for i in range(20)]
    rows=[dict(league="E0",season="2425",date=pd.Timestamp("2025-05-01"),home=h,away=a,hg=2 if h=="T00" else 0,ag=2 if a=="T00" else 0) for h in teams for a in teams if h!=a]
    result=simulate_league(pd.DataFrame(rows),"E0","2425",{}, {},simulations=30)
    assert result["status"]=="completed"
    assert result["remaining_matches"]==0
    assert result["table"][0]["team"]=="T00"
    assert result["table"][0]["title"]==1
    assert result["table"][0]["expected_points"]==114

def test_simulation_reproducibility_and_conservation():
    teams=[f"T{i:02d}" for i in range(20)]
    data=pd.DataFrame([dict(league="E0",season="2425",date=pd.Timestamp("2024-08-01"),home=teams[i],away=teams[i+1],hg=1,ag=0) for i in range(0,20,2)])
    models={"goals":None,"corners":None,"shots":None,"selected":"baseline","baseline":{"global":1.3,"rates":{}}}
    a=simulate_league(data,"E0","2425",models,{},simulations=100,seed=12)
    b=simulate_league(data,"E0","2425",models,{},simulations=100,seed=12)
    assert a==b
    assert abs(sum(row["title"] for row in a["table"])-1)<1e-10
    assert a["remaining_matches"]==370
    assert all(row["expected_points"]>=row["points"] for row in a["table"])
