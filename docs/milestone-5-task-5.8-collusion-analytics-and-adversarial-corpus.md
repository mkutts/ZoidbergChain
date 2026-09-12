# Milestone 5 Task 5.8: Collusion analytics and adversarial corpus

## Boundary and architecture

`services/collusion_analytics_service.py` is a read-only projection over durable
accepted votes, submission creators, reviewer states, and settled/included/finalized
native ZOID transfers. Alerts are recomputed locally, are not peer messages, and are
not stored in consensus tables. Deleting or recomputing an alert cannot affect chain
validity. IP addresses, browser/device fingerprints, cookies, geolocation, and
operator notes are not inputs.

The service returns stable `collusion:<sha256>` IDs based on alert version, analysis
version, reason code, sorted entities, canonical reference, epochs, and metrics.
Operational timestamps are excluded except from the explicitly advisory synchronized
timing metric. Schema fields are `alert_id`, `alert_version`, `reason_code`,
`severity`, reviewer/creator/submission arrays, epochs, reference height/hash,
summary, metrics, first/last observed epoch, and `analysis_version`.

Reason codes: `HIGH_COVOTING_CORRELATION`, `RECURRING_REVIEWER_CLUSTER`,
`CREATOR_REVIEWER_RECURRENCE`, `CREATOR_FUNDED_REVIEWERS`,
`FRESH_WALLET_COORDINATION`, `SYNCHRONIZED_VOTING_PATTERN`, and
`REPEATED_SAME_CREATOR_SUPPORT`. They describe suspicious correlated patterns, not
proof of collusion.

## Transparent thresholds

- Pairs require at least three common reviews, at least two persisted status epochs,
  and 4/5 agreement (integer comparison). Six reviews across three epochs with an
  additional corroborating signal is HIGH; four across two is MEDIUM; otherwise LOW.
- Strong-pair connected components of three or more reviewers are recurring clusters.
- Creator/reviewer recurrence requires three reviews across two epochs and at least
  60% of that reviewer's recorded reviews. Three `original` choices add the repeated
  support finding.
- Funding requires a settled/included/finalized creator-to-reviewer transfer **and**
  two later-associated recorded reviews; a one-off transfer alone never alerts.
- Fresh status/probation alone never alerts. It requires a correlated pair and
  concentration on a creator. Qualification timing uses persisted status height.
- Synchronized voting requires three same-choice pair votes within five minutes across
  two epochs. `observed_at` is a durably stored operational value, used only here and
  never by consensus.

## API and isolation

Public read-only endpoints are `/analytics/collusion/alerts`, plus filtered reviewer,
submission, and creator variants. Every response says `non_consensus: true`.
There is no mutation endpoint, migration, index, peer payload, eligibility change,
vote-weight change, quorum change, certificate mutation, originality decision, or
reputation action. Reviewer Policy v1, Certificate v3 fixed quorum/validity, and
Reputation Rule v2 remain unchanged.

## Corpus, observations, and scaling

`scripts/task_5_8_adversarial_corpus.py` runs the retained Task 5.3 JPEG, resize,
crop, border, brightness/color, metadata, OCR/template/generic-text, posterized and
exact cases with fresh-wallet, coordinated-cluster, creator-funded, one-off-transfer,
and diverse-reviewer analytics cases. Its synthetic labels report TP/TN/FP/FN
reproducibly; they are corpus observations, not global performance claims. Pair
generation is O(sum(submission reviewers squared)); current basic use is hundreds of
reviewers/thousands of votes. Indexing votes by submission/reviewer and native
transfers by sender/recipient would be the first scaling improvement if needed.

## Security matrix

| Attack | Milestone 5 behavior |
| --- | --- |
| Exact media duplicate | HARD_REJECT |
| Fuzzy duplicate/template derivative | FLAG_FOR_REVIEW / PARTIALLY_DETECTABLE |
| Creator self-vote, replay, equivocation, rate abuse | PROTOCOL_REJECT and applicable REPUTATION_PENALTY |
| Fresh-wallet swarm, coordinated voting, creator-funded reviewers, recurring ring | ANALYTICS_ALERT when repeated observable evidence meets thresholds |
| Private multi-wallet ownership with no observable linkage | NOT_DETECTABLE |

Remaining risk: correlated honest reviewers and legitimate funding can create alerts;
private coordination remains outside this design. Task 5.9 should evaluate operator
triage workflow and scaling indexes, not introduce automatic penalties without a new
consensus policy.
