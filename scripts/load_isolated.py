"""Carga k6 sobre Documents y MongoDB temporales, sin puertos ni datos compartidos."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def docker(*arguments, **kwargs):
    return subprocess.run(['docker', *arguments], check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def wait_ready(container):
    code = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).close()"
    for _ in range(60):
        result = subprocess.run(['docker', 'exec', container, 'python', '-c', code], capture_output=True)
        if result.returncode == 0:
            return
        time.sleep(.5)
    raise RuntimeError('Documents no alcanzó readiness; revisar la imagen y su configuración')


def start_services(context):
    name, env, image = context['name'], context['env'], context['image']
    docker('network', 'create', '--internal', name)
    docker('run', '-d', '--name', name+'-mongo', '--network', name, '--network-alias', 'mongodb',
           '--memory', '512m', 'mongo:7.0.45')
    for _ in range(60):
        result = subprocess.run(['docker', 'exec', name+'-mongo', 'mongosh', '--quiet', '--eval',
                                 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)'], capture_output=True)
        if result.returncode == 0:
            break
        time.sleep(.5)
    docker('run', '-d', '--name', name+'-documents', '--network', name, '--network-alias', 'documents',
           '--cpus', '1', '--memory', '1g', '--read-only', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges:true', '-e', 'DOCUMENTS_API_TOKEN',
           '-e', 'MONGODB_URI=mongodb://mongodb:27017', '-e', 'MONGODB_DATABASE='+name.replace('-', '_'),
           image, env=env)
    wait_ready(name+'-documents')


def measure(context, args):
    name, env, folder = context['name'], context['env'], context['folder']
    docker('create', '--name', name+'-k6', '--network', name, '--cpus', '1', '--memory', '256m',
           '-e', 'DOCUMENTS_API_TOKEN', '-e', 'RUN_ID='+name, '-e', 'BASE_URL=http://documents:8000',
           '-e', 'PROFILE='+args.profile, '-e', 'CONTENT_BYTES='+str(args.content_bytes),
           '-v', str(ROOT/'tests/stress/documents.js')+':/test.js:ro', args.k6_image,
           'run', '--summary-export=/tmp/summary.json', '/test.js', env=env)
    with (folder/'k6.log').open('w') as log:
        process = subprocess.Popen(['docker', 'start', '-a', name+'-k6'], stdout=log, stderr=log)
        samples = []
        while process.poll() is None:
            sample = docker('stats', '--no-stream', '--format', '{{json .}}', name+'-documents')
            samples.append({'time': time.time(), 'stats': json.loads(sample)})
        process.wait()
    (folder/'resources.json').write_text(json.dumps(samples, indent=2))
    docker('cp', name+'-k6:/tmp/summary.json', str(folder/'k6-summary.json'))
    code = "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/metrics',headers={'Authorization':'Bearer '+os.environ['DOCUMENTS_API_TOKEN']}); print(urllib.request.urlopen(r).read().decode())"
    metrics = subprocess.run(['docker', 'exec', name+'-documents', 'python', '-c', code], capture_output=True, text=True)
    if metrics.returncode == 0:
        (folder/'metrics.prom').write_text(metrics.stdout)
    exit_code = int(docker('inspect', '--format', '{{.State.ExitCode}}', name+'-k6'))
    return exit_code


def run(args):
    name = 'documents-load-'+uuid.uuid4().hex[:10]
    folder = ROOT/'.integration'/'load'/name
    folder.mkdir(parents=True)
    context = {'name': name, 'folder': folder, 'image': args.image,
               'env': {**os.environ, 'DOCUMENTS_API_TOKEN': secrets.token_urlsafe(32)}}
    report = {'run': name, 'profile': args.profile, 'content_bytes': args.content_bytes,
              'documents_image': docker('image', 'inspect', '--format', '{{.Id}}', args.image),
              'k6_image': docker('image', 'inspect', '--format', '{{.Id}}', args.k6_image),
              'replicas': 1, 'cpu_limit': 1, 'memory_limit': '1GiB', 'passed': False}
    try:
        start_services(context)
        report['passed'] = measure(context, args) == 0
    finally:
        cleanup = [subprocess.run(['docker', 'rm', '-f', '-v', name+suffix], capture_output=True).returncode
                   for suffix in ('-k6', '-documents', '-mongo')]
        cleanup.append(subprocess.run(['docker', 'network', 'rm', name], capture_output=True).returncode)
        report['cleanup_ok'] = not any(cleanup)
        (folder/'report.json').write_text(json.dumps(report, indent=2))
        print('Resultado:', folder)
    if not report['passed'] or not report['cleanup_ok']:
        raise SystemExit('La carga no aprobó los umbrales; revisar resultados')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--k6-image', default='grafana/k6@sha256:3e4186aea62e11a45560bfc51e19eeafe82fc07ce069c78aff44b7ff893d9a5e')
    parser.add_argument('--profile', choices=['smoke', 'spike'], default='smoke')
    parser.add_argument('--content-bytes', type=int, default=1024)
    run(parser.parse_args())
