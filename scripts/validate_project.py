"""Offline project validation: notebooks and workflows, with no provider calls."""
import ast
import json
from pathlib import Path
import subprocess
import yaml

root=Path(__file__).resolve().parents[1]
for path in (root/'notebooks').glob('*.ipynb'):
    book=json.loads(path.read_text())
    for index,cell in enumerate(book['cells']):
        if cell['cell_type']=='code':ast.parse(''.join(cell['source']),filename=f'{path.name}:cell{index}')
for path in (root/'.github'/'workflows').glob('*.yml'):
    data=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    if not isinstance(data,dict) or not {'on','jobs'}.issubset(data):raise ValueError('Invalid workflow: '+path.name)
for path in (root/'src'/'pitchops').glob('*.js'):
    subprocess.run(['node','--check',str(path)],check=True)
print('Notebook Python, workflow YAML and dashboard JavaScript syntax verified.')
