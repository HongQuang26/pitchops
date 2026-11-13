import json
from pathlib import Path
import pytest
from pitchops.storage import migrate_workspace, latest_run, verify_persistence
from pitchops.media import resolve_team, safe_image_url, logo_from_index, player_record
from pitchops.media import is_player_position
from pitchops.data import atomic_json

def test_migration_rebases_latest_and_is_idempotent(tmp_path):
    source, dest = tmp_path/'runtime', tmp_path/'drive'
    run = source/'artifacts'/'runs'/'20261113-run'
    atomic_json(run/'snapshot.json', {'meta':{'run_id':'20261113-run'}})
    (run/'model.joblib').write_bytes(b'test model bytes')
    atomic_json(source/'artifacts'/'latest.json', {'run_id':run.name,'snapshot':str(run/'snapshot.json')})
    a=migrate_workspace(source,dest)
    assert a['copied']==2 and a['verified']==2
    payload,current=latest_run(dest)
    assert current == dest/'artifacts'/'runs'/run.name
    assert current.joinpath('model.joblib').read_bytes()==b'test model bytes'
    assert migrate_workspace(source,dest)['copied']==0
    assert verify_persistence(dest)['write_read_verified']

def test_migration_does_not_overwrite_conflicting_model(tmp_path):
    source,dest=tmp_path/'a',tmp_path/'b'
    for root,text in [(source,b'old'),(dest,b'new')]:
        path=root/'artifacts'/'runs'/'run'/'model.joblib'
        path.parent.mkdir(parents=True);path.write_bytes(text)
    with pytest.raises(FileExistsError):
        migrate_workspace(source,dest)
    assert (dest/'artifacts'/'runs'/'run'/'model.joblib').read_bytes()==b'new'

def test_migration_preserves_both_provider_quota_logs(tmp_path):
    source,dest=tmp_path/'a',tmp_path/'b'
    atomic_json(source/'data'/'bronze'/'provider.json',[{'url':'a','time':1}])
    atomic_json(dest/'data'/'bronze'/'provider.json',[{'url':'b','time':2}])
    migrate_workspace(source,dest)
    rows=json.loads((dest/'data'/'bronze'/'provider.json').read_text())
    assert {r['url'] for r in rows}=={'a','b'}

def test_nested_workspaces_rejected(tmp_path):
    with pytest.raises(ValueError):
        migrate_workspace(tmp_path,tmp_path/'nested')

def test_team_identity_uses_exact_alias_and_refuses_ambiguity():
    records=[{'idTeam':'1','strTeam':'Manchester City','strTeamAlternate':'Man City'}]
    assert resolve_team('Man City',records)['idTeam']=='1'
    assert resolve_team('Manchester',records) is None
    assert resolve_team('Man City',records+[{'idTeam':'2','strTeam':'Man City'}]) is None

@pytest.mark.parametrize('url',['javascript:alert(1)','http://r2.thesportsdb.com/a.png','https://evil.example/a.png','https://www.thesportsdb.com.evil.example/a.png','https://user:secret@www.thesportsdb.com/a.png'])
def test_external_image_validation(url):
    assert safe_image_url(url) is None

def test_logo_index_has_no_fuzzy_club_matching():
    index=[{'path':'logos/England/Manchester City.png','type':'blob'},{'path':'history/2020/Man City.png','type':'blob'}]
    assert logo_from_index('Man City',index)=='logos/England/Manchester City.png'
    assert logo_from_index('Manchester',index) is None

def test_player_face_uses_namespaced_id_and_same_provider_metadata():
    row={'idPlayer':'7','strPlayer':'Test Player','strCutout':'https://r2.thesportsdb.com/player/7.png','strTeam':'Test FC','strCreativeCommonsAttribution':'Creator credit'}
    item=player_record(row,'E0','Test FC')
    assert item['id']=='thesportsdb:7'
    assert item['image_url']==row['strCutout']
    assert item['credit']=='Creator credit'

def test_media_refresh_does_not_rewrite_model_snapshot(tmp_path,monkeypatch):
    import pitchops.media as media
    from pitchops.storage import latest_dashboard
    model_dir=tmp_path/'artifacts'/'runs'/'20261113-run'
    atomic_json(model_dir/'snapshot.json',{'meta':{'run_id':model_dir.name}})
    before=(model_dir/'snapshot.json').read_bytes()
    atomic_json(tmp_path/'artifacts'/'latest.json',{'run_id':model_dir.name})
    monkeypatch.setattr(media,'sync_media',lambda *a,**kw:{'retrieved_at':'2026-11-13T00:00:00Z','coverage':{},'players':[],'teams':{},'leagues':{}})
    payload,view_dir=media.enrich_dashboard(tmp_path)
    assert (model_dir/'snapshot.json').read_bytes()==before
    assert view_dir.parent.name=='views'
    assert latest_run(tmp_path)[1]==model_dir
    assert latest_dashboard(tmp_path)[1]==view_dir
    assert payload['meta']['model_run_directory']==str(model_dir)

@pytest.mark.parametrize('position',['Manager','Assistant Manager','Goalkeeping Coach','Technical Director','Physiotherapist'])
def test_support_staff_are_not_player_cards(position):
    assert not is_player_position(position)

def test_verified_club_aliases_match_secondary_logo_filenames():
    index=[{'path':'logos/Germany - Bundesliga/VfB Stuttgart.png','type':'blob'},{'path':'logos/Spain - LaLiga/CA Osasuna.png','type':'blob'}]
    assert logo_from_index('Stuttgart',index).endswith('VfB Stuttgart.png')
    assert logo_from_index('Osasuna',index).endswith('CA Osasuna.png')
