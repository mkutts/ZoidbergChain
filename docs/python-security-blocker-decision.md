# Milestone 2 Task 4C: Python Security Blocker Decision

Audit date: 2026-09-01. This is an analysis-only decision record. No source,
dependency, CI, suppression, protocol, or deployment change was made.

## 1. Executive Decision Summary

Choose two separate, compatibility-first remediation tasks; do not add an audit
exception now.

1. Remove the unreferenced legacy `zoidbergCoin.py` executable and its direct
   `sentence-transformers` dependency after a small removal-characterization
   task. This is the smallest safe disposition for all five Transformers
   findings. The supported FastAPI node and its originality path do not import
   or use that model stack.
2. Replace `ecdsa` behind the legacy `Wallet` and `Transaction` interfaces with
   the already retained, audited `cryptography` implementation only after
   adding exact legacy-key/signature/block compatibility tests. Do not delete
   the legacy signing types: peer block validation and persisted legacy blocks
   still deserialize and verify them.

This sequence can return the Python audit gate to green without a yanked,
prerelease, or release-candidate package and without a Protocol v1 change.

## 2. Initial State And Task 4B Precondition

- Initial branch: `Repository-Hygiene-and-Core-Refactor`.
- Initial HEAD: `c067116cb9f5f5880ddf9a1dcfdcf6372b493457` (`Remediate frontend dependency advisories`).
- Initial worktree: clean.
- Task 4A is separately committed as `48dd93a`; Task 4B is separately committed
  as `c067116` and changes only its report plus the frontend manifest/lockfile.
- The parent Task 4A verification record reports both `pip check` and
  `scripts/check_repository_hygiene.py` passing before Task 4B. Task 4B's own
  committed report records its isolated frontend verification but does not
  independently timestamp repeat Python/hygiene invocations. This is an
  evidence-recording gap, not a recorded failed verification; the clean
  post-Task-4B worktree allowed this analysis to proceed.

## 3. Reproduced Current Audit

A new external Python 3.13 environment was created outside the repository.
It installed the exact CI input, `requirements-test.txt`, and
`pip-audit==2.9.0`. `python -m pip check` reported `No broken requirements
found.` The exact CI command was then run:

```powershell
python -m pip_audit -r requirements-test.txt --strict
```

It failed, as expected, with six advisories in two packages:

| Package | Installed | Advisory | Current fixed version reported |
| --- | ---: | --- | --- |
| ecdsa | 0.19.2 | PYSEC-2026-1325 | none |
| transformers | 4.57.6 | PYSEC-2025-217 | none |
| transformers | 4.57.6 | PYSEC-2026-2290 | none |
| transformers | 4.57.6 | PYSEC-2026-2288 | 5.0.0 |
| transformers | 4.57.6 | PYSEC-2026-2289 | 5.3.0 |
| transformers | 4.57.6 | GHSA-xrqw-3rrv-vx5w | 5.10.0 |

Resolved relevant versions were `cryptography 50.0.0`, `ecdsa 0.19.2`,
`eth-account 0.13.7`, `sentence-transformers 3.3.1`, `transformers 4.57.6`,
and `torch 2.13.0`. The advisory count, IDs, and fixed-version fields have not
changed from Task 4A. `5.10.0` remains excluded from any recommendation because
Task 4A identified it as yanked.

## 4. Prior-Summary Mismatches

The Task 4A statement that `ecdsa` is reachable through legacy signing is
directionally correct but incomplete. `api.py` imports `Wallet` and
`Transaction`; `blockchain.py` imports both; and `api.py` creates three
SECP256k1 server wallets at module import. Thus a supported node imports and
executes `ecdsa` key generation during startup. The public-testnet identity,
vote, submission, and native-transfer signature paths are nevertheless
separate MetaMask `personal_sign` recovery paths using `eth-account`.

