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
