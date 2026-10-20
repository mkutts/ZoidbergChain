"""Closed evidence formats and cryptographic commitments, without live policy state."""
from .primitives import (
    bounded, canonical, closed, digest, envelope, expiry, h64, opaque, pattern,
    require, text, uint, verify_signature, wallet, without_digest,
)
from .media import MIMES, MAX_IMAGE, MAX_TEXT

# Pinned engineering statement, not new launch wording or an active policy import.
STATEMENT_ID = 'zoidberg-public-testnet-v1/submitter-rights-permanence/1'
STATEMENT = (
    'I assert that I have the right or authorization to submit this exact content '
    'under the identified ZoidbergChain Public Testnet media-admission policy. '
    'I understand that, if accepted and finalized, the accepted media bytes become '
    'permanently replicated in immutable ZoidbergChain history and cannot be removed '
    'through ordinary moderation. This testnet attestation is my signed assertion; '
    'it is not proof of ownership, a legal determination, a waiver, or a license '
    'beyond this explicit assertion.'
)
TECHNICAL_FIELDS = '''evidence_version validator_id policy_id policy_version policy_digest
outcome reason_codes detected_media_type detected_mime_type raw_media_byte_length
raw_media_sha256 raw_media_semantics width_pixels height_pixels frame_count
aggregate_decoded_pixels evidence_digest'''.split()
ATTESTATION_FIELDS = '''attestation_version statement_id statement_version domain protocol_version
network_id signature_scheme signer_wallet signature nonce canonical_payload
canonical_payload_digest canonical_message canonical_message_hash'''.split()
ATTESTATION_PAYLOAD_FIELDS = '''attestation_version statement_id statement_version statement wallet_address
submission_id raw_media_sha256 policy_id policy_version policy_digest technical_evidence_version
technical_evidence_digest nonce issued_at expires_at network_id'''.split()
VOTE_FIELDS = '''submission_id content_hash voter voter_wallet_address vote_type dimension vote_version
protocol_version network_id signature_scheme vote_signature vote_message vote_nonce signed_message_hash
vote_issued_at vote_expires_at vote_identity reviewer_policy_version reputation_rule_version reviewer_status
reviewer_eligible reviewer_status_effective_height reviewer_status_reference_block_hash'''.split()
TALLY_FIELDS = '''dimension policy_version policy_digest eligible_valid_votes established_reviewer_votes
positive_votes negative_votes unsure_votes approval_denominator approval_threshold_bps quorum_reached
resolved outcome vote_set_digest'''.split()
CERTIFICATE_FIELDS = '''certificate_version network_id submission_id content_hash creator_wallet policy_id
policy_version policy_digest technical_evidence_version technical_evidence attestation_version attestation
review_policy_version review_policy_digest votes originality admissibility certificate_digest'''.split()
POSITIVE = dict(originality='original', admissibility='admissible')
NEGATIVE = dict(originality='not_original', admissibility='not_admissible')


def certificate_size_bound():
    """Retained field caps, including every closed certificate key/delimiter."""
    widths = dict(certificate_version=1, network_id=66, submission_id=34, content_hash=66,
                  creator_wallet=44, policy_id=84, policy_version=1, policy_digest=66,
                  technical_evidence_version=1, technical_evidence=8192,
                  attestation_version=1, attestation=16384, review_policy_version=1,
                  review_policy_digest=66, votes=32 * 4096 + 33,
                  originality=8192, admissibility=8192, certificate_digest=66)
    require(set(widths) == set(CERTIFICATE_FIELDS), 'certificate_size_inventory')
    return 2 + len(widths) - 1 + sum(len(k) + 3 + v for k, v in widths.items())


def fixed(value, expected):
    """Typed equality: JSON true must never satisfy an integer version."""
    require(canonical(value) == canonical(expected), 'fixed_value')


def fields_equal(value, expected):
    for key, wanted in expected.items():
        fixed(value[key], wanted)


def policy_fields(ctx):
    return dict(policy_id=ctx.media_policy_id, policy_version=2, policy_digest=ctx.media_policy_digest)


