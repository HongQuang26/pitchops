"""CI/CD safety and correctness contracts, without scraping in tests."""
import io
import json
from pathlib import Path
import tarfile
from datetime import datetime,timezone
import pytest
from cryptography.exceptions import InvalidTag
from pitchops.artifact_sync import recipient_keys,encrypt_bytes,decrypt_bytes,package_run,import_bundle,unpack_run
from pitchops.weekly import rolling_seasons,promotion_gate,GitHubState
from pitchops.data import atomic_json,CachedHTTP

@pytest.fixture
def keys(tmp_path):
    private,public=recipient_keys(tmp_path)
    return private.read_bytes(),public.read_bytes()

def test_encrypted_artifact_roundtrip_and_tamper_detection(keys):
    private,public=keys;plain=b'private model and academic source data'
    cipher=encrypt_bytes(plain,public)
    assert plain not in cipher and decrypt_bytes(cipher,private)==plain
    altered=cipher[:-1]+bytes([cipher[-1]^1])
    with pytest.raises(InvalidTag):decrypt_bytes(altered,private)

def test_recipient_key_is_preserved_between_colab_sessions(tmp_path):
    private,public=recipient_keys(tmp_path);before=private.read_bytes()
    recipient_keys(tmp_path)
    assert private.read_bytes()==before and public.read_bytes().startswith(b'-----BEGIN PUBLIC KEY-----')

def test_path_traversal_archive_does_not_write_anything(tmp_path):
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as tar:
        member=tarfile.TarInfo('../../escaped');member.size=1;tar.addfile(member,io.BytesIO(b'x'))
    with pytest.raises(ValueError,match='Unsafe'):unpack_run(archive.getvalue(),tmp_path,'run')
    assert not list(tmp_path.iterdir())

def test_encrypted_delivery_preserves_local_research_and_model_snapshot(tmp_path,keys):
    private,public=keys;source=tmp_path/'ci';dest=tmp_path/'drive'
    run='20261113-new'
    atomic_json(source/'artifacts'/'runs'/run/'snapshot.json',{'meta':{'run_id':run,'created_at':'2026-11-13T00:00:00+00:00','code_commit':'a'*40}})
    (source/'artifacts'/'runs'/run/'model.joblib').write_bytes(b'model')
    old='20261112-old';old_payload={'meta':{'run_id':old,'created_at':'2026-11-12T00:00:00+00:00'},'research':{'as_of':'2022-12-15'},'media':{'players':[]}}
    atomic_json(dest/'artifacts'/'runs'/old/'snapshot.json',old_payload);atomic_json(dest/'artifacts'/'latest.json',{'run_id':old})
    cipher=tmp_path/'model.enc';receipt=package_run(source,run,public,cipher)
    result=import_bundle(dest,cipher.read_bytes(),receipt,private)
    from pitchops.storage import latest_dashboard
    payload,view=latest_dashboard(dest)
    assert result['status']=='updated' and payload['research']==old_payload['research'] and payload['media']==old_payload['media']
    assert 'research' not in json.loads((dest/'artifacts'/'runs'/run/'snapshot.json').read_text())
    assert (dest/'artifacts'/'runs'/old/'snapshot.json').exists()

def test_archive_for_wrong_recipient_is_rejected(tmp_path,keys):
    private,public=keys
    other_private,_=recipient_keys(tmp_path/'other')
    cipher=encrypt_bytes(b'x',public)
    with pytest.raises(ValueError,match='another recipient'):
        from pitchops.artifact_sync import fingerprint
        import_bundle(tmp_path/'dest',cipher,{'sha256':__import__('hashlib').sha256(cipher).hexdigest(),'recipient_sha256':fingerprint(public),'run_id':'x'},other_private.read_bytes())

def test_season_rollover_uses_actual_calendar_year():
    assert rolling_seasons(datetime(2026,11,13,tzinfo=timezone.utc))==['2526','2627']
    assert rolling_seasons(datetime(2027,1,1,tzinfo=timezone.utc))==['2526','2627']
    assert rolling_seasons(datetime(2027,8,1,tzinfo=timezone.utc))==['2627','2728']

