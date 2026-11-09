"""Validate a built image using disposable MongoDB and HTTP containers.

Usage: python3 scripts/validate_container.py --image pdf-document-service-hardened:local
Requires Docker and mongo:7.0.45. Does not modify the shared deployment.
"""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', default='pdf-document-service-hardened:local')
args = parser.parse_args()
run = 'documents-review-' + uuid.uuid4().hex[:10]
net = run + '-net'
mongo = run + '-mongo'
api = run + '-api'

def docker(*args, check=True):
    return subprocess.run(['docker', *args], text=True, capture_output=True, check=check).stdout.strip()

def http(path, method='GET', data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return (response.status, response.read())
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read())

def wait_ready():
    for _ in range(60):
        try:
            if http('/health/ready')[0] == 200:
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise RuntimeError('readiness timeout: ' + docker('logs', api))
try:
    docker('network', 'create', net)
    docker('run', '-d', '--name', mongo, '--network', net, 'mongo:7.0.45')
    for _ in range(60):
        if subprocess.run(['docker', 'exec', mongo, 'mongosh', '--quiet', '--eval', 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)'], capture_output=True).returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('MongoDB startup timeout')
    token = 'temporary-runtime-test-token-' + uuid.uuid4().hex
    docker('run', '-d', '--name', api, '--network', net, '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m', '-p', '127.0.0.1::8123', '-e', 'PORT=8123', '-e', 'MONGODB_URI=mongodb://' + mongo + ':27017', '-e', 'DOCUMENTS_API_TOKEN=' + token, args.image)
    base = 'http://127.0.0.1:' + docker('port', api, '8123/tcp').split(':')[-1]
    wait_ready()
    assert http('/health/live')[0] == 200
    assert http('/documents')[0] == 401
    assert http('/documents', token='incorrect')[0] == 401
    payload = {'checksum': 'a' * 64, 'content': '# smoke', 'page_count': 1}
    code, body = http('/documents', 'POST', payload, token)
    assert code == 201, (code, body)
    document = json.loads(body)
    doc_id = document['id']
    assert http('/documents', 'POST', payload, token)[0] == 200
    assert http('/documents/' + doc_id, token=token)[0] == 200
    assert http('/documents/' + doc_id, 'PATCH', {'filename': 'updated.pdf'}, token)[0] == 200
    assert http('/documents/by-checksum/' + 'a' * 64, token=token)[0] == 200
    assert http('/documents', token=token)[0] == 200
    assert docker('exec', api, 'python', '-c', "import os, importlib.util; assert os.getuid()==10001; assert importlib.util.find_spec('pytest') is None; assert importlib.util.find_spec('pip') is None; assert not os.access('/app/app/main.py',os.W_OK); print('runtime privileges OK')") == 'runtime privileges OK'
    docker('stop', '-t', '5', mongo)
    assert http('/health/live')[0] == 200
    assert http('/health/ready')[0] == 503
    assert http('/documents/' + doc_id, token=token)[0] == 503
    docker('start', mongo)
    wait_ready()
    assert http('/documents/' + doc_id, token=token)[0] == 200
    assert http('/documents/' + doc_id, 'DELETE', token=token)[0] == 204
    missing = run + '-missing-secret'
    docker('run', '-d', '--name', missing, '--network', net, args.image)
    try:
        for _ in range(120):
            state = json.loads(docker('inspect', missing))[0]['State']
            if not state['Running']:
                break
            time.sleep(0.5)
        assert not state['Running'] and state['ExitCode'] != 0, state
        assert 'DOCUMENTS_API_TOKEN' in docker('logs', missing) + subprocess.run(['docker', 'logs', missing], capture_output=True, text=True).stderr
    finally:
        docker('rm', '-f', missing, check=False)
    assert token not in docker('logs', api)
    print('PASS: HTTP CRUD, Bearer, read-only non-root runtime, database outage/recovery, persistence, startup without secret')
finally:
    for name in [api, mongo]:
        docker('rm', '-f', '-v', name, check=False)
    docker('network', 'rm', net, check=False)
