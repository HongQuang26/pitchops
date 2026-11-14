"""Headless weekly training and encrypted delivery, runnable in Actions or Colab.

CI is allowed only on the trusted default branch. No raw dataset/model is put in
public Actions artifacts or caches. Fresh two-workbook downloads are globally
budgeted; retrying training reuses the local files without downloading again.
"""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import requests
from .artifact_sync import package_run
from .data import CachedHTTP,atomic_json
from .storage import latest_dashboard
from .simulation import EXPECTED_TEAMS

REPOSITORY='HongQuang26/pitchops'
STATE_PATH='automation/state.json'

class GitHubState:
    def __init__(self,token,repository=REPOSITORY):
        if repository!=REPOSITORY or not token:raise ValueError('Trusted repository and scoped job token required')
        self.token=token;self.repository=repository;self.sha=None;self.state=None
    def request(self,method,path,**kwargs):
        response=requests.request(method,'https://api.github.com/repos/'+self.repository+'/'+path,headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},timeout=(15,90),**kwargs)
        response.raise_for_status();return response.json() if response.content else None
    def read(self):
        body=self.request('GET','contents/'+STATE_PATH,params={'ref':'main'})
        self.sha=body['sha'];self.state=json.loads(base64.b64decode(body['content']));return self.state
    def write(self,state,message='Persist training receipt'):
        body=self.request('PUT','contents/'+STATE_PATH,json={'message':'chore(mlops): '+message+' [skip ci]','branch':'main','sha':self.sha,'content':base64.b64encode(json.dumps(state,indent=2,allow_nan=False).encode()).decode()})
        self.sha=body['content']['sha'];self.state=state
    def reserve(self,url):
        # Atomic compare-and-swap before HTTP; a conflict aborts rather than racing.
        if not url.startswith('https://www.football-data.co.uk/mmz4281/'):return
        waited=0.0
        while True:
            state=self.read();now=time.time();attempts=state.setdefault('provider_attempts',[])
            active=[r for r in attempts if now-float(r['time'])<7*86400 and 'football-data.co.uk' in r['url']]
            if len(active)<2:break
            # Cron jitter around the seven-day boundary must not cost a full week.
            delay=sorted(float(r['time']) for r in active)[-2]+7*86400-now+1
            if delay<=0 or waited+delay>300:raise RuntimeError('Shared football-data two-attempt rolling weekly budget reached')
            pause=min(delay,60.0)
            print(f'Waiting {pause:.0f}s for the existing provider budget window to expire.',flush=True)
            time.sleep(pause);waited+=pause
        state['provider_attempts']=[r for r in attempts if now-float(r['time'])<90*86400]+[{'url':url,'time':now}]
        self.write(state,'reserve provider download before HTTP')


def rolling_seasons(now=None,count=2):
    now=now or datetime.now(timezone.utc);start=now.year if now.month>=7 else now.year-1
    return [f'{year%100:02d}{(year+1)%100:02d}' for year in range(start-count+1,start+1)]

def promotion_gate(payload,config):
    report=payload['metrics'];test=report['test'];baseline=report['test_baseline'];quality=payload['quality']
    values=[test.get('log_loss'),baseline.get('log_loss'),test.get('brier'),test.get('goals_mae')]
    checks={
        'finite_metrics':all(isinstance(v,(int,float)) and math.isfinite(v) for v in values),
        'enough_test_matches':test.get('matches',0)>=config['minimum_test_matches'],
        'baseline_regression_guard':test.get('log_loss',math.inf)<=baseline.get('log_loss',0)*config['maximum_test_log_loss_ratio'],
        'no_duplicate_matches':quality.get('duplicate_matches')==0,
        'no_missing_goal_labels':quality.get('missing_goal_labels')==0,
        'league_coverage':set(config['leagues']).issubset(payload['leagues']),
        'complete_membership':all(len(payload['leagues'].get(code,{}).get('teams',[]))==EXPECTED_TEAMS[code] for code in config['leagues'])
    }
    month=datetime.now(timezone.utc).month
    if month not in {6,7}:checks['result_freshness']=quality.get('snapshot_age_days',999)<=config['maximum_in_season_match_age_days']
    for code,league in payload['leagues'].items():
        checks['probabilities_'+code]=bool(league['forecasts']) and all(abs(f['home_win']+f['draw']+f['away_win']-1)<1e-6 and min(f['home_win'],f['draw'],f['away_win'])>=0 for f in league['forecasts'].values())
    return {'approved':all(checks.values()),'checks':checks,'test_log_loss':test.get('log_loss'),'test_baseline_log_loss':baseline.get('log_loss'),'test_matches':test.get('matches')}

def public_summary(payload,gate):
    return {'run_id':payload['meta']['run_id'],'code_commit':payload['meta']['code_commit'],'training_through':payload['meta']['training_through'],'matches':payload['meta']['matches'],'selected':payload['metrics']['selected'],'quality_gate':gate}

def publish_release(remote,bundle,receipt):
    tag='model-'+receipt['run_id']
    release=remote.request('POST','releases',json={'tag_name':tag,'target_commitish':receipt['code_commit'],'name':'PitchOps model '+receipt['run_id'],'body':'Encrypted personal/academic model delivery. Decrypt in the owner Colab using the key stored on Drive. CI metrics are in the Actions summary.','draft':True,'prerelease':False})
    upload=f'https://uploads.github.com/repos/{remote.repository}/releases/{release["id"]}/assets'
    with Path(bundle).open('rb') as stream:
        response=requests.post(upload,params={'name':'model.enc'},data=stream,headers={'Authorization':'Bearer '+remote.token,'Content-Type':'application/octet-stream'},timeout=(15,180));response.raise_for_status()
    # Publish only after the encrypted asset upload succeeds.
    release=remote.request('PATCH','releases/'+str(release['id']),json={'draft':False,'make_latest':'true'})
    receipt={**receipt,'tag':tag,'asset_url':f'https://github.com/{remote.repository}/releases/download/{tag}/model.enc','release_url':release['html_url']}
    state=remote.read();state['promoted_model']=receipt;remote.write(state,'promote encrypted model after validation')
    return receipt

