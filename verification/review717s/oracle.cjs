// TEST ONLY. Independent BigInt secp256k1 recovery/ECDSA and Keccak ported
// from I's independent JS oracle, with R's NEW strict low-S requirement.
// No Python crypto calls, keys, signing, network or node integration.
'use strict';
const fs=require('node:fs'), crypto=require('node:crypto'), assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const schema=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/review717r_v1/schema.json')));
const data=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/review717s_v1/vectors.json')));
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const tag=(t,b)=>sha(Buffer.concat([Buffer.from('ZCRJ717R\0'+t+'\0'),b]));
const mask=(1n<<64n)-1n;
const rc=[1n,0x8082n,0x800000000000808an,0x8000000080008000n,0x808bn,0x80000001n,0x8000000080008081n,0x8000000000008009n,0x8an,0x88n,0x80008009n,0x8000000an,0x8000808bn,0x800000000000008bn,0x8000000000008089n,0x8000000000008003n,0x8000000000008002n,0x8000000000000080n,0x800an,0x800000008000000an,0x8000000080008081n,0x8000000000008080n,0x80000001n,0x8000000080008008n];
const rot=[0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14];
const rol=(x,n)=>((x<<BigInt(n))|(x>>BigInt(64-n)))&mask;
function keccak(input) {
  const rate=136, b=Buffer.alloc(Math.ceil((input.length+1)/rate)*rate); input.copy(b);
  b[input.length]^=1; b[b.length-1]^=128;
  const a=Array(25).fill(0n);
  for(let off=0;off<b.length;off+=rate) {
    for(let i=0;i<17;i++) a[i]^=b.readBigUInt64LE(off+i*8);
    for(const r of rc) {
      const c=Array.from({length:5},(_,x)=>a[x]^a[x+5]^a[x+10]^a[x+15]^a[x+20]);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) a[x+5*y]^=c[(x+4)%5]^rol(c[(x+1)%5],1);
      const z=Array(25).fill(0n);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) z[y+5*((2*x+3*y)%5)]=rol(a[x+5*y],rot[x+5*y]);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) a[x+5*y]=(z[x+5*y]^((~z[(x+1)%5+5*y])&z[(x+2)%5+5*y]))&mask;
      a[0]^=r;
    }
  }
  const out=Buffer.alloc(32); for(let i=0;i<4;i++) out.writeBigUInt64LE(a[i],8*i); return out;
}
assert.equal(keccak(Buffer.alloc(0)).toString('hex'),'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470');
const P=0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn;
const N=0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
const G=[0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n,0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n];
const mod=(x,n=P)=>(x%n+n)%n;
function pow(a,b,n=P){let r=1n;for(a=mod(a,n);b;b>>=1n,a=a*a%n)if(b&1n)r=r*a%n;return r;}
const inv=(a,n=P)=>pow(a,n-2n,n);
function add(a,b){
  if(!a)return b;if(!b)return a;
  if(a[0]===b[0]&&mod(a[1]+b[1])===0n)return null;
  const s=a[0]===b[0]?mod(3n*a[0]*a[0]*inv(2n*a[1])):mod((b[1]-a[1])*inv(b[0]-a[0]));
  const x=mod(s*s-a[0]-b[0]);return[x,mod(s*(a[0]-x)-a[1])];
}
function mul(a,k){let r=null;for(;k;k>>=1n,a=add(a,a))if(k&1n)r=add(r,a);return r;}
const hex32=x=>x.toString(16).padStart(64,'0');
function recover(sig,digest){
  assert(/^0x[0-9a-f]{130}$/.test(sig));const r=BigInt('0x'+sig.slice(2,66)),s=BigInt('0x'+sig.slice(66,130)),vv=parseInt(sig.slice(130),16);
  assert(r>0n&&r<N&&s>0n&&s<=N/2n&&(vv===27||vv===28));
  const x=r;assert(x<P);let y=pow(mod(x*x*x+7n),(P+1n)/4n);assert.equal(mod(y*y),mod(x*x*x+7n));
  if(Number(y&1n)!==vv-27)y=P-y;
  const R=[x,y];assert.equal(mul(R,N),null);
  const q=mul(add(mul(R,s),mul(G,mod(-BigInt('0x'+digest),N))),inv(r,N));assert(q);
  // Check verification independently of the recovered-point equation.
  const w=inv(s,N),pt=add(mul(G,mod(BigInt('0x'+digest)*w,N)),mul(q,mod(r*w,N)));assert(pt&&mod(pt[0],N)===r);
  return (q[1]&1n?'03':'02')+hex32(q[0]);
}
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
const ctxNames=schema.schemas.HEADER.slice(0,7);
const ctxt=c=>Buffer.concat(ctxNames.map(([k,t])=>encode(t,c[k])));
function preimage(kind,o,time) {
  const unsigned=encode(kind,o).subarray(0,-65);
  if(kind==='OPEN'||kind==='VOTE') {
    const m=Buffer.concat([Buffer.from('ZCRJ717R\0user-'+kind+'\0'),unsigned]);
    return Buffer.concat([Buffer.from('\x19Ethereum Signed Message:\n'+m.length),m]);
  }
  if(kind==='MESSAGE')return Buffer.concat([Buffer.from('ZCRJ717R\0consensus\0'),unsigned]);
  assert.equal(kind,'TIME_SAMPLE');
  return Buffer.concat([Buffer.from('ZCRJ717R\0time\0'),ctxt(time.context),integer(time.height,8),
    Buffer.from(time.parent,'hex'),integer(time.sequence,8),unsigned]);
}
function address(key) {
  assert.match(key,/^0[23][0-9a-f]{64}$/);
  const raw=crypto.ECDH.convertKey(Buffer.from(key,'hex'),'secp256k1',undefined,undefined,'uncompressed');
  return keccak(raw.subarray(1)).subarray(12).toString('hex');
}
const cache=new Map();
function authenticate(kind,obj,expected,time) {
  const p=preimage(kind,obj,time), d=keccak(p).toString('hex');
  const key=d+obj.signature;
  if(!cache.has(key))cache.set(key,recover('0x'+obj.signature,d));
  assert.equal(cache.get(key),expected);
  return address(expected);
}
const context=data.context, pubs=data.manifest.validator_public_keys;
assert.equal(sha(Buffer.from(JSON.stringify(data.manifest,Object.keys(data.manifest).sort()))),context.validators);
assert.equal(pubs.length,4);assert.deepEqual(pubs,[...new Set(pubs)].sort());
function checkContext(o) {for(const [k] of ctxNames)assert.equal(o[k],context[k]);}
function message(o,target) {
  encode('MESSAGE',o);checkContext(o);
  for(const k of ['height','parent','round','step','nil','value'])assert.equal(o[k],target[k]);
  assert(o.height>=1);
  if(o.height===1)assert.equal(o.parent,data.origin);
  if(o.nil)assert(o.value==='00'.repeat(32)&&o.step!==0);
  if(o.step===0) {
    assert.equal(o.nil,0);assert.equal(o.validator,((o.height-1)%4+o.round%4)%4);
    assert(o.valid_round===-1||(o.valid_round>=0&&o.valid_round<o.round));
    if(o.valid_round===-1)assert.equal(o.justification,'00'.repeat(32));
    else {
      const p=Buffer.from(data.proofs.pv_hex,'hex');assert.equal(tag('pv',p),o.justification);
      // Actual complete PV bytes are checked below, not accepted by hash alone.
    }
  } else assert(o.valid_round===-1&&o.justification==='00'.repeat(32));
  authenticate('MESSAGE',o,pubs[o.validator]);
}
let accepted=0,rejected=0;
for(const row of data.records) {
  const b=encode(row.kind,row.object), pre=preimage(row.kind,row.object,row.time_context);
  assert.equal(b.toString('hex'),row.hex);assert.equal(b.length,row.length);assert.equal(sha(b),row.sha256);
  assert.equal(pre.toString('hex'),row.preimage_hex);assert.equal(sha(pre),row.preimage_sha256);
  assert.equal(keccak(pre).toString('hex'),row.keccak256);assert.equal(address(row.public_key),row.wallet);
  const validate=()=>{
    const o=row.object;
    if(row.kind==='TIME_SAMPLE')authenticate(row.kind,o,pubs[o.validator],row.time_context);
    else {
      checkContext(o);
      if(row.kind==='MESSAGE')message(o,o);
      else {
        if(row.name.startsWith('signed-wrong-')) {
          const base=data.records.find(r=>r.name==='vote-0-0').object;
          for(const k of ['sid','submission','dimension'])assert.equal(o[k],base[k]);
        }
        const wallet=authenticate(row.kind,o,o.key);
        if(row.kind==='OPEN')assert.equal(wallet,o.creator);
      }
    }
  };
  if(row.expected==='REJECT'){assert.throws(validate);rejected++;}
  else {validate();accepted++;}
}
function byName(n){return data.records.find(r=>r.name===n).object;}
function quorum(votes,target) {
  const ids=votes.map(o=>o.validator);
  assert.equal(votes.length,3);assert.equal(new Set(ids).size,3);assert.deepEqual(ids,[...ids].sort());
  for(const o of votes)message(o,target);
}
let parent=data.origin, state=data.initial_state;
for(let i=0;i<4;i++) {
  const unit=data.history.units[i], h=i+1;
  const samples=[0,1,2].map(j=>byName(`time-${h}-${j}`));
  const events=h===1?[['OPEN',byName('open')]]:null;
  // Independently reconstruct every frame from the retained display objects.
  // They are metadata for this oracle, not an alternative wire format.
  const parsed=data.history.display_units[i], frames=Buffer.concat(parsed.events.map(([k,o])=>frame(k,o)));
  const header=parsed.header;checkContext(header);assert.equal(header.height,h);
  assert.equal(header.parent,parent);assert.equal(header.previous_state,state);
  assert.equal(header.events_root,tag('events',frames));assert.equal(header.event_count,parsed.events.length);
  assert.equal(header.event_bytes,frames.length);
  for(const sample of header.clock.samples)authenticate('TIME_SAMPLE',sample,pubs[sample.validator],
    {context,height:h,parent,sequence:h});
  const hb=encode('HEADER',header);
  const batch=Buffer.concat([Buffer.from('R717B001'),integer(1,2),integer(hb.length,2),hb,frames]);
  assert.equal(batch.toString('hex'),unit.batch_hex);assert.equal(sha(batch),unit.batch_sha256);
  const value=tag('batch',batch);assert.equal(value,unit.batch_id);
  const proof=parsed.proof,pb=encode('PROOF',proof);
  assert.equal(pb.toString('hex'),unit.proof_hex);assert.equal(sha(pb),unit.proof_sha256);
  assert.equal(tag('proof',pb),unit.proof_id);
  message(proof.proposal,{height:h,parent,round:0,value,step:0,nil:0});
  quorum(proof.precommits,{height:h,parent,round:0,value,step:2,nil:0});
  parent=value;state=tag('state',Buffer.from(state+parent,'hex'));
}
const v3=data.history.display_units[2], value=data.history.units[2].batch_id, par=v3.header.parent;
const pv={votes:[0,1,2].map(i=>byName('prevote-'+i))};
assert.equal(encode('PV',pv).toString('hex'),data.proofs.pv_hex);
quorum(pv.votes,{height:3,parent:par,round:0,value,step:1,nil:0});
const nilPV={votes:[0,1,2].map(i=>byName('nil-prevote-'+i))};
assert.equal(encode('PV',nilPV).toString('hex'),data.proofs.nil_pv_hex);
quorum(nilPV.votes,{height:3,parent:par,round:0,value:'00'.repeat(32),step:1,nil:1});
const rp={proposal:byName('justified-proposal'),precommits:[0,1,2].map(i=>byName('round-one-precommit-'+i))};
assert.equal(encode('PROOF',rp).toString('hex'),data.proofs.round_one_hex);
message(rp.proposal,{height:3,parent:par,round:1,value,step:0,nil:0});
quorum(rp.precommits,{height:3,parent:par,round:1,value,step:2,nil:0});
const bad=structuredClone(rp);bad.precommits[1]=bad.precommits[0];
assert.throws(()=>quorum(bad.precommits,{height:3,parent:par,round:1,value,step:2,nil:0}));
const mixed=structuredClone(rp);mixed.precommits[0]=byName('precommit-3-0');
assert.throws(()=>quorum(mixed.precommits,{height:3,parent:par,round:1,value,step:2,nil:0}));
// R rejects the mathematically equivalent high-S form accepted by I's old parser.
const hi=structuredClone(byName('vote-0-0')), sig=hi.signature;
hi.signature=sig.slice(0,64)+hex32(N-BigInt('0x'+sig.slice(64,128)))+(sig.endsWith('1b')?'1c':'1b');
assert.throws(()=>authenticate('VOTE',hi,hi.key));
let count=0,fold=tag('empty-votes',Buffer.from(data.history.media.sid,'hex'));
for(let i=0;i<v3.events.length;i++) {
  const [kind,a]=v3.events[i];if(kind!=='ADMISSION')continue;
  const vb=encode('VOTE',a.vote);count++;
  fold=tag('vote-step',Buffer.concat([Buffer.from(fold,'hex'),integer(count,8),integer(3,8),integer(i,2),
    Buffer.from(tag('vote-message',vb.subarray(0,-65)),'hex'),Buffer.from(tag('vote-evidence',vb),'hex'),integer(a.status,1)]));
}
assert.equal(count,10);assert.equal(fold,data.history.media.fold);
for(const [kind,field] of [['CHECKPOINT','checkpoint'],['MEDIA','media']])
  assert.equal(encode(kind,data.history[field]).toString('hex'),data.history[field+'_hex']);