def test_bad_candidate_cannot_pass_deployment_gate():
    config={'minimum_test_matches':100,'maximum_test_log_loss_ratio':1.05,'leagues':['E0'],'maximum_in_season_match_age_days':21}
    payload={'metrics':{'test':{'matches':473,'log_loss':1.8,'brier':.8,'goals_mae':1.1},'test_baseline':{'log_loss':1.0}},'quality':{'duplicate_matches':0,'missing_goal_labels':0,'snapshot_age_days':1},'leagues':{'E0':{'teams':[str(i) for i in range(20)],'forecasts':{'A|B':{'home_win':.4,'draw':.3,'away_win':.3}}}}}
    assert not promotion_gate(payload,config)['approved']
    payload['metrics']['test']['log_loss']=.9
    assert promotion_gate(payload,config)['approved']
    payload['leagues']['E0']['forecasts']['A|B']['home_win']=.9
    assert not promotion_gate(payload,config)['approved']

def test_cached_http_guard_does_not_run_for_cache_hits(tmp_path,monkeypatch):
    import hashlib,time
    url='https://www.football-data.co.uk/test.xlsx'
    (tmp_path/(hashlib.sha256(url.encode()).hexdigest()+'.bin')).write_bytes(b'cached')
    def fail(url):raise AssertionError('guard should only reserve actual network attempts')
    monkeypatch.setattr(CachedHTTP,'request_guard',fail)
    assert CachedHTTP(tmp_path).get(url)==b'cached'

def test_shared_guard_refuses_third_attempt_before_http(monkeypatch):
    remote=GitHubState('test-token');now=__import__('time').time()
    monkeypatch.setattr(remote,'read',lambda:{'provider_attempts':[{'time':now,'url':'https://www.football-data.co.uk/a'},{'time':now,'url':'https://www.football-data.co.uk/b'}]})
    with pytest.raises(RuntimeError,match='budget'):remote.reserve('https://www.football-data.co.uk/mmz4281/c.xlsx')

def test_failed_render_never_promotes_partial_model_run(tmp_path,monkeypatch):
    import pandas as pd
    import pitchops.pipeline as pipeline
    import pitchops.dashboard as dashboard
    previous={'run_id':'old','snapshot':'old/snapshot.json'}
    atomic_json(tmp_path/'artifacts'/'latest.json',previous)
    records=[{'league':'E0','season':'2627','date':pd.Timestamp('2026-01-01')+pd.Timedelta(days=i),'home':'A','away':'B','hg':1,'ag':0,'hc':4,'ac':3,'hs':8,'as':6} for i in range(60)]
    monkeypatch.setattr(pipeline,'load_seasons',lambda *a,**kw:(pd.DataFrame(records),[]))
    models={'goals':None,'corners':None,'shots':None,'selected':'baseline','baseline':{'global':1.3,'rates':{}}}
    report={'selected':'baseline','test':{'log_loss':1.0},'test_baseline':{'log_loss':1.0}}
    monkeypatch.setattr(pipeline,'train_and_evaluate',lambda frame:(models,report))
    def fail(*args):raise OSError('simulated render failure')
    monkeypatch.setattr(dashboard,'render_dashboard',fail)
    with pytest.raises(OSError,match='render failure'):pipeline.run(tmp_path,simulations=1)
    assert json.loads((tmp_path/'artifacts'/'latest.json').read_text())==previous


def test_failed_deployment_gate_restores_previous_champion(tmp_path,keys,monkeypatch):
    import pitchops.pipeline as pipeline
    from pitchops.weekly import train_weekly
    private,public=keys
    previous={'run_id':'champion'};atomic_json(tmp_path/'artifacts'/'latest.json',previous)
    config={'history_seasons':2,'leagues':['E0'],'simulations':1,'automatic_retries':1,'minimum_test_matches':100,'maximum_test_log_loss_ratio':1.05,'maximum_in_season_match_age_days':21}
    def run(*args,**kwargs):
        atomic_json(tmp_path/'artifacts'/'latest.json',{'run_id':'candidate'})
        return {'meta':{'run_id':'candidate','code_commit':'a'*40,'training_through':'2026-11-01','matches':10},'metrics':{'selected':'baseline','test':{'matches':3,'log_loss':2.0,'brier':.8,'goals_mae':1},'test_baseline':{'log_loss':1.0}},'quality':{},'leagues':{}},tmp_path
    monkeypatch.setattr(pipeline,'run',run)
    with pytest.raises(ValueError,match='quality gate'):train_weekly(tmp_path,config,public)
    assert json.loads((tmp_path/'artifacts'/'latest.json').read_text())==previous
    assert (tmp_path/'weekly_failure.json').exists()