def train_weekly(root,config,public_pem,remote=None,publish=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    started=datetime.now(timezone.utc).isoformat();previous_pointer=(root/'artifacts'/'latest.json')
    old_pointer=previous_pointer.read_bytes() if previous_pointer.exists() else None
    old_view=root/'artifacts'/'latest_view.json';old_view_bytes=old_view.read_bytes() if old_view.exists() else None
    state=remote.read() if remote else {'schema':1}
    state.update({'last_attempt_at':started,'status':'running','workflow_run_id':os.getenv('GITHUB_RUN_ID')})
    if remote:remote.write(state,'start weekly training')
    previous_guard=CachedHTTP.request_guard
    if remote:CachedHTTP.request_guard=remote.reserve
    payload=None
    try:
        from .pipeline import run
        # Only retry CPU/model work; provider cache hits must satisfy both attempts.
        for attempt in range(config.get('automatic_retries',2)):
            try:
                payload,run_dir=run(root,seasons=rolling_seasons(count=config['history_seasons']),leagues=config['leagues'],simulations=config['simulations'],run_context={'environment':'GitHub Actions' if remote else 'Colab weekly validation','weekly_schedule_utc':config['schedule_utc'],'workflow_run_id':os.getenv('GITHUB_RUN_ID'),'workflow_url':f'https://github.com/{REPOSITORY}/actions/runs/'+os.environ['GITHUB_RUN_ID'] if os.getenv('GITHUB_RUN_ID') else None})
                break
            except (requests.RequestException,RuntimeError):raise
            except Exception:
                if attempt+1>=config.get('automatic_retries',2):raise
                time.sleep(2)
        gate=promotion_gate(payload,config)
        summary=public_summary(payload,gate);atomic_json(root/'weekly_report.json',summary)
        if not gate['approved']:raise ValueError('Deployment quality gate rejected candidate; previous release stays active')
        receipt=package_run(root,payload['meta']['run_id'],public_pem,root/'delivery'/'model.enc')
        if publish:
            if remote is None:raise ValueError('Publishing needs the scoped Actions job token')
            receipt=publish_release(remote,root/'delivery'/'model.enc',receipt)
        state=remote.read() if remote else state
        state.update({'status':'completed','last_success_at':datetime.now(timezone.utc).isoformat(),'last_success':summary})
        if remote:remote.write(state,'complete weekly training')
        atomic_json(root/'weekly_receipt.json',{**receipt,'status':'completed'})
        return {'status':'completed','summary':summary,'receipt':receipt}
    except Exception as exc:
        # Keep local champion pointers too, not just the remote release.
        if old_pointer is not None:previous_pointer.parent.mkdir(parents=True,exist_ok=True);previous_pointer.write_bytes(old_pointer)
        else:previous_pointer.unlink(missing_ok=True)
        if old_view_bytes is not None:old_view.write_bytes(old_view_bytes)
        state=remote.read() if remote else state
        state.update({'status':'failed','failed_at':datetime.now(timezone.utc).isoformat(),'error_type':type(exc).__name__})
        if remote:remote.write(state,'record failed training; retain previous model')
        atomic_json(root/'weekly_failure.json',{'status':'failed','error_type':type(exc).__name__})
        raise
    finally:CachedHTTP.request_guard=previous_guard

def write_summary(value,path):
    if not path:return
    summary=value.get('summary',value);gate=summary.get('quality_gate',{})
    lines=['## PitchOps weekly pipeline','',f"Status: **{value.get('status','verified')}**",'',f"Run: `{summary.get('run_id','validation only')}`",f"Test matches: {gate.get('test_matches','—')}",f"Test log loss: {gate.get('test_log_loss','—')} / baseline {gate.get('test_baseline_log_loss','—')}",'','Data/model bundles are encrypted. Private key remains on Drive.','']
    with Path(path).open('a') as stream:stream.write('\n'.join(lines))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--config',default='config/weekly.json');parser.add_argument('--mode',choices=['train','verify'],default='train');parser.add_argument('--no-publish',action='store_true')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text());public=Path(config['artifact_recipient']).read_bytes()
    # Parse/validate recipient before any provider request.
    from .artifact_sync import encrypt_bytes
    encrypt_bytes(b'preflight',public)
    if args.mode=='verify':
        report={'status':'verified','configuration':{'schedule':config['schedule_vietnam'],'seasons':rolling_seasons(),'leagues':config['leagues']}}
        if os.getenv('GITHUB_ACTIONS')=='true':
            remote=GitHubState(os.environ['GITHUB_TOKEN']);state=remote.read()
            state['verification']={'status':'passed','at':datetime.now(timezone.utc).isoformat(),'workflow_run_id':os.getenv('GITHUB_RUN_ID')}
            remote.write(state,'verify scheduled runner configuration and write access')
    else:
        remote=GitHubState(os.environ['GITHUB_TOKEN']) if os.getenv('GITHUB_ACTIONS')=='true' else None
        report=train_weekly(args.root,config,public,remote=remote,publish=not args.no_publish)
    write_summary(report,os.getenv('GITHUB_STEP_SUMMARY'))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