const nc=data.negative_close, nh=encode('HEADER',nc.header), nf=Buffer.concat(nc.events.map(([k,o])=>frame(k,o)));
assert.equal(nc.header.events_root,tag('events',nf));
const nb=Buffer.concat([Buffer.from('R717B001'),integer(1,2),integer(nh.length,2),nh,nf]);
assert.equal(nb.toString('hex'),nc.unit.batch_hex);assert.equal(sha(nb),nc.unit.batch_sha256);
assert.equal(encode('PROOF',nc.proof).toString('hex'),nc.unit.proof_hex);
const nv=tag('batch',nb);assert.equal(nv,nc.unit.batch_id);
message(nc.proof.proposal,{height:4,parent:nc.header.parent,round:0,value:nv,step:0,nil:0});
quorum(nc.proof.precommits,{height:4,parent:nc.header.parent,round:0,value:nv,step:2,nil:0});
assert.notEqual(nc.events[0][1].count,count); // valid crypto, invalid CLOSE application commitment
const result={records:data.records.length,accepted,rejected,batches:4,proofs:8,
  independent_encoder:true,sha256:true,keccak:true,full_key_recovery_and_ecdsa:true,
  low_s:true,duplicate_and_mixed_rounds_rejected:true,fixture_fold:true,signed_false_close_detected:true,
  history_outcome:'INCOMPLETE_HISTORY',complete_finalized_history:false,agreement_execution:false};
process.stdout.write(JSON.stringify(result)+'\n');
