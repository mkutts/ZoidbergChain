# Milestone 6 Task 6.2 — Public Testnet v1 media-admission policy

Task 6.2 implements the versioned policy model specified by Task 6.1. It does
not activate the policy or implement Tasks 6.3 and later enforcement.

## Identity

- Policy ID: `zoidberg-public-testnet-v1/media-admission/1`
- Integer lookup version: `1`
- Semantic version: `1.0.0`
- Network: `zoidberg-public-testnet-v1`
- Protocol version: `1`
- Canonical form: Protocol v1 canonical JSON
- Canonical digest:
  `96ca86e260de39645ac835e3be8413cdcde91a0d385bf3d951c8f3efe25b5915`

Unknown versions fail closed with `UNKNOWN_POLICY_VERSION`. The module returns
deep copies so callers cannot mutate process-global network policy.

## Frozen values and scope

Consensus/protocol fields are detected-and-validated MIME/type authority;
JPEG, PNG, GIF, WebP and canonical UTF-8 text allowlists; 256 KiB accepted image
and text limits; 512 KiB canonical non-genesis block limit; dimensions 1–4,096;
60 frames; 16,777,216 aggregate decoded pixels; RGB/RGBA convertibility;
complete-container/all-frame requirements; archive, polyglot, active-content,
executable and script rejection; metadata bounds; and peer page/media limits.
These values come only from the versioned object and cannot be changed through
environment variables.

Local-defense defaults are a 5 MiB staged payload, a 5 MiB + 64 KiB multipart
body, a 320 KiB text JSON body, two-second structural decode ceiling,
five-second OCR ceiling, and 256 MiB worker memory. Machine-local overrides may
only tighten these values. Time/resource termination rejects local admission but
is not deterministic evidence that another machine's structurally valid media
is protocol-invalid.

The 5 MiB/500 KB mismatch is resolved exactly as Task 6.1 specifies: staging is
allowed up to 5 MiB, accepted immutable media is limited to 256 KiB, and both
producer and validator will ultimately enforce the 512 KiB canonical block cap.

## Deterministic evaluation

`evaluate_media_admission_policy()` evaluates metadata supplied by later
technical validation: canonical MIME, declared-MIME mismatch, byte/request/block
limits, dimensions, pixels, frames, archive/polyglot/active payload
classification, malformed/unsupported metadata, and resource termination. It
does not claim to detect those properties from bytes. Outcomes and reason codes
are machine-readable, unique, and sorted.

No policy identity is yet persisted on submissions. Doing so now would falsely
label historical and newly created submissions as admitted before Task 6.3+
enforcement exists. Existing records remain unchanged/readable; later admission
records, certificates, and blocks can durably use the stable ID, version, and
digest exposed here.

## POLICY TODO — OWNER DECISION REQUIRED

Public minting remains fail-closed and inactive until owners resolve:

- prohibited-content definitions, jurisdiction, appeals, rejected-byte
  retention, and emergency contact;
- denylist ownership, signing, distribution, and activation;
- safety-review authority, quorum, conflicts, recusals, welfare, and audit;
- permanent-publication/rights attestation wording;
- whether animated GIF/WebP remains enabled at activation;
- safe-preview encoding and animation review;
- raw-media access after presentation suppression;
- activation height and treatment of in-flight/legacy submissions;
- isolated-worker, malware-signature, incident-response, reporting, and
  monitoring ownership/capacity.

## Deferred enforcement

Task 6.3 must implement complete byte detection, full decoding, resource-bomb
defenses, and worker enforcement. Task 6.4 must implement signed attestation.
Task 6.5 must implement separate admissibility voting/certificate bindings.
Quarantine, reports, disputes, safe serving, activation, and other later
Milestone 6 work are also unchanged.
