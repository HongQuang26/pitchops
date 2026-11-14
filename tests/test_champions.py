import copy
import pytest
from pitchops.champions import normalize_events, validate_league_phase, simulate_champions, fetch_calendar


def phase():
    names = [f'Club {i:02d}' for i in range(36)]
    return [{'id':f'{i}-{d}', 'date':'2027-01-27T20:00:00+00:00', 'home':names[i],
             'away':names[(i+d)%36], 'stage':'league-phase', 'season':2026,
             'status':'pre', 'score':None, 'regulation':False}
            for i in range(36) for d in range(1,5)]


def event(identity='1', when='2026-11-01T20:00Z', completed=True, period=2):
    return {'id':identity, 'date':when, 'season':{'year':2026,'slug':'league-phase'},
            'competitions':[{'status':{'period':period,'type':{'name':'STATUS_FULL_TIME','completed':completed,'state':'post' if completed else 'pre'}},
                'competitors':[{'id':str(i),'homeAway':side,'score':str(i),'team':{'id':str(i),'displayName':name},'statistics':[]}
                               for i,side,name in [(1,'home','A'),(2,'away','B')]]}]}


def test_ucl_source_never_uses_future_or_extra_time_labels():
    events = [event(), event('2','2026-12-01T20:00Z'), event('3',period=4),event('4',completed=False)]
    frame, fixtures, identities, excluded = normalize_events([{'events':events}], '2026-11-14')
    assert frame.id.tolist() == ['1']
    assert len(fixtures) == 4 and frame.hg.tolist() == [1]
    assert excluded['extra_time_or_unverified_regulation'] == 1
    assert identities['1']['name'] == 'A'
    assert fixtures[-1]['score'] is None


def test_ucl_repeated_pair_can_exist_in_knockout_but_conflicting_ids_fail():
    a=event();b=event('2');b['season']['slug']='round-of-16'
    frame,*_=normalize_events([{'events':[a,b,a]}], '2026-11-14')
    assert len(frame)==2
    changed=copy.deepcopy(a);changed['date']='2026-11-02T20:00Z'
    with pytest.raises(ValueError,match='Conflicting'):
        normalize_events([{'events':[a,changed]}], '2026-11-14')


def test_ucl_requires_real_complete_fixture_graph():
    fixtures=phase();teams,_=validate_league_phase(fixtures)
    assert len(teams)==36
    with pytest.raises(ValueError,match='144'):
        validate_league_phase(fixtures[:-1])
    broken=copy.deepcopy(fixtures);broken[-1]['home']=broken[0]['home']
    with pytest.raises(ValueError):validate_league_phase(broken)


def test_ucl_probability_mass_round_counts_and_fixed_observed_points():
    fixtures=phase();names,_=validate_league_phase(fixtures)
    fixtures[0].update(status='completed',score=[2,0],regulation=True)
    means={a+'|'+b:{'goals':[1.5,1.1]} for a in names for b in names if a!=b}
    race=simulate_champions(fixtures,means,simulations=40)
    assert race['remaining_matches']==143
    for key,total in [('top8',8),('top24',24),('round16',16),('quarterfinal',8),('semifinal',4),('final',2),('title',1)]:
        assert sum(row[key] for row in race['table'])==pytest.approx(total)
    row=next(r for r in race['table'] if r['team']==fixtures[0]['home'])
    assert row['points']==3 and row['played']==1
    assert all(r['title']<=r['final']<=r['semifinal']<=r['quarterfinal']<=r['round16']<=r['top24'] for r in race['table'])
    assert race==simulate_champions(fixtures,means,simulations=40)


def test_ucl_published_knockout_draw_is_not_ignored():
    fixtures=phase()+[{'stage':'round-of-16'}]
    race=simulate_champions(fixtures,{},simulations=1)
    assert race['status']=='awaiting_knockout_conditioning' and race['table']==[]


def test_archived_ucl_cache_is_reused_without_network(tmp_path,monkeypatch):
    (tmp_path/'ucl-espn-2024.bin').write_text('{"events":[]}')
    monkeypatch.setattr('pitchops.champions.requests.get',lambda *a,**k:pytest.fail('Unexpected network'))
    assert fetch_calendar(tmp_path,2024)['events']==[]