def validate_technical(value, ctx):
    closed(value, TECHNICAL_FIELDS)
    bounded(value, 8192)
    fields_equal(value, dict(evidence_version=1, validator_id='zoidberg-media-technical-validator/1',
                            outcome='ACCEPT', reason_codes=['ACCEPTED_POLICY_METADATA'], **policy_fields(ctx)))
    mime = value['detected_mime_type']
    require(type(mime) is str and mime in MIMES, 'technical_mime')
    detected = ('plain_utf8_text', 'jpeg', 'png', 'gif', 'webp')[MIMES.index(mime)]
    fixed(value['detected_media_type'], detected)
    h64(value['raw_media_sha256'])
    uint(value['raw_media_byte_length'], 1, MAX_TEXT if mime == 'text/plain' else MAX_IMAGE)
    image_fields = ('width_pixels', 'height_pixels', 'frame_count', 'aggregate_decoded_pixels')
    if mime == 'text/plain':
        fixed(value['raw_media_semantics'], 'policy_canonical_utf8_text')
        for key in image_fields:
            fixed(value[key], None)
    else:
        fixed(value['raw_media_semantics'], 'exact_input_bytes')
        for key, maximum in zip(image_fields, (4096, 4096, 60, 16777216)):
            uint(value[key], 1, maximum)
    without_digest(value, 'evidence_digest')


def attestation_bytes(payload, ctx):
    closed(payload, ATTESTATION_PAYLOAD_FIELDS)
    fields_equal(payload, dict(attestation_version=1, statement_id=STATEMENT_ID, statement_version=1,
                              statement=STATEMENT, technical_evidence_version=1, network_id=ctx.network_id,
                              **policy_fields(ctx)))
    wallet(payload['wallet_address'])
    pattern(payload['submission_id'], r'[0-9a-f]{32}')
    h64(payload['raw_media_sha256'])
    h64(payload['technical_evidence_digest'])
    opaque(payload['nonce'])
    expiry(payload['issued_at'], payload['expires_at'])
    message = canonical(envelope(payload, 'submitter-attestation', ctx))
    require(len(message) <= 8192, 'attestation_message_size')
    return message


def validate_attestation(value, ctx):
    closed(value, ATTESTATION_FIELDS)
    bounded(value, 16384)
    payload = value['canonical_payload']
    message = attestation_bytes(payload, ctx)
    fields_equal(value, dict(attestation_version=1, statement_id=STATEMENT_ID, statement_version=1,
                            domain='zoidbergchain/submitter-attestation/v2', protocol_version=2,
                            network_id=ctx.network_id, signature_scheme='personal_sign',
                            signer_wallet=payload['wallet_address'], nonce=payload['nonce'],
                            canonical_message=message.decode('utf-8'),
                            canonical_payload_digest=digest(envelope(payload, 'submitter-attestation', ctx)),
                            canonical_message_hash=digest(envelope(payload, 'submitter-attestation', ctx))))
    verify_signature(message, value['signature'], value['signer_wallet'])


def vote_payload(value, ctx):
    return dict(domain='zoidbergchain/community-review/v3', network_id=ctx.network_id,
                vote_version=3, policy_version=2, policy_digest=ctx.review_policy_digest,
                reviewer_policy_version=1, reputation_rule_version=2,
                wallet_address=value['voter_wallet_address'], submission_id=value['submission_id'],
                content_hash=value['content_hash'], dimension=value['dimension'], choice=value['vote_type'],
                nonce=value['vote_nonce'], issued_at=value['vote_issued_at'], expires_at=value['vote_expires_at'])


def validate_vote(value, ctx):
    closed(value, VOTE_FIELDS)
    bounded(value, 4096)
    pattern(value['submission_id'], r'[0-9a-f]{32}')
    h64(value['content_hash'])
    wallet(value['voter_wallet_address'])
    fields_equal(value, dict(voter=value['voter_wallet_address'], vote_version=3, protocol_version=2,
                            network_id=ctx.network_id, signature_scheme='personal_sign',
                            reviewer_policy_version=1, reputation_rule_version=2, reviewer_eligible=True))
    dimension = value['dimension']
    require(type(dimension) is str and dimension in POSITIVE, 'review_dimension')
    require(type(value['vote_type']) is str and value['vote_type'] in
            (POSITIVE[dimension], NEGATIVE[dimension], 'unsure'), 'review_choice')
    require(type(value['reviewer_status']) is str and value['reviewer_status'] in
            ('PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER'), 'reviewer_status')
    uint(value['reviewer_status_effective_height'])
    h64(value['reviewer_status_reference_block_hash'])
    opaque(value['vote_nonce'])
    expiry(value['vote_issued_at'], value['vote_expires_at'])
    payload = vote_payload(value, ctx)
    message = canonical(payload)
    require(len(message) <= 2048, 'vote_message_size')
    fields_equal(value, dict(vote_message=message.decode('utf-8'), signed_message_hash=digest(payload),
                            vote_identity=digest(dict(payload=payload, signature=value['vote_signature']))))
    verify_signature(message, value['vote_signature'], value['voter_wallet_address'])