The Task 4A description of `zoidbergCoin.py` as a retained executable entry
point is also incomplete. It is not invoked by README, deployment, systemd,
scripts, CI, the UI, or tests. Its only `SentenceTransformer` construction is
the import-time `all-MiniLM-L6-v2` load; no `model.encode` or other model use
exists. It is therefore an unsupported legacy executable, not a dependency of
the supported originality service.

## 5. ecdsa Advisory And Reachability

`PYSEC-2026-1325` aliases CVE-2024-23342/GHSA-wj6h-64fc-37mp. Current advisory
metadata describes a Minerva timing attack on P-256 when timing
`ecdsa.SigningKey.sign_digest()`, P-256 key generation, or ECDH. It can leak a
nonce and then a private key. Verification is explicitly unaffected; upstream
considers side channels out of scope and provides no fix.

Repository use is `SECP256k1`, not P-256. It calls `SigningKey.generate`,
`SigningKey.from_string`, `SigningKey.sign`, and `VerifyingKey.verify`; it does
not call `sign_digest`, ECDH, recovery, or P-256. The actual reported vulnerable
operation is therefore not reachable. Private-key material is used in the
legacy server-wallet generation, validation, and signing paths; it must not be
treated as a routine false positive even though the specific advisory condition
is absent.

### Legacy Signing Call Graph

```text
FastAPI/systemd: uvicorn api:app
  -> api imports blockchain, Wallet, Transaction
  -> api module initialization: Wallet() x3
  -> wallet.generate_key_pair() -> ecdsa SECP256k1 key generation

POST /generate_wallet (development only) -> Wallet() -> key generation
POST /add_transaction (registered legacy wallet; no development guard)
  -> validate_private_key -> Transaction.sign_transaction -> Blockchain.add_transaction
  -> Transaction.is_valid -> ecdsa verification
Legacy /add_block (development only) -> validates legacy transactions
Peer block receive -> Block.from_dict -> Transaction.from_dict
  -> _validate_block_transactions -> Transaction.is_valid -> ecdsa verification

Supported native flow
  MetaMask personal_sign -> eth-account Account.recover_message
  -> wallet_auth/native_transfer -> native transaction, vote, submission checks
```

`wallet.py`, `transaction.py`, and `zoidbergCoin.py` are the only source
modules importing `ecdsa`; `blockchain.py` does not import it directly.
`Wallet` and `Transaction` are active compatibility components, not merely
dead code: they are instantiated in API startup/tests, serialized in legacy
blocks, and reached by peer validation. The direct legacy transaction route is
not called by the supported UI or deployment documentation, but current tests
exercise it with a private key. It accepts attacker-controlled public key,
recipient, amount, and private-key query inputs; a successful request requires
a registered wallet and matching key. It never reaches the advisory's P-256
`sign_digest` condition.

## 6. Cryptographic Encoding And Compatibility Requirements

Observed legacy properties (verified with ephemeral non-recorded test keys):

- Curve: SECP256k1, supported by `cryptography.ec.SECP256K1`.
- Private key: 32-byte scalar, lowercase hexadecimal in `Wallet`.
- Wallet public key: 33-byte compressed SEC point (`02`/`03` plus 32-byte X),
  lowercase hexadecimal. `cryptography` generated the byte-identical compressed
  point for the same scalar.
- Legacy `Transaction` signature: `ecdsa.sign` default SHA-1, raw fixed-width
  `r || s` (64 bytes), base64 encoded. It is neither DER nor recoverable.
- Existing raw signatures verified after conversion to DER for `cryptography`'s
  verifier; new `cryptography` signatures must be converted from DER back to
  exactly 64-byte `r || s` before storing them.
- The current call uses randomized `sign`, not deterministic signing. Exact
  fresh-signature byte equality is not an existing promise, but encoding,
  verification, and signed-payload equality are required.
- Current code does not canonicalize low-S. A migration must characterize and
  retain the current acceptance of both valid S ranges, or make an explicitly
  approved compatibility decision. It must not silently invalidate historical
  signatures.
