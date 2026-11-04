// Independent Node JSON/preimage/SHA-256 check; not a second consensus validator.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dir = path.join(root, 'tests/fixtures/milestone_7_v3_v1');
const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function j(value) {
  if (Array.isArray(value)) return '[' + value.map(j).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + j(value[k])).join(',') + '}';
  }
  return JSON.stringify(value);
}
const a = value => j(value).replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
const assert = (ok, name) => { if (!ok) throw new Error(name); };
const env = (payload, purpose) => ({domain: 'zoidbergchain/' + purpose + '/v2', network_id: manifest.context.network_id,
  object_type: purpose, payload, protocol: 'zoidbergchain', protocol_version: 2});
const unsigned = (value, field) => Object.fromEntries(Object.entries(value).filter(([k]) => k !== field));
function transaction(t) {
  const keys = 'amount fee from_address genesis_hash memo nonce timestamp to_address transaction_type transaction_version'.split(' ');
  const m = j(env(Object.fromEntries(keys.map(k => [k, t[k]])), 'native-transfer'));
  assert(m === t.signed_message && sha(m) === t.tx_id && sha(m) === t.signed_message_hash, 'native preimage');
}
let checked = 0;
for (const v of manifest.vectors) {
  const raw = fs.readFileSync(path.join(dir, v.file));
  assert(raw.length === v.bytes && sha(raw) === v.sha256, v.id + ' inventory');
  if (v.expected !== 'valid') continue;
  const value = JSON.parse(raw.toString('utf8'));
  assert(Buffer.from(v.kind === 'aggregate' ? a(value) : j(value)).equals(raw), v.id + ' JSON');
  if (v.kind === 'transaction') transaction(value);
  if (v.kind === 'record') {
    assert(sha(j(value.envelope)) === value.hash, v.id + ' block hash');
    const p = value.envelope.payload, c = p.admission_certificate;
    assert(sha(a(p.native_transactions)) === p.transactions_hash, 'native aggregate');
    p.native_transactions.forEach(transaction);
    assert(sha(j(unsigned(c, 'certificate_digest'))) === c.certificate_digest, 'certificate');
    assert(sha(j(unsigned(c.technical_evidence, 'evidence_digest'))) === c.technical_evidence.evidence_digest, 'technical');
    const am = j(env(c.attestation.canonical_payload, 'submitter-attestation'));
    assert(am === c.attestation.canonical_message && sha(am) === c.attestation.canonical_payload_digest &&
      sha(am) === c.attestation.canonical_message_hash, 'submitter');
    for (const vote of c.votes) {
      const vp = JSON.parse(vote.vote_message);
      assert(j(vp) === vote.vote_message && sha(j(vp)) === vote.signed_message_hash, 'vote message');
      assert(sha(j({payload: vp, signature: vote.vote_signature})) === vote.vote_identity, 'vote identity');
    }
    for (const dim of ['originality', 'admissibility']) {
      const projection = c.votes.filter(v => v.dimension === dim).sort((a,b) => a.voter < b.voter ? -1 : a.voter > b.voter ? 1 : 0)
        .map(v => ({wallet: v.voter, choice: v.vote_type, identity: v.vote_identity, status: v.reviewer_status}));
      assert(sha(j(projection)) === c[dim].vote_set_digest, 'tally digest');
    }
    console.log(v.id + ': R=' + raw.length + ', hash=' + value.hash);
  }
  checked++;
}
assert(sha(fs.readFileSync(path.join(dir, 'native-message.json'))) ===
  'e68931c52c88865a0ad5f73edee11b36d57887c1f953898ab0f052d86ac4f425', 'published B oracle');
console.log(`${manifest.vectors.length} frozen files; ${checked} positive JSON/preimage checks; Node ${process.version} ${process.platform}`);
