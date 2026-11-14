import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';

export const REPOSITORY = 'HongQuang26/pitchops';
const REGISTRY = `https://raw.githubusercontent.com/${REPOSITORY}/main/automation/state.json`;
const MAX_COMPRESSED = 8_000_000, MAX_DECODED = 24_000_000;
const sha256 = value => createHash('sha256').update(value).digest('hex');

export function decodeSnapshot(bytes, receipt) {
  if (!receipt || receipt.format !== 'pitchops-web-gzip-v1' || !receipt.quality_gate?.approved) throw new Error('Unapproved web receipt');
  if (bytes.length > MAX_COMPRESSED || bytes.length !== receipt.bytes || sha256(bytes) !== receipt.sha256) throw new Error('Web checksum mismatch');
  const snapshot = JSON.parse(gunzipSync(bytes, {maxOutputLength:MAX_DECODED}).toString('utf8'));
  if (snapshot.schema !== 1 || snapshot.meta?.run_id !== receipt.run_id || !snapshot.publication?.quality_gate?.approved || !snapshot.leagues || !snapshot.metrics) throw new Error('Invalid web snapshot');
  if (snapshot.publication.model_weights !== false || snapshot.publication.raw_match_data !== false) throw new Error('Unexpected private payload');
  return snapshot;
}

export function trustedAsset(value) {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'github.com' && !url.username && !url.password && !url.search && !url.hash && new RegExp(`^/${REPOSITORY}/releases/download/model-[A-Za-z0-9_-]+/web\\.json\\.gz$`).test(url.pathname);
  } catch { return false; }
}

async function boundedFetch(fetchImpl, url, maximum) {
  const response = await fetchImpl(url, {signal:AbortSignal.timeout(8000),headers:{'User-Agent':'PitchOps approved snapshot reader','Accept':'application/octet-stream'}});
  if (!response.ok) throw new Error('Snapshot origin unavailable');
  if (Number(response.headers.get('content-length')) > maximum) throw new Error('Origin response too large');
  const chunks = []; let total = 0;
  if (!response.body) throw new Error('Empty origin response');
  for await (const chunk of response.body) {
    total += chunk.length;
    if (total > maximum) throw new Error('Origin response too large');
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

async function localBootstrap() {
  const [bytes, manifest] = await Promise.all([
    readFile(new URL('../bootstrap.json.gz',import.meta.url)),
    readFile(new URL('../bootstrap.manifest.json',import.meta.url),'utf8')
  ]);
  return {bytes, receipt:JSON.parse(manifest)};
}

// Memory is a per-instance optimization. Durable truth is the checked GitHub
// release; every cold instance can fall back to the deployed approved bootstrap.
export function createStore({fetchImpl=fetch, bootstrap=localBootstrap, now=Date.now, refreshMs=300_000}={}) {
  let current, receipt, source='bootstrap', checkedAt=0, registry={}, degraded=false, pending;
  async function refresh() {
    if (!current) {
      const initial = await bootstrap();
      current = decodeSnapshot(initial.bytes,initial.receipt); receipt = initial.receipt;
    }
    if (now()-checkedAt < refreshMs) return;
    checkedAt = now();
    try {
      const raw = await boundedFetch(fetchImpl,REGISTRY,150_000);
      const nextRegistry = JSON.parse(raw.toString('utf8'));
      const next = nextRegistry.promoted_web;
      if (next && next.sha256 !== receipt.sha256) {
        if (!trustedAsset(next.asset_url)) throw new Error('Untrusted release URL');
        const bytes = await boundedFetch(fetchImpl,next.asset_url,MAX_COMPRESSED);
        const candidate = decodeSnapshot(bytes,next);
        current = candidate; receipt = next; source = 'github-release';
      }
      registry = nextRegistry; degraded = false;
    } catch {
      // Last approved snapshot stays usable, including after an origin outage.
      degraded = true;
    }
  }
  return {
    async load() {
      if (!pending) pending = refresh().finally(() => { pending = undefined; });
      await pending;
      const age = Math.max(0,Math.floor((now()-Date.parse(current.meta.training_through+'T00:00:00Z'))/86400000));
      return {snapshot:current, receipt, status:{ready:true,source,degraded,dataset_id:receipt.sha256,run_id:receipt.run_id,training_through:current.meta.training_through,data_age_days:age,last_checked_at:new Date(checkedAt).toISOString()}, registry};
    }
  };
}

export const store = createStore();
