import http from 'k6/http';
import { check } from 'k6';
import { sha256 } from 'k6/crypto';

const profile = __ENV.PROFILE || 'smoke';
const profiles = {
  smoke: { vus: Number(__ENV.VUS || 5), duration: __ENV.DURATION || '15s' },
  spike: { stages: [{ duration: '10s', target: 100 }, { duration: '20s', target: 100 }, { duration: '10s', target: 0 }] },
};
if (!(profile in profiles)) throw new Error('PROFILE debe ser smoke o spike');
export const options = {
  ...profiles[profile],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    http_req_duration: [`p(95)<${Number(__ENV.P95_MS || 2000)}`],
  },
};

const base = (__ENV.BASE_URL || 'http://documents.universidad.localhost').replace(/\/$/, '');
const runId = __ENV.RUN_ID;
if (!runId) throw new Error('Definir RUN_ID único para esta ejecución');
const content = '# Documento de carga\n' + 'x'.repeat(Number(__ENV.CONTENT_BYTES || 1024));
const token = __ENV.DOCUMENTS_API_TOKEN;
if (!token) throw new Error('Definir DOCUMENTS_API_TOKEN para esta ejecución');

export default function () {
  const checksum = sha256(`${runId}-${__VU}-${__ITER}`, 'hex');
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'X-Request-ID': `load-${runId}-${__VU}-${__ITER}`,
    },
    timeout: '5s',
  };
  const created = http.post(`${base}/documents`, JSON.stringify({
    checksum, content, page_count: 1,
    filename: 'load-test.pdf',
  }), params);
  if (!check(created, { 'creado 201': r => r.status === 201 })) return;
  const documentId = created.json('id');
  const found = http.get(`${base}/documents/by-checksum/${checksum}`, params);
  check(found, {
    'consulta 200': r => r.status === 200,
    'mismo documento': r => r.status === 200 && r.json('id') === documentId,
  });
  const deleted = http.del(`${base}/documents/${documentId}`, null, params);
  check(deleted, { 'eliminado 204': r => r.status === 204 });
}