def validate_votes(votes, ctx):
    require(type(votes) is list and len(votes) <= 32, 'vote_count')
    for vote in votes:
        validate_vote(vote, ctx)
    order = [(v['dimension'], v['voter_wallet_address'], v['vote_identity']) for v in votes]
    require(order == sorted(order), 'vote_order')
    require(len({(v['dimension'], v['voter_wallet_address']) for v in votes}) == len(votes), 'vote_duplicate')
    for dimension in POSITIVE:
        require(sum(v['dimension'] == dimension for v in votes) <= 16, 'dimension_count')


def _derive_tally(votes, dimension, ctx):
    selected = sorted((v for v in votes if v['dimension'] == dimension), key=lambda v: v['voter_wallet_address'])
    p = sum(v['vote_type'] == POSITIVE[dimension] for v in selected)
    n = sum(v['vote_type'] == NEGATIVE[dimension] for v in selected)
    u = len(selected) - p - n
    e = sum(v['reviewer_status'] == 'ESTABLISHED_REVIEWER' for v in selected)
    d = p + n
    quorum = len(selected) >= 5 and e >= 1
    resolved = quorum and d > 0
    outcome = (POSITIVE[dimension] if p * 10000 >= d * 7000 else NEGATIVE[dimension]) if resolved else 'unresolved'
    projection = [dict(wallet=v['voter_wallet_address'], choice=v['vote_type'],
                       identity=v['vote_identity'], status=v['reviewer_status']) for v in selected]
    return dict(dimension=dimension, policy_version=2, policy_digest=ctx.review_policy_digest,
                eligible_valid_votes=len(selected), established_reviewer_votes=e,
                positive_votes=p, negative_votes=n, unsure_votes=u, approval_denominator=d,
                approval_threshold_bps=7000, quorum_reached=quorum, resolved=resolved,
                outcome=outcome, vote_set_digest=digest(projection))


def derive_tally(votes, dimension, ctx):
    require(type(dimension) is str and dimension in POSITIVE, 'review_dimension')
    validate_votes(votes, ctx)
    return _derive_tally(votes, dimension, ctx)


def validate_tally(value, votes, dimension, ctx):
    require(type(dimension) is str and dimension in POSITIVE, 'review_dimension')
    validate_votes(votes, ctx)
    _validate_derived_tally(value, votes, dimension, ctx)


def _validate_derived_tally(value, votes, dimension, ctx):
    closed(value, TALLY_FIELDS)
    bounded(value, 8192)
    # Full typed equality with the derived object enforces every counter/bool.
    fixed(value, _derive_tally(votes, dimension, ctx))


def validate_certificate(value, ctx):
    closed(value, CERTIFICATE_FIELDS)
    bounded(value, 196608)
    fields_equal(value, dict(certificate_version=2, network_id=ctx.network_id, technical_evidence_version=1,
                            attestation_version=1, review_policy_version=2,
                            review_policy_digest=ctx.review_policy_digest, **policy_fields(ctx)))
    pattern(value['submission_id'], r'[0-9a-f]{32}')
    h64(value['content_hash'])
    wallet(value['creator_wallet'])
    technical, attestation = value['technical_evidence'], value['attestation']
    validate_technical(technical, ctx)
    validate_attestation(attestation, ctx)
    fields_equal(technical, dict(raw_media_sha256=value['content_hash']))
    fields_equal(attestation['canonical_payload'], dict(submission_id=value['submission_id'],
                 wallet_address=value['creator_wallet'], raw_media_sha256=value['content_hash'],
                 technical_evidence_digest=technical['evidence_digest']))
    votes = value['votes']
    validate_votes(votes, ctx)
    for vote in votes:
        fields_equal(vote, dict(submission_id=value['submission_id'], content_hash=value['content_hash']))
        require(vote['voter_wallet_address'] != value['creator_wallet'], 'self_vote')
    for dimension in POSITIVE:
        _validate_derived_tally(value[dimension], votes, dimension, ctx)
        require(value[dimension]['outcome'] == POSITIVE[dimension], 'certificate_not_qualified')
    without_digest(value, 'certificate_digest')
