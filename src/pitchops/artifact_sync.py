"""Encrypted model delivery: CI needs only a public recipient; private key stays on Drive.

The public repository hosts ciphertext and aggregate receipts. No Drive OAuth or
long-lived GitHub token is required. Only trust releases from your own repository.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import tarfile
import tempfile
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .data import atomic_json

MAGIC=b'PITCHOPS-ENC-1\n'
MAX_BYTES=250_000_000

def recipient_keys(root):
    directory=Path(root)/'.keys';directory.mkdir(parents=True,exist_ok=True)
    private=directory/'artifact-private.pem';public=directory/'artifact-public.pem'
    if not private.exists():
        key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        with private.open('xb') as stream:
            stream.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        private.chmod(0o600)
    key=serialization.load_pem_private_key(private.read_bytes(),password=None)
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    return private,public

def fingerprint(public_pem):return hashlib.sha256(public_pem).hexdigest()

def encrypt_bytes(plain,public_pem):
    public=serialization.load_pem_public_key(public_pem)
    if not isinstance(public,rsa.RSAPublicKey) or public.key_size<3072:raise ValueError('RSA recipient must be at least 3072 bits')
    aes=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
    wrapped=public.encrypt(aes,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=MAGIC))
    return MAGIC+struct.pack('>I',len(wrapped))+wrapped+nonce+AESGCM(aes).encrypt(nonce,plain,MAGIC)

def decrypt_bytes(cipher,private_pem):
    if not cipher.startswith(MAGIC) or len(cipher)>MAX_BYTES:raise ValueError('Invalid or excessive artifact')
    offset=len(MAGIC);size=struct.unpack('>I',cipher[offset:offset+4])[0];offset+=4
    if size<256 or size>1024 or len(cipher)<offset+size+28:raise ValueError('Invalid encrypted envelope')
    private=serialization.load_pem_private_key(private_pem,password=None)
    aes=private.decrypt(cipher[offset:offset+size],padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=MAGIC));offset+=size
    return AESGCM(aes).decrypt(cipher[offset:offset+12],cipher[offset+12:],MAGIC)

def package_run(root,run_id,public_pem,output):
    root=Path(root);run=root/'artifacts'/'runs'/run_id
    if not run.is_dir() or Path(run_id).name!=run_id:raise ValueError('Invalid model run')
    payload=json.loads((run/'snapshot.json').read_text());model_meta=payload['meta']
    if model_meta['run_id']!=run_id:raise ValueError('Model identity mismatch')
    file_hashes={};archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as tar:
        for path in sorted(run.rglob('*')):
            if not path.is_file():continue
            if path.is_symlink():raise ValueError('No symlinks in model archives')
            name=path.relative_to(root).as_posix()
            file_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            tar.add(path,arcname=name,recursive=False)
        manifest={'schema':1,'run_id':run_id,'files':file_hashes,'created_at':model_meta['created_at'],'code_commit':model_meta['code_commit']}
        encoded=json.dumps(manifest,sort_keys=True).encode();info=tarfile.TarInfo('bundle_manifest.json');info.size=len(encoded);tar.addfile(info,io.BytesIO(encoded))
    plain=archive.getvalue()
    if len(plain)>MAX_BYTES:raise ValueError('Model bundle too large')
    encrypted=encrypt_bytes(plain,public_pem);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(encrypted)
    return {'run_id':run_id,'created_at':model_meta['created_at'],'code_commit':model_meta['code_commit'],'sha256':hashlib.sha256(encrypted).hexdigest(),'recipient_sha256':fingerprint(public_pem),'bytes':len(encrypted),'file_count':len(file_hashes)}

def unpack_run(plain,destination,expected_run):
    """Extract only the declared model run; reject traversal, links and archive bombs."""
    destination=Path(destination);prefix='artifacts/runs/'+expected_run+'/'
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as tar:
        members=[];total=0
        for member in tar:
            total+=member.size
            if len(members)>=1000 or total>MAX_BYTES:raise ValueError('Archive size limit exceeded')
            members.append(member)
        names=set()
        for member in members:
            path=PurePosixPath(member.name)
            if member.name in names or path.is_absolute() or '..' in path.parts or not member.isfile():raise ValueError('Unsafe archive member')
            names.add(member.name)
            if member.name!='bundle_manifest.json' and not member.name.startswith(prefix):raise ValueError('Archive outside expected model run')
        manifest=json.load(tar.extractfile('bundle_manifest.json'))
        if manifest['run_id']!=expected_run or names!={'bundle_manifest.json',*manifest['files']}:raise ValueError('Manifest membership mismatch')
        for name,digest in manifest['files'].items():
            content=tar.extractfile(name).read()
            if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Artifact checksum mismatch')
            path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    return destination/'artifacts'/'runs'/expected_run

def import_bundle(root,cipher,receipt,private_pem):
    root=Path(root)
    if hashlib.sha256(cipher).hexdigest()!=receipt['sha256']:raise ValueError('Release hash mismatch')
    key=serialization.load_pem_private_key(private_pem,password=None)
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    if fingerprint(public)!=receipt['recipient_sha256']:raise ValueError('This release belongs to another recipient')
    plain=decrypt_bytes(cipher,private_pem)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pitchops-import-') as stage:
        incoming=unpack_run(plain,stage,receipt['run_id'])
        payload=json.loads((incoming/'snapshot.json').read_text())
        if payload['meta']['run_id']!=receipt['run_id']:raise ValueError('Snapshot identity mismatch')
        from .storage import latest_dashboard
        try:old,_=latest_dashboard(root)
        except FileNotFoundError:old={}
        if old and datetime.fromisoformat(old['meta']['created_at'])>datetime.fromisoformat(payload['meta']['created_at']):
            return {'status':'older_than_local','run_id':old['meta']['run_id']}
        target=root/'artifacts'/'runs'/receipt['run_id']
        if target.exists():
            for path in incoming.rglob('*'):
                if path.is_file() and (not (target/path.relative_to(incoming)).exists() or hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256((target/path.relative_to(incoming)).read_bytes()).digest()):raise FileExistsError('Conflicting immutable model run')
        else:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(incoming,target)
        # Independent historical research and media remain explicitly timestamped.
        for name in ['media','research']:
            if name in old and name not in payload:payload[name]=old[name]
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        view=root/'artifacts'/'views'/(receipt['run_id']+'-sync-'+stamp);view.mkdir(parents=True,exist_ok=False)
        payload['meta'].update({'workspace':str(root),'persistent_drive':str(root).startswith('/content/drive/MyDrive/'),'delivery':'GitHub Actions encrypted release','release_tag':receipt.get('tag')})
        atomic_json(view/'snapshot.json',payload)
        from .dashboard import render_dashboard
        render_dashboard(payload,view/'dashboard.html')
        atomic_json(view/'source_run.json',{'model_run_id':receipt['run_id'],'delivery_receipt':receipt})
        atomic_json(root/'artifacts'/'latest.json',{'run_id':receipt['run_id'],'snapshot':str(target/'snapshot.json')})
        atomic_json(root/'artifacts'/'latest_view.json',{'model_run_id':receipt['run_id'],'view_id':view.name})
        atomic_json(root/'artifacts'/'delivery_receipt.json',receipt)
    return {'status':'updated','run_id':receipt['run_id'],'dashboard':str(view/'dashboard.html')}

def sync_latest(root,repository='HongQuang26/pitchops'):
    """Download only this repository's promoted encrypted release, then import to Drive."""
    if repository!='HongQuang26/pitchops':raise ValueError('Explicit repository allowlist required for a different project')
    response=requests.get(f'https://raw.githubusercontent.com/{repository}/main/automation/state.json',timeout=(10,30));response.raise_for_status()
    state=response.json();receipt=state.get('promoted_model')
    if not receipt:return {'status':'no_promoted_model'}
    existing=Path(root)/'artifacts'/'delivery_receipt.json'
    if existing.exists() and json.loads(existing.read_text()).get('sha256')==receipt['sha256']:return {'status':'up_to_date','run_id':receipt['run_id']}
    private,public=recipient_keys(root)
    if fingerprint(public.read_bytes())!=receipt['recipient_sha256']:raise ValueError('Keep the original artifact key from Drive; this release is for a different key')
    expected=f'https://github.com/{repository}/releases/download/{receipt["tag"]}/model.enc'
    if receipt['asset_url']!=expected:raise ValueError('Release URL outside the expected repository')
    response=requests.get(expected,timeout=(15,120),stream=True);response.raise_for_status();chunks=[];total=0
    for chunk in response.iter_content(1024*1024):
        total+=len(chunk)
        if total>MAX_BYTES:raise ValueError('Excessive release download')
        chunks.append(chunk)
    return import_bundle(root,b''.join(chunks),receipt,private.read_bytes())