- `Wallet.verify_signature` strips the compressed key prefix before calling
  `ecdsa`, which rejects the remaining 32 bytes. This existing broken helper is
  distinct from `Transaction.is_valid`, which passes the complete 33-byte key.
  The migration must explicitly decide and test this behavior, not accidentally
  rely on it.
- Legacy transaction signature text participates in legacy block hashing and
  also appears in the Protocol v1 consensus transaction payload. Native
  transaction IDs are computed from canonical native fields before the
  signature; their MetaMask signature is separately carried in records. Do not
  rewrite existing signature bytes, block hashes, transaction IDs, or genesis.

Required characterization fixtures must use disposable test-only material and
contain no operator wallet material: private-scalar-to-compressed-public-key
round trips; existing valid/invalid raw signatures; malformed key/signature
lengths; raw-to-DER conversion; high-S behavior; the exact legacy concatenated
transaction message; `Wallet.sign_data`; deserialized legacy blocks; peer block
receipt; and unchanged Protocol v1/genesis/native-transfer golden vectors.

## 7. ecdsa Remediation Options

| Option | Assessment |
| --- | --- |
| A. `cryptography` implementation migration | Recommended. It already exists in the audited dependency set, supports the same curve and compressed-point serialization, and can preserve raw legacy signatures through explicit DER conversion. Medium scope; compatibility fixtures and review are mandatory. |
| B. `eth-keys` implementation migration | Not recommended. It is transitively retained through `eth-account`, supports SECP256k1 and recoverable Ethereum signatures, but its normal API is Keccak/recoverable-signature oriented and is not a drop-in for legacy SHA-1 raw `r || s` signatures or compressed keys. It would require more custom compatibility logic. |
| C. Remove legacy signing | Not safe today. It would break startup wallet creation, the tested legacy endpoint, legacy block deserialization, and peer validation until persisted-data support is deliberately retired. |
| D. External unsupported tool | Not sufficient for `wallet.py`/`transaction.py`; they remain inside the supported backend import/peer graph. It is appropriate only for the separate `zoidbergCoin.py` executable. |
| E. Temporary exact exception | Potentially defensible only for `PYSEC-2026-1325`: the P-256 `sign_digest`/ECDH behavior is demonstrably unused. It needs a named security owner, review date, removal condition (merged compatibility migration), and explicit acceptance of legacy private-key handling risk. It is not selected because the permanent gate must become green. |

This is implementation-affecting only if the listed compatibility properties
hold. Any change to serialized bytes, validity semantics, hashes, or protocol
signature meaning is protocol-affecting and must stop for separately approved
versioned-protocol review.

## 8. Transformers Advisory Reachability

`sentence_transformers` is imported only by `zoidbergCoin.py`; no source module
imports `transformers` or `torch` directly. `zoidbergCoin.py` immediately loads
the remote Hugging Face identifier `all-MiniLM-L6-v2` through
`SentenceTransformer(...)`; absent a cached model this downloads remote model,
tokenizer, and configuration artifacts. No user-controlled model name, path,
repository, tokenizer file, serialized model, generation setting,
`from_pretrained`, `Trainer`, `torch.load`, `save_pretrained`, or
`trust_remote_code` use exists in project code. The source does not call the
loaded model after construction.

The supported `uvicorn api:app` node imports `blockchain.py`, which uses
Pillow, ImageHash, and pytesseract for media/image/OCR processing. Submission,
evaluation, certificate, and mint routes do not import the legacy executable
or ML stack. The supported node does not require sentence-transformers.

| Advisory | Vulnerable behavior | Actual ZoidbergChain reachability |
| --- | --- | --- |
| PYSEC-2025-217 | X-CLIP untrusted checkpoint deserialization | Not used; no X-CLIP/checkpoint path. |
| PYSEC-2026-2290 | LightGlue malicious repository/config remote code | Not used; no LightGlue/AutoModel path. |
| PYSEC-2026-2288 | Trainer `torch.load` malicious RNG checkpoint | Not used; no Trainer/checkpoint path. |
| PYSEC-2026-2289 | malicious `_attn_implementation_internal` config | Not used; no causal-LM loader/config path. |
| GHSA-xrqw-3rrv-vx5w | tokenizer/processor save path traversal | Not used; no tokenizer/processor save path. |

