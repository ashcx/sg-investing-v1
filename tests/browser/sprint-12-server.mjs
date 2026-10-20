// Fixed-data review of the actual frontend. No market API or production data
// writes. Run: node tests/browser/sprint-12-server.mjs [port=4174]
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';
import { fixture, manifest, pack } from '../fixtures/redesign/sprint-12-packs.mjs';

const port = Number(process.argv[2] || 4174);
const root = fileURLToPath(new URL('../../frontend/', import.meta.url));
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml' };
createServer(async (req, res) => {
  const send = (status, body, type = 'application/json') => {
    res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' });
    res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
  };
  const path = new URL(req.url, `http://127.0.0.1:${port}`).pathname;
  if (path === '/data/catalog.json') return send(200, { securities: fixture.securities.map(item => ({ universe: 'synthetic_review', security: item.security })) });
  if (path.endsWith('/data/packs/manifest.json')) return send(200, manifest(path.startsWith('/tier2/')));
  if (path.includes('/data/packs/security=')) {
    const item = fixture.securities.find(item => path.includes(item.security.security_id));
    if (!item || !path.endsWith('year=2024.json')) return send(404, { error: 'No fixture pack for this year' });
    if (item.security.ticker === 'BROKEN') {
      // Leave time to inspect queued/loading cards and invalidate an in-flight run.
      await new Promise(resolve => setTimeout(resolve, 1500));
      return send(503, { error: 'Deliberate fixture pack failure' });
    }
    if (item.security.ticker === 'REMOTE' && !path.startsWith('/tier2/')) return send(404, {});
    return send(200, pack(item));
  }
  if (path === '/data/data-status.json') return send(200, { backfill: { as_of: '2024-05-01' } });
  if (path.startsWith('/api/')) return send(400, { error: 'Review server is static mode only' });
  const file = resolve(root, `.${decodeURIComponent(path === '/' ? '/index.html' : path)}`);
  if (!file.startsWith(root.endsWith(sep) ? root : root + sep)) return send(403, {});
  try {
    let body = await readFile(file);
    if (file.endsWith('index.html')) body = body.toString()
      .replace(/(<meta name="sg-invest-pack-base" content=")[^"]*/, `$1http://127.0.0.1:${port}/tier2`)
      .replace('<title>', '<title>Synthetic fixture review — ');
    send(200, body, mime[extname(file)] || 'application/octet-stream');
  } catch { send(404, { error: 'No such review asset' }); }
}).listen(port, '127.0.0.1', () => console.log(`Synthetic Sprint 12 review: http://127.0.0.1:${port}/#compare`));
