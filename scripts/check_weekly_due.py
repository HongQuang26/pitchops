"""Skip recovery runs after a recent success; manual verify never fetches data."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from pitchops.weekly import GitHubState

mode=os.environ.get('PITCHOPS_MODE','verify')
event=os.environ.get('GITHUB_EVENT_NAME','workflow_dispatch')
state=GitHubState(os.environ['GITHUB_TOKEN']).read()
last=state.get('last_success_at')
recent=last and (datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()<6*86400
run=not (event=='schedule' and recent)
with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:stream.write('run='+str(run).lower()+'\n')
if not run:
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write('Weekly recovery check: recent successful training exists; no downloads or retraining needed.\n')
print(json.dumps({'mode':mode,'run':run,'last_success_at':last}))
