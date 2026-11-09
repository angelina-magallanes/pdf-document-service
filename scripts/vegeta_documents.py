"""Carga fija de lectura de Documents; requiere vegeta y una base de pruebas aislada."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import uuid


def request(url, token, payload=None, method='GET'):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
    })
    return urllib.request.urlopen(req, timeout=10)


def run(args):
    token = os.environ['DOCUMENTS_API_TOKEN']
    base = args.base_url.rstrip('/')
    payload = {'checksum': uuid.uuid4().hex + uuid.uuid4().hex,
               'content': '# Lectura de carga\n' + 'x' * args.content_bytes, 'page_count': 1}
    with request(base + '/documents', token, payload, 'POST') as response:
        document_id = json.load(response)['id']
    url = base + '/documents/' + document_id
    try:
        with tempfile.TemporaryDirectory(prefix='documents-vegeta-') as folder:
            target = Path(folder) / 'targets.txt'
            target.write_text(f'GET {url}\nAuthorization: Bearer {token}\n\n')
            target.chmod(0o600)
            attack = subprocess.run(['vegeta', 'attack', '-targets', str(target), '-rate', args.rate,
                                     '-duration', args.duration, '-timeout', '30s'], check=True, capture_output=True)
            report = subprocess.run(['vegeta', 'report', '-type=json'], input=attack.stdout,
                                    check=True, capture_output=True)
            args.output.write_bytes(report.stdout)
            print(f'Resultado de lectura Documents: {args.output}')
    finally:
        with request(url, token, method='DELETE'):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--rate', default='50/s')
    parser.add_argument('--duration', default='30s')
    parser.add_argument('--content-bytes', type=int, default=1024)
    parser.add_argument('--output', type=Path, default=Path('/tmp/documents-vegeta.json'))
    parser.add_argument('--isolated-test-database', action='store_true', required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