The legacy executable's unconditional remote model identifier is a supply-chain
and operational risk of its own, but it is not a supported node or consensus
path. Model A and the accepted-media/certificate flow are unchanged.

## 9. Stable ML Options

Current package-index versions: `sentence-transformers 6.0.1`, `transformers
5.16.1`, and `torch 2.13.0`. In a separate Python 3.13 candidate environment,
the stable `sentence-transformers 6.0.1` plus `transformers 5.16.1` resolved,
passed `pip check`, and imported `SentenceTransformer`, `AutoModel`, and
`AutoTokenizer`. It selected `torch 2.13.0`, `tokenizers 0.23.1`,
`huggingface-hub 1.29.0`, `hf-xet`, and `typer`. A full-environment audit also
reported six current `pip 25.1.1` advisories unrelated to the ML candidates;
none were ML package findings. The exact CI requirements audit remains the
authoritative gate result.

| Option | Assessment |
| --- | --- |
| A. Upgrade to sentence-transformers 6.0.1 / Transformers 5.16.1 | Stable and Python-3.13 resolvable, but a major ML migration. It changes tokenizer/hub dependencies and requires model download, embedding-output, and threshold decision fixtures. Because this executable does not influence current originality decisions, it is unnecessary scope. |
| B. Keep sentence-transformers 3.3.1 and constrain Transformers | Not viable: its declared compatible range is `>=4.41,<5`, while the relevant fixed releases are 5.x. No safe non-yanked all-fixed 4.x result was reported. |
| C. Remove sentence-transformers with dead executable | Recommended after confirming the unsupported status and removing the executable. No supported node capability is lost; Pillow/ImageHash/pytesseract remain the current originality path. Small scope. |
| D. Move to a documented optional unsupported tool | Safe only with owner approval and isolated optional requirements/documentation; it retains a remote-model attack surface and does not solve the audit unless excluded from the main CI requirement set. Less small than removal. |
| E. Replace the ML implementation | Unjustified without a product requirement. It would need output/threshold equivalence and could affect originality decisions if ever wired into consensus-adjacent acceptance. |
| F. Temporary exact exceptions | Technically defensible only while the demonstrably unsupported executable is being removed or isolated. One exception per listed advisory needs owner, rationale, review date, and removal condition. Do not select it as a shortcut. |

## 10. Advisory-Exception Analysis

No suppression exists. No exception is selected for this task.

- `PYSEC-2026-1325`: a temporary exact exception could be defensible because the
  documented P-256 `sign_digest`/ECDH conditions are not used. It must not hide
  the separate risk of legacy private-key operations and must expire when the
  implementation migration removes `ecdsa`.
- `PYSEC-2025-217`, `PYSEC-2026-2290`, `PYSEC-2026-2288`, `PYSEC-2026-2289`, and
  `GHSA-xrqw-3rrv-vx5w`: a temporary exact exception could be defensible only
  while the unsupported `zoidbergCoin.py` is removed or isolated. Its remote
  model load makes the package reachable if an operator manually runs it, so an
  exception is not a claim that the executable is safe.

Every exception would require a security owner, written risk acceptance,
specific advisory ID, review date, and removal condition. A permanent red gate
or a convenience exception is unacceptable.

## 11. Recommended Implementation Sequence

1. **Legacy cryptography characterization (first).** Add disposable fixtures
   and tests before changing implementation. Likely files: new focused tests
   under `tests/blockchain`/`tests/api`, plus existing Protocol v1 and peer
   tests. Stop if a historical signature/key/block cannot be characterized
   without changing a protocol-visible byte or if persisted deployment data
   needs unsupported formats.
