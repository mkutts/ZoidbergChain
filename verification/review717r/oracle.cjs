/* Independent Node encoder + SHA-256 oracle. No Python imports or signing. */
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '../../tests/fixtures/review717r_v1');
const schema = JSON.parse(fs.readFileSync(path.join(root, 'schema.json')));
const fixtures = JSON.parse(fs.readFileSync(path.join(root, 'vectors.json')));
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const tag = (t, b) => hash(Buffer.concat([Buffer.from('ZCRJ717R\0'+t+'\0'), b]));
function integer(v, width, signed=false) {
  assert(Number.isSafeInteger(v));
  let n = BigInt(v);
  if (signed && n < 0) n += 1n << BigInt(width*8);
  const out = Buffer.alloc(width);
  for(let i=width-1; i>=0; --i) { out[i]=Number(n & 255n); n >>= 8n; }
  assert.equal(n, 0n);
  return out;
}
function encode(t, v) {
  if(typeof t === 'number') {
    assert.match(v, new RegExp('^[0-9a-f]{'+t*2+'}$'));
    return Buffer.from(v, 'hex');
  }
  if(Array.isArray(t)) {
    assert(Array.isArray(v) && v.length >= t[2] && v.length <= t[3]);
    return Buffer.concat([integer(v.length, 1), ...v.map(x => encode(t[1], x))]);
  }
  if(schema.schemas[t]) {
    assert.deepEqual(Object.keys(v).sort(), schema.schemas[t].map(x => x[0]).sort());
    return Buffer.concat(schema.schemas[t].map(([k,type]) => encode(type, v[k])));
  }
  if(t === 'nid') {
    assert.match(v, /^[a-z0-9][a-z0-9-]{2,63}$/);
    return Buffer.concat([integer(v.length, 1), Buffer.from(v), Buffer.alloc(64-v.length)]);
  }
  if(t === 'chunk') {
    const b = Buffer.from(v, 'hex');
    assert(b.length >= 1 && b.length <= 8140);
    return Buffer.concat([integer(b.length, 2), b]);
  }
  const [width, lo, hi] = schema.enums[t];
  assert(v >= lo && v <= hi);
  return integer(v, width, t === 'vr');
}
function frame(kind, obj) {
  const b=encode(kind, obj);
  return Buffer.concat([integer(schema.kinds[kind],1), integer(1,2), integer(b.length,4), b]);
}
let checks=0;
for(const row of fixtures.vectors) {
  const b = encode(row.kind, row.object);
  assert.equal(b.toString('hex'), row.hex);
  assert.equal(b.length, row.length);
  assert.equal(hash(b), row.sha256);
  assert.equal(tag(row.kind.toLowerCase(), b), row.object_id);
  if(row.signing_preimage_hex) {
    const message = Buffer.concat([Buffer.from('ZCRJ717R\0user-'+row.kind+'\0'), b.subarray(0, -65)]);
    const pre = Buffer.concat([Buffer.from('\x19Ethereum Signed Message:\n'+message.length), message]);
    assert.equal(pre.toString('hex'), row.signing_preimage_hex);
    assert.equal(hash(pre), row.signing_preimage_sha256);
  }
  checks++;
}
const b=fixtures.batch;
const frames=Buffer.concat(b.events.map(([k,v]) => frame(k,v)));
const header={...b.header, events_root:tag('events',frames), event_count:b.events.length, event_bytes:frames.length};
const h=encode('HEADER',header);
const full=Buffer.concat([Buffer.from('R717B001'),integer(1,2),integer(h.length,2),h,frames]);
assert.equal(full.toString('hex'),b.hex);
assert.equal(full.length,b.length);
assert.equal(hash(full),b.sha256);
const contextNames=['network','genesis','protocol','instance','validators','membership','policy'];
const contextFields=schema.schemas.HEADER.filter(([k]) => contextNames.includes(k));
const sample=b.header.clock.samples[0];
const time=Buffer.concat([Buffer.from('ZCRJ717R\0time\0'),
  ...contextFields.map(([k,t])=>encode(t,b.header[k])), integer(1,8), Buffer.from(b.header.parent,'hex'),
  integer(1,8), encode('TIME_SAMPLE',sample).subarray(0,-65)]);
assert.equal(time.toString('hex'),fixtures.time_preimage.hex);
assert.equal(hash(time),fixtures.time_preimage.sha256);
const result=JSON.parse(fs.readFileSync(path.resolve(__dirname,'results.json')));
for(const page of result.closure.pages) {
  const bytes=Buffer.concat(page.rows.map(r=>frame('CLOSE',r)));
  assert.equal(bytes.toString('hex'),page.hex);
  assert.equal(hash(bytes),page.sha256);
  assert.equal(bytes.length,page.frame_bytes);
}
const vote=fixtures.vectors.find(x=>x.name==='invalid_signature').object;
const close=fixtures.vectors.find(x=>x.name==='mandatory_close').object;
const vb=encode('VOTE',vote);
const empty=tag('empty-votes',Buffer.from(vote.sid,'hex'));
const fold=tag('vote-step',Buffer.concat([Buffer.from(empty,'hex'),integer(1,8),integer(3,8),
  integer(0,2),Buffer.from(tag('vote-message',vb.subarray(0,-65)),'hex'),
  Buffer.from(tag('vote-evidence',vb),'hex'),integer(2,1)]));
assert.equal(fold,close.fold);
process.stdout.write(JSON.stringify({vectors:checks,batch:true,time_preimage:true,
  closure_pages:result.closure.pages.length,vote_fold:true,
  independent_encoder:true,hash:'node:crypto SHA-256',signatures_generated:0})+'\n');
