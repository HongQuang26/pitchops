import gzip
import json
from pitchops.web_export import public_projection,export_web
import pytest


def snapshot():
    return {'meta':{'run_id':'run-1','created_at':'2026-11-14','training_through':'2026-11-08','code_commit':'a'*40,'workspace':'/private/path','source_manifests':[{'private':'value'}]},
        'metrics':{'selected':'baseline'},'leagues':{'E0':{'name':'Premier League','teams':['A','B'],'forecasts':{},'raw_training_rows':['private']}},
        'media':{'players':[{'id':'1','name':'A','image_data':'data:image/png;base64,private','image_url':'https://www.thesportsdb.com/a.png'}]},
        'raw_matches':['private'],'model_weights':'private'}


def test_public_web_projection_excludes_private_training_and_embedded_files():
    original=snapshot();result=public_projection(original,{'approved':True})
    encoded=json.dumps(result)
    assert 'private' not in encoded
    assert 'image_data' not in encoded
    assert original['media']['players'][0]['image_data']
    assert result['publication']['raw_match_data'] is False


def test_unapproved_model_cannot_be_published_to_web(tmp_path):
    with pytest.raises(ValueError,match='approved'):
        export_web(snapshot(),{'approved':False},tmp_path/'web.json.gz')
    assert not (tmp_path/'web.json.gz').exists()


def test_weekly_club_projection_preserves_separate_historical_research(tmp_path):
    auxiliary={'meta':{'research_code_commit':'research-code'},'research':{'run_id':'historical','as_of':'2022-12-15','teams':['A'],'raw_provider_events':['private']},'media':{'players':[]}}
    result,receipt=export_web(snapshot(),{'approved':True},tmp_path/'web.json.gz',auxiliary)
    assert result['research']['as_of']=='2022-12-15'
    assert result['meta']['research_code_commit']=='research-code'
    assert 'raw_provider_events' not in result['research']
    assert json.loads(gzip.decompress((tmp_path/'web.json.gz').read_bytes()))==result
    assert receipt['bytes']==(tmp_path/'web.json.gz').stat().st_size


def test_model_and_web_registry_are_updated_only_after_both_assets_upload(tmp_path,monkeypatch):
    from pitchops.weekly import publish_release
    from types import SimpleNamespace
    import requests
    class Remote:
        repository='HongQuang26/pitchops'
        token='test-only'
        def __init__(self):self.state={'promoted_model':{'run_id':'old'}};self.calls=[]
        def request(self,method,path,**kwargs):
            self.calls.append((method,path))
            return {'id':123,'html_url':'https://github.com/HongQuang26/pitchops/releases/tag/model-new'}
        def read(self):return self.state.copy()
        def write(self,state,message):self.state=state
    remote=Remote();model=tmp_path/'model.enc';web=tmp_path/'web.json.gz'
    model.write_bytes(b'encrypted fixture');web.write_bytes(b'public derived fixture')
    receipt={'run_id':'new','code_commit':'a'*40};web_receipt={'run_id':'new','sha256':'b'*64}
    def fail_web(*args,**kwargs):
        if kwargs['params']['name']=='web.json.gz':raise requests.HTTPError('Upload failed')
        return SimpleNamespace(raise_for_status=lambda:None)
    monkeypatch.setattr('pitchops.weekly.requests.post',fail_web)
    with pytest.raises(requests.HTTPError):publish_release(remote,model,receipt,(web,web_receipt))
    assert remote.state=={'promoted_model':{'run_id':'old'}}
    assert not any(method=='PATCH' for method,_ in remote.calls)
    monkeypatch.setattr('pitchops.weekly.requests.post',lambda *args,**kwargs:SimpleNamespace(raise_for_status=lambda:None))
    publish_release(remote,model,receipt,(web,web_receipt))
    assert remote.state['promoted_model']['run_id']=='new'
    assert remote.state['promoted_web']['sha256']=='b'*64
    assert remote.state['promoted_web']['asset_url'].endswith('/model-new/web.json.gz')
