// Exact independent Task 7.17L Appendix B recipe, retained unchanged below.
// Independent fixture construction and SHA-256, not a generic G2 parser.
const fs=require('node:fs'), crypto=require('node:crypto'), assert=require('node:assert/strict');
function J(x){if(x===null||typeof x!=='object')return JSON.stringify(x);
 if(Array.isArray(x))return '['+x.map(J).join(',')+']';
 return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+J(x[k])).join(',')+'}';}
const S=x=>crypto.createHash('sha256').update(x,'utf8').digest('hex'), D=x=>S(J(x));
const N='task717i-test';
function E(kind,payload,version=1){return {domain:`zoidbergchain/${kind}/v${version}`,
 network_id:N,object_type:kind,payload,protocol:'zoidbergchain',protocol_version:2};}
const pubs=[
 '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798',
 '02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5',
 '02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13',
 '02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9'];
const ids=['0x7e5f4552091a69125d5dfcb7b8c2659029395bdf','0x2b5ad5c4795c026514f8317c7a215e218dccd6cf'];
const M={validator_public_keys:pubs,required_quorum:3,byzantine_fault_budget:1,
 validator_epoch:0,authority_profile:'static-genesis-v1',network_id:N,protocol_version:2,
 protocol:'zoidbergchain',membership_version:1,domain:'zoidbergchain/validator-set/v1'};
const versions={technical:1,rights:1,reviewer:2,review:3,reputation:3,native:2,media:2,issuance:1,history:1,encoding:1};
const PR={policies:Object.keys(versions).sort().map(policy_kind=>({canonical_bytes:'7b7d',
 policy_version:versions[policy_kind],policy_kind})),network_id:N,registry_version:1,
 domain:'zoidbergchain/application-policy-registry/v1'};
const DA={wire_profile:'bft-ascii-json-v1',timeout_profile:'linear-1000ms-plus-1000ms-per-round-v1',
 signer_profile:'reserve-sign-store-release-v1',rule_selection:'printed-lines-1-67',
 reference:'arxiv:1807.04938v3/Algorithm1',protocol_version:2,protocol:'zoidbergchain',
 proposer_profile:'height-minus-one-plus-round-mod-four-v1',parent_profile:'immediate-finalized-v1',
 limits:{signed_bytes:2304,round_evidence_bytes:8192,proposal_bundle_bytes:3160400,
 prevote_certificate_bytes:12288,max_uint:9007199254740991,max_round:2147483647,max_depth:32,
 manifest_bytes:8192,envelope_bytes:2048,commit_proof_bytes:16384,block_bytes:3145728,agreement_bytes:4096},
 domain:'zoidbergchain/bft-agreement/v1',authority_profile:'static-genesis-n4-f1-q3-v1',
 application_policy_digest:D(PR),agreement_version:1};
const B0={reviewers:[...ids].sort(),reputation_rule_digest:D({}),reviewer_policy_digest:D({}),network_id:N,bootstrap_version:1};
const N0={allocations:[],initial_reward_pool:'0',total_supply:'0',network_id:N,native_state_version:1};
const N1={allocations:[{wallet_address:ids[0],balance:'1',next_nonce:'1'}],initial_reward_pool:'0',total_supply:'1',network_id:N,native_state_version:1};
const HB={bootstrap_events:[],history_version:1};
const BE=E('reviewer-bootstrap',B0),NE=E('native-bootstrap',N0),HE=E('history-bootstrap',HB);
const S0={bootstrap_history_commitment:D(HE),native_bootstrap_digest:D(NE),reviewer_bootstrap_digest:D(BE),policy_registry_digest:D(PR),state_version:1};
const SE=E('initial-state',S0), H0={initial_state_commitment:D(SE),initial_state:S0,bootstrap_history_commitment:D(HE),bootstrap_events:[],history_version:1};
const P={history_bootstrap:H0,native_bootstrap_digest:D(NE),native_bootstrap:N0,
 reviewer_bootstrap_digest:D(BE),reviewer_bootstrap:B0,policy_registry_digest:D(PR),policy_registry:PR,
 agreement_profile_digest:D(DA),agreement_descriptor:DA,validator_set_commitment:D(M),validator_manifest:M,
 consensus_message_version:1,initial_block_version:4,application:N,previous_hash:'0'.repeat(64),index:0,genesis_version:2};
const G2=E('genesis',P,2), G=D(G2);
const NS={validator_id:ids[0],validator_public_key:pubs[0],validator_set_commitment:D(M),validator_epoch:0,
 agreement_profile_digest:D(DA),genesis_hash:G,network_id:N,protocol_version:2,protocol:'zoidbergchain'};
const J0={bootstrap_digest:D(BE),history_policy_digest:D({}),genesis_hash:G,network_id:N,
 protocol_version:2,domain:'zoidbergchain/reviewer-journal-genesis/v1'};
const rebuilt={accounts:[],reward_pool:'0',reviewers:[...ids].sort().map(wallet_address=>({wallet_address,
 underlying_status:'ESTABLISHED_REVIEWER',quota_used:0})),claims:[],offenses:[],penalties:[],participation:[],finalized_ref:{block_height:0,block_hash:G}};
const expected=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const objects={M,PR,DA,B0:BE,N0:NE,N1:E('native-bootstrap',N1),HB:HE,S0:SE,G2,NS,J0,rebuilt};
for(const [name,value] of Object.entries(objects)){
 assert.equal(J(value),expected.objects[name].preimage,name+' bytes');
 assert.equal(Buffer.byteLength(J(value)),expected.objects[name].bytes,name+' length');
 assert.equal(D(value),expected.objects[name].sha256,name+' SHA256');
}
const cases={
 'wrong-manifest':[['payload','validator_manifest','required_quorum'],2],
 'wrong-network':[['network_id'],'task717i-test-b'],
 'malformed-reviewer':[['payload','reviewer_bootstrap','reviewers'],['0xBAD']],
 'duplicate-reviewer':[['payload','reviewer_bootstrap','reviewers'],[ids[0],ids[0]]],
 'tampered-policy-version':[['payload','policy_registry','policies',0,'policy_version'],2],
 'wrong-validator-epoch':[['payload','validator_manifest','validator_epoch'],1],
 'unknown-field':[['payload','genesis_hash'],G],
 'null-reviewers':[['payload','reviewer_bootstrap','reviewers'],null],
 'self-consistent-foreign-root':[['payload','application'],'task717i-other']};
for(const [name,[path,value]] of Object.entries(cases)){
 const changed=structuredClone(G2);let at=changed;
 for(const k of path.slice(0,-1))at=at[k];at[path.at(-1)]=value;
 assert.equal(S(J(changed)),expected.mutations[name].sha256,name);
 assert.equal(Buffer.byteLength(J(changed)),expected.mutations[name].bytes,name+' length');
 assert.notEqual(D(changed),G);
}
assert.equal(S(J(G2)+'\n'),expected.mutations['noncanonical-newline'].sha256);
assert.equal(Buffer.byteLength(J(G2)+'\n'),expected.mutations['noncanonical-newline'].bytes);
assert.equal(J(rebuilt),expected.objects.rebuilt.preimage);
console.log('PASS: 12 independently constructed canonical objects/hashes and 10 mutation bytes/hashes; genesis projection only; no semantic policy/launch acceptance');
