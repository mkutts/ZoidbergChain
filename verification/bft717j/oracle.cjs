// Disposable independent byte/crypto oracle. No node, database, wallet or consensus service.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const v = JSON.parse(fs.readFileSync(__dirname+'/vectors.json','utf8'));
function J(x) {
  if (x===null) return 'null';
  if (Array.isArray(x)) return '['+x.map(J).join(',')+']';
  if (typeof x==='object') return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+J(x[k])).join(',')+'}';
  if (typeof x==='number') assert(Number.isSafeInteger(x)&&!Object.is(x,-0));
  return JSON.stringify(x);
}
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
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
  assert(r>0n&&r<N&&s>0n&&s<N&&(vv===27||vv===28));
  const x=r;assert(x<P);let y=pow(mod(x*x*x+7n),(P+1n)/4n);assert.equal(mod(y*y),mod(x*x*x+7n));
  if(Number(y&1n)!==vv-27)y=P-y;
  const R=[x,y];assert.equal(mul(R,N),null);
  const q=mul(add(mul(R,s),mul(G,mod(-BigInt('0x'+digest),N))),inv(r,N));assert(q);
  // Check verification independently of the recovered-point equation.
  const w=inv(s,N),pt=add(mul(G,mod(BigInt('0x'+digest)*w,N)),mul(q,mod(r*w,N)));assert(pt&&mod(pt[0],N)===r);
  return (q[1]&1n?'03':'02')+hex32(q[0]);
}
function pub(i){const e=crypto.createECDH('secp256k1');e.setPrivateKey(Buffer.from(hex32(BigInt(i)),'hex'));return e.getPublicKey('hex','compressed');}
function address(i){const e=crypto.createECDH('secp256k1');e.setPrivateKey(Buffer.from(hex32(BigInt(i)),'hex'));return '0x'+keccak(e.getPublicKey().subarray(1)).subarray(12).toString('hex');}
function manifest(network='task717i-test',members=[1,2,3,4]){return {validator_public_keys:members.map(pub).sort(),required_quorum:3,byzantine_fault_budget:1,validator_epoch:0,authority_profile:'static-genesis-v1',network_id:network,protocol_version:2,protocol:'zoidbergchain',membership_version:1,domain:'zoidbergchain/validator-set/v1'};}
const C=sha(J(manifest()));assert.equal(C,v.validator_set_commitment);assert.equal(J(manifest()),J(v.manifest));
const D={protocol_version:2,protocol:'zoidbergchain',domain:'zoidbergchain/bft-agreement/v1',agreement_version:1,
reference:'arxiv:1807.04938v3/Algorithm1',rule_selection:'printed-lines-1-67',authority_profile:'static-genesis-n4-f1-q3-v1',
proposer_profile:'height-minus-one-plus-round-mod-four-v1',parent_profile:'immediate-finalized-v1',wire_profile:'bft-ascii-json-v1',timeout_profile:'linear-1000ms-plus-1000ms-per-round-v1',
signer_profile:'reserve-sign-store-release-v1',application_policy_digest:'55'.repeat(32),
limits:{max_uint:9007199254740991,max_round:2147483647,max_depth:32,manifest_bytes:8192,agreement_bytes:4096,envelope_bytes:2048,signed_bytes:2304,
prevote_certificate_bytes:12288,commit_proof_bytes:16384,block_bytes:3145728,proposal_bundle_bytes:3160400,round_evidence_bytes:8192}};
assert.equal(J(D),J(v.agreement));const A=sha(J(D));assert.equal(A,v.agreement_profile_digest);
function envelope({step='prevote',i=1,h=1,r=0,value='aa'.repeat(32),vr=-1,network='task717i-test',genesis='11'.repeat(32),commitment=C}={}){
  const p={step,block_hash:value,validator_set_commitment:commitment,validator_id:address(i),validator_epoch:0,round:r,parent_hash:genesis,message_version:1,genesis_hash:genesis,block_height:h,agreement_profile_digest:A};
  const purpose=step==='propose'?'bft-proposal':'bft-vote';if(step==='propose')p.valid_round=vr;
  return {protocol_version:2,protocol:'zoidbergchain',payload:p,object_type:purpose,network_id:network,domain:`zoidbergchain/${purpose}/v1`};
}
const specs={proposal:{step:'propose'},prevote:{},precommit:{step:'precommit'},'nil-prevote':{value:null},'nil-precommit':{step:'precommit',value:null},
'round-one-prevote':{r:1},'justified-proposal':{step:'propose',i:2,r:1,vr:0},'network-b':{network:'task717i-test-b',commitment:sha(J(manifest('task717i-test-b')))},'genesis-b':{genesis:'22'.repeat(32)},'set-b':{commitment:sha(J(manifest('task717i-test',[1,2,3,5])))},'conflicting-prevote':{value:'bb'.repeat(32)},'conflicting-proposal':{step:'propose',value:'bb'.repeat(32)}};
for(const i of [2,3,4]){specs[`precommit-key-${i}`]={step:'precommit',i};specs[`prevote-key-${i}`]={i};}
for(const i of [1,2,3])specs[`conflicting-precommit-key-${i}`]={step:'precommit',i,value:'bb'.repeat(32)};
const verifiedCache=new Map();
function verify(s){const cacheKey=J(s);if(verifiedCache.has(cacheKey))return verifiedCache.get(cacheKey);const raw=Buffer.from(J(s.envelope),'ascii'),prefix=Buffer.from('\x19Ethereum Signed Message:\n'+raw.length,'ascii'),digest=keccak(Buffer.concat([prefix,raw])).toString('hex');const key=recover(s.signature,digest);verifiedCache.set(cacheKey,key);return key;}
for(const [name,spec] of Object.entries(specs)){
  const expected=v.cases[name],raw=Buffer.from(J(envelope(spec)),'ascii'),prefix=Buffer.from('\x19Ethereum Signed Message:\n'+raw.length,'ascii');
  assert.equal(raw.toString(),expected.preimage_ascii);assert.equal(raw.length,expected.byte_length);assert.equal(sha(raw),expected.message_id);assert.equal(prefix.toString('hex'),expected.prefix_hex);
  assert.equal(keccak(Buffer.concat([prefix,raw])).toString('hex'),expected.signing_digest);
  assert.equal(verify(expected.signed),pub(spec.i||1));assert.equal(sha(J(expected.signed)),expected.signed_id);assert.equal(Buffer.byteLength(J(expected.signed)),expected.signed_length);
}
function core(q){
  const t=q.commitment,ss=q.precommits,ids=ss.map(s=>s.envelope.payload.validator_id);assert(t.block_hash!==null&&t.step==='precommit');
  assert(ss.length>=3&&ss.length<=4);assert.equal(new Set(ids).size,ids.length);assert.deepEqual(ids,[...ids].sort());
  const {validator_id:discard,...pp}=q.proposal.envelope.payload;
  const sorted=manifest().validator_public_keys,proposer=sorted[(pp.block_height-1+pp.round)%4];assert.equal(verify(q.proposal),proposer);
  assert.equal(pp.step,'propose');assert(pp.valid_round===-1||(pp.valid_round>=0&&pp.valid_round<pp.round));
  const {valid_round:ignore,step:also,...common}=pp;const {step:omit,...target}=t;assert.equal(J(common),J(target));
  for(const s of ss){const {validator_id,...fields}=s.envelope.payload;assert.equal(J(fields),J(t));assert(sorted.includes(verify(s)));assert.equal(validator_id, '0x'+keccak(Buffer.from(mul(G,BigInt(v.keys.find(k=>k.public_key===verify(s)).scalar)).map(hex32).join(''),'hex')).subarray(12).toString('hex'));}
  return t.block_hash;
}
function commitment(e){const {validator_id,...t}=e.payload;return t;}
const sigFor=(name)=>({signature_scheme:'personal_sign',signature:v.cases[name].signed.signature,envelope:envelope(specs[name])});
const sortID=a=>a.sort((x,y)=>x.envelope.payload.validator_id.localeCompare(y.envelope.payload.validator_id));
const independentPV={votes:sortID(['prevote','prevote-key-2','prevote-key-3'].map(sigFor)),commitment:commitment(envelope()),certificate_version:1};
const independentQ=(conflict=false,four=false)=>({proof_version:4,proposal:sigFor(conflict?'conflicting-proposal':'proposal'),commitment:commitment(envelope({step:'precommit',value:(conflict?'bb':'aa').repeat(32)})),precommits:sortID((conflict?['conflicting-precommit-key-1','conflicting-precommit-key-2','conflicting-precommit-key-3']:['precommit','precommit-key-2','precommit-key-3',...(four?['precommit-key-4']:[])]).map(sigFor))});
const independentRE={evidence_version:1,messages:sortID(['round-one-prevote','justified-proposal'].map(sigFor))};
const independentProofs={pv:independentPV,'q4-x':independentQ(),'q4-y':independentQ(true),'q4-x-four':independentQ(false,true),re:independentRE};
for(const [name,row] of Object.entries(v.proofs)){assert.equal(J(independentProofs[name]),J(row.value));assert.equal(sha(J(independentProofs[name])),row.digest);assert.equal(Buffer.byteLength(J(independentProofs[name])),row.byte_length);if(name.startsWith('q4'))core(row.value);}
function rejected(f){assert.throws(f);}
const duplicate=structuredClone(v.proofs['q4-x'].value);duplicate.precommits[1]=duplicate.precommits[0];rejected(()=>core(duplicate));
const mixed=structuredClone(v.proofs['q4-x'].value);mixed.precommits[0].envelope.payload.round=1;rejected(()=>core(mixed));
const badSignature=structuredClone(v.proofs['q4-x'].value);badSignature.precommits[0].signature='0x'+'00'.repeat(65);rejected(()=>core(badSignature));
const high=structuredClone(v.cases.prevote.signed),sig=high.signature;high.signature=sig.slice(0,66)+hex32(N-BigInt('0x'+sig.slice(66,130)))+(sig.endsWith('1b')?'1c':'1b');assert.equal(verify(high),pub(1));assert.equal(J(high.envelope),J(v.cases.prevote.envelope));
assert.notEqual(core(v.proofs['q4-x'].value),core(v.proofs['q4-y'].value));
assert.equal(core(v.proofs['q4-x'].value),core(v.proofs['q4-x-four'].value));
let contextMutations=0;
for(const [where,name,value] of [['envelope','network_id','task717i-other'],['payload','genesis_hash','33'.repeat(32)],['payload','validator_set_commitment','44'.repeat(32)],['payload','agreement_profile_digest','66'.repeat(32)],['payload','parent_hash','77'.repeat(32)],['payload','message_version',2],['payload','validator_epoch',1],['payload','step','precommit']]){
  const mutated=structuredClone(v.cases.prevote.signed);(where==='payload'?mutated.envelope.payload:mutated.envelope)[name]=value;
  assert.notEqual(verify(mutated),pub(1));contextMutations++;
}
// Independent maximum-width reconstruction, not cryptographically valid certificates.
const wideE=envelope({step:'propose',h:9007199254740991,r:2147483647,vr:2147483646,network:'n'.repeat(64)});
const wideS={envelope:wideE,signature:'0x'+'ff'.repeat(64)+'1b',signature_scheme:'personal_sign'};
const wideVote=step=>({envelope:envelope({step,h:9007199254740991,r:2147483647,network:'n'.repeat(64)}),signature:wideS.signature,signature_scheme:'personal_sign'});
const wpv=wideVote('prevote'),wpc=wideVote('precommit');
const width=x=>Buffer.byteLength(J(x));
const pvn=n=>({certificate_version:1,commitment:commitment(wpv.envelope),votes:Array(n).fill(wpv)});
const qn=n=>({proof_version:4,commitment:commitment(wpc.envelope),proposal:wideS,precommits:Array(n).fill(wpc)});
const sizes={manifest:width(manifest('n'.repeat(64))),agreement:width(D),proposal_envelope:width(wideE),proposal_signed:width(wideS),prevote_envelope:width(wpv.envelope),prevote_signed:width(wpv),precommit_envelope:width(wpc.envelope),precommit_signed:width(wpc),pv3:width(pvn(3)),pv4:width(pvn(4)),q4_3:width(qn(3)),q4_4:width(qn(4)),round_evidence:width({evidence_version:1,messages:[wideS,wpc]}),context_extension:width({consensus_context:{agreement_profile_digest:A,validator_epoch:0,validator_set_commitment:C}})-1,proposal_bundle:3145728+width(wideS)+width(pvn(4))+43};
assert.deepEqual(sizes,v.sizes);
const NS={validator_id:address(1),validator_public_key:pub(1),validator_set_commitment:C,validator_epoch:0,agreement_profile_digest:A,genesis_hash:'11'.repeat(32),network_id:'task717i-test',protocol_version:2,protocol:'zoidbergchain'};
assert.equal(J(NS),J(v.namespace));
const scenarioSpecs={retry:['return_exact_stored','prevote',43,'22','unknown'],conflict:['CONFLICTING_SLOT','conflicting-prevote',43,'22','unknown'],'crash-before-publication':['publish_exact_stored','prevote',43,'22','not_started'],'stale-state':['STALE_STATE','prevote',41,'11','unknown'],'same-sequence-divergence':['STALE_STATE','prevote',43,'33','unknown']};
for(const [name,[expected,request,sequence,event,publication]] of Object.entries(scenarioSpecs)){
  const x={case:name,namespace_id:sha(J(NS)),slot:{height:1,round:0,purpose:'prevote'},stored_message_id:sha(J(envelope())),stored_signature:v.cases.prevote.signed.signature,request_message_id:sha(J(envelope(specs[request]))),db_sequence:sequence,db_event_id:event.repeat(32),witness_sequence:43,witness_event_id:'22'.repeat(32),publication,expected};
  assert.equal(J(x),J(v.scenarios[name]));
}
console.log(JSON.stringify({cases:Object.keys(specs).length,proofs:Object.keys(v.proofs).length,sha256:'all match',keccak:'all match',full_key_recovery:'all match',context_mutations:contextMutations,maximum_widths:'all match',high_s:'same message/key',duplicate_mixed_bad_signature:'rejected',same_height_conflict:'detected',scope:'certificate crypto core only; no application/genesis validation'},null,2));