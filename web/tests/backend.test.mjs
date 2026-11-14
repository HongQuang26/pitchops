import test from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {createStore,decodeSnapshot,trustedAsset} from '../server/store.mjs';
import {routeData,encodeResponse} from '../server/api.mjs';
import handler from '../../api/index.mjs';

function bundle(id='one') {
  const snapshot={schema:1,meta:{run_id:id,training_through:'2026-11-08'},publication:{quality_gate:{approved:true},raw_match_data:false,model_weights:false},metrics:{selected:'baseline'},leagues:{E0:{name:'Premier League',teams:['A','B'],forecasts:{'A|B':{home_win:.5,draw:.3,away_win:.2}}}},research:{as_of:'2022-12-15',forecasts:{one:1},spatial:{one:2},team_players:{A:[]}}};
  const bytes=gzipSync(JSON.stringify(snapshot));
  const receipt={format:'pitchops-web-gzip-v1',run_id:id,quality_gate:{approved:true},bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),asset_url:`https://github.com/HongQuang26/pitchops/releases/download/model-${id}/web.json.gz`};
  return {bytes,receipt,snapshot};
}
const loaded=snapshot=>({snapshot,status:{ready:true,run_id:snapshot.meta.run_id,data_age_days:6,dataset_id:'hash'},registry:{status:'completed'}});

test('Reject corrupt or unapproved snapshots and foreign release URLs',()=>{
  const item=bundle();assert.deepEqual(decodeSnapshot(item.bytes,item.receipt),item.snapshot);
  assert.throws(()=>decodeSnapshot(Buffer.from('corrupt'),item.receipt));
  assert.throws(()=>decodeSnapshot(item.bytes,{...item.receipt,quality_gate:{approved:false}}));
  assert.equal(trustedAsset(item.receipt.asset_url),true);
  for(const url of ['https://evil.com/model-one/web.json.gz','https://github.com/other/repo/releases/download/model-one/web.json.gz',item.receipt.asset_url+'?redirect=evil'])assert.equal(trustedAsset(url),false);
});
test('Serve the approved bootstrap through an origin outage',async()=>{
  const first=bundle();let calls=0;
  const store=createStore({bootstrap:async()=>first,fetchImpl:async()=>{calls++;throw new Error('offline');},now:()=>1_900_000_000_000});
  const results=await Promise.all([store.load(),store.load(),store.load()]);
  assert.equal(calls,1);assert.equal(results[0].status.degraded,true);assert.equal(results[0].snapshot.meta.run_id,'one');
});
test('Follow a new approved release without a source redeploy',async()=>{
  const first=bundle(),second=bundle('two');let calls=0;
  const store=createStore({bootstrap:async()=>first,fetchImpl:async url=>{calls++;return new Response(url.endsWith('state.json')?JSON.stringify({status:'completed',promoted_web:second.receipt}):second.bytes);},now:()=>1_900_000_000_000});
  const result=await store.load();assert.equal(result.snapshot.meta.run_id,'two');assert.equal(result.status.source,'github-release');assert.equal(calls,2);
});
test('Keep prior approved release when a newly advertised asset is corrupted',async()=>{
  const first=bundle(),second=bundle('two');let time=1_900_000_000_000;
  const store=createStore({bootstrap:async()=>first,fetchImpl:async url=>new Response(url.endsWith('state.json')?JSON.stringify({promoted_web:second.receipt}):'bad'),now:()=>time});
  const result=await store.load();assert.equal(result.snapshot.meta.run_id,'one');assert.equal(result.status.degraded,true);
});
test('API validates team identity, exposes usable predictions and has bounded responses',()=>{
  const item=bundle();const get=query=>routeData(new URL('https://example.test/api/'+query),loaded(item.snapshot));
  assert.equal(get('predict?league=E0&home=A&away=B').body.forecast.home_win,.5);
  assert.equal(get('predict?league=E0&home=A&away=A').status,400);
  assert.equal(get('predict?league=E0&home=A&away=unknown').status,404);
  assert.equal(get('league?league=__proto__').status,404);
  assert.equal(get('bootstrap').body.leagues.E0.forecasts,undefined);
  assert.equal(get('research?part=overview').body.forecasts,undefined);
  assert.equal(get('research?part=spatial').body.spatial.one,2);
  assert.equal(encodeResponse({status:200,body:'x'.repeat(4_000_001)}).status,413);
});
test('Public API does not accept write or training requests',async()=>{
  const response={headers:{},setHeader(key,value){this.headers[key]=value;},status(code){this.code=code;return this;},json(body){this.body=body;return this;}};
  await handler({method:'POST',url:'/api/predict'},response);
  assert.equal(response.code,405);assert.equal(response.headers.Allow,'GET, HEAD');
});

test('UCL API keeps its own model cutoff and filters actual fixtures',()=>{
  const item=bundle();
  item.snapshot.leagues.UCL={name:'UEFA Champions League',teams:['A','B'],meta:{run_id:'ucl-1',training_through:'2026-11-04'},forecasts:{'A|B':{home_win:.6}},fixtures:[{id:'1',home:'A',away:'B',status:'completed'},{id:'2',home:'B',away:'A',status:'pre'}]};
  const get=path=>routeData(new URL('https://test/api/'+path),loaded(item.snapshot));
  assert.equal(get('predict?league=UCL&home=A&away=B').body.training_through,'2026-11-04');
  assert.equal(get('predict?league=UCL&home=A&away=B').body.model_run_id,'ucl-1');
  assert.deepEqual(get('fixtures?league=UCL&team=A&status=upcoming').body.fixtures.map(f=>f.id),['2']);
  assert.equal(get('fixtures?league=UCL&team=unknown').status,404);
  assert.equal(get('fixtures?league=UCL&status=bad').status,400);
  assert.equal(get('fixtures?league=__proto__').status,404);
  assert.equal(get('fixtures?league=E0').body.available,false);
});