2. **Behavior-preserving `ecdsa` migration.** Update `wallet.py` and
   `transaction.py` to use `cryptography`; retain exact legacy serialization and
   validation via explicit conversion. Update the applicable requirements files
   only after tests pass. Re-run startup, legacy route, peer block, full backend,
   integration, `pip check`, and exact audit tests. Stop for security/protocol
   review if low-S, SHA-1, key parsing, or historical verification differs.
3. **Remove unsupported ML executable.** With owner confirmation that
   `zoidbergCoin.py` has no supported operator workflow or retained data
   contract, remove it and `sentence-transformers` from the main requirements
   aggregate; update only documentation that mentions its supported status.
   Do not replace Model A. Re-run the complete supported-node tests and audit.
4. **Final security verification.** In a clean Python 3.13 environment install
   `requirements-test.txt`, run `pip check`, exact `pip-audit --strict`, backend
   and integration tests, repository hygiene, secret scan as available, and
   `git diff --check`. The audit must be green without exclusions.

Use a high-reasoning, security-focused implementation agent with an independent
cryptography review. Owner approval is required before retiring a legacy
operator/data-compatibility path and before any behavior that could alter
historical verification or protocol-visible bytes.

## 12. Remaining Risks And Acceptance Result

Until follow-up work lands, the CI Python audit remains red by six unsuppressed
findings. The legacy transaction endpoint accepts private keys in a query
parameter and lacks an explicit development-mode guard; this analysis records
the fact but does not expand scope to remediate it. Historical wallet/key state
was previously tracked and is addressed by the repository-hygiene owner
response, not by this task.

Task 4C acceptance result: **PASS** for the requested analysis and decision.
The audit was reproduced; actual call paths, cryptographic compatibility,
stable ML alternatives, advisory-exception eligibility, a smallest safe
sequence, and owner decisions are documented. The two required decision reports
are the only repository changes.

## Task 4D characterization note

The checked-in supported requirement remains `ecdsa==0.19.2`. The local `.venv`
available during Task 4D imported `ecdsa 0.19.0`, not 0.19.2. Its inspected
`SigningKey.sign` and `VerifyingKey.verify` defaults nevertheless matched the
documented SHA-1 and raw `r || s` compatibility behavior. This is local
environment drift, not a changed audit conclusion; the pinned CI environment
must execute the new compatibility suite before a dependency migration.

## Task 4E: Legacy SECP256K1 Migration

Task 4E replaced direct `ecdsa` use in `wallet.py`, `transaction.py`, and the
retained `zoidbergCoin.py` legacy executable with the already pinned
`cryptography==50.0.0`; it did not remove or otherwise change the executable's
Transformers behavior. `requirements-core.txt` no longer declares `ecdsa`.

The replacement generates and loads valid 32-byte SECP256K1 scalars, preserves
lowercase generated scalar and compressed SEC public-key encodings, signs the
original UTF-8 message once with SHA-1, and translates `cryptography` DER
signatures to the historical fixed-width raw `r || s` standard-base64 format.
Verification decodes the historical raw form, checks length and scalar ranges,
translates it to DER, and accepts both Task 4D low-S and high-S fixture forms.
Historical signature text remains stored verbatim, so legacy block hashes and
Protocol v1 payload semantics are unchanged. No stored data migration or
signature/block normalization was added.

The Task 4D fixed vectors remain explicitly documented as originating from the
historical `ecdsa` implementation and continue to be the compatibility oracle.
The historical broken compressed-key `Wallet.verify_signature` helper remains
false for that fixture; Transaction and peer validation continue to use the
full compressed-point path. MetaMask `personal_sign`, wallet authentication,
native transfers, votes, submissions, peer authentication, and Protocol v1
signatures were not changed.

This resolves `PYSEC-2026-1325` by removing `ecdsa` from the supported
installation. The five Transformers advisories remain unresolved and are still
reserved for the separately scoped legacy-ML decision; this migration does not
claim that the complete audit gate is green.
