"""Deterministic planning arithmetic; no throughput or crypto benchmark claim."""
from math import ceil, floor

from .model import canonical, digest


def structural_vote():
    # Literal 7.17O section 4/15 recipe; invalid placeholder key/signature.
    p = dict(domain='zoidbergchain/community-review/network-wide-v1', protocol='zoidbergchain',
             protocol_version=2, review_protocol_version=1, network_id='zoidberg-signing-vector-v2',
             genesis_hash='a'*64, review_policy_digest='b'*64, reviewer_policy_digest='c'*64,
             reputation_policy_digest='d'*64, history_policy_digest='e'*64,
             submission_id='1'*32, original_media_sha256='2'*64, creator_wallet='0x'+'3'*40,
             review_session_id='4'*64, dimension='admissibility', reviewer_wallet='0x'+'5'*40,
             reviewer_public_key='02'+'6'*64, choice='not_admissible',
             eligibility_media_height=9007199254740991, eligibility_media_hash='7'*64,
             eligibility_journal_height=9007199254740734, eligibility_journal_hash='8'*64,
             session_close_height=9007199254740991, vote_sequence=0, vote_nonce='9'*32)
    return dict(payload=p, signature_scheme='personal_sign', signature='0x'+'1'*130)


def calculate(*, votes_per_minute, cadence_seconds=5, batch_bytes=262144,
              vote_bytes=1701, event_bytes=None, vote_cap=24, reserve_bytes=33792,
              proof_bytes=4096, metadata_bytes=1024, outage_hours=6):
    event_bytes = event_bytes or len(canonical(dict(kind='VOTE', payload=dict(signed_vote=structural_vote()))))
    byte_slots = floor((batch_bytes-reserve_bytes)/ (event_bytes+1))
    slots = min(vote_cap, byte_slots) if vote_cap is not None else byte_slots
    assert slots > 0 and cadence_seconds > 0
    capacity_minute = slots*60/cadence_seconds
    required_batches_hour = ceil(votes_per_minute*60/slots)
    backlog = votes_per_minute*60*outage_hours
    spare_minute = capacity_minute-votes_per_minute
    clear_minutes = backlog/spare_minute if spare_minute > 0 else None
    daily_votes = votes_per_minute*1440
    # Offered storage demand, feasible admitted demand only when stable.
    vote_daily = daily_votes*vote_bytes
    event_daily = daily_votes*(event_bytes+1)
    ticks_daily = 86400/cadence_seconds
    archive_daily = event_daily+ticks_daily*(metadata_bytes+proof_bytes)
    return dict(votes_per_minute=votes_per_minute, cadence_seconds=cadence_seconds,
                batch_bytes=batch_bytes, vote_bytes=vote_bytes, event_bytes=event_bytes,
                reserve_bytes=reserve_bytes, vote_cap=vote_cap, byte_slots=byte_slots,
                votes_per_full_batch=slots, capacity_votes_minute=capacity_minute,
                required_batches_second=required_batches_hour/3600,
                required_journal_blocks_hour=required_batches_hour,
                available_blocks_hour=3600/cadence_seconds,
                stable=votes_per_minute <= capacity_minute,
                backlog_growth_votes_hour=max(0, (votes_per_minute-capacity_minute)*60),
                outage_hours=outage_hours, outage_backlog_votes=backlog,
                clear_backlog_minutes=clear_minutes,
                offered_vote_storage_daily_bytes=vote_daily,
                offered_vote_storage_year_bytes=vote_daily*365,
                offered_vote_storage_three_year_bytes=vote_daily*1095,
                archive_daily_bytes=archive_daily, archive_year_bytes=archive_daily*365,
                archive_three_year_bytes=archive_daily*1095,
                four_validator_archive_three_year_bytes=archive_daily*1095*4,
                replication_payload_daily_bytes=vote_daily*3,
                replication_payload_bytes_second=vote_daily*3/86400,
                four_node_signature_checks_second=votes_per_minute*4/60,
                per_node_signature_checks_second=votes_per_minute/60,
                planning_bft_phase_bytes_day=ticks_daily*24576,
                full_cap_body_and_16k_proof_three_year_bytes=ticks_daily*(batch_bytes+16384)*1095)


def report():
    vote = structural_vote()
    ev = len(canonical(dict(kind='VOTE', payload=dict(signed_vote=vote))))
    rows = [calculate(votes_per_minute=r, cadence_seconds=c) for c in (1, 5, 10)
            for r in (10, 100, 1000, 10000)]
    return dict(classification='modeled projections, structural serialization measurements only',
                measurement=dict(payload_bytes=len(canonical(vote['payload'])),
                                 signed_vote_bytes=len(canonical(vote)), vote_event_bytes=ev,
                                 payload_sha256=digest(vote['payload'])),
                assumptions=dict(reserve_bytes=33792, metadata_bytes=1024, proof_mean_bytes=4096,
                                 close_reserved_bytes=32768, years_days=1095,
                                 network_validators=4, transport_and_indexes_excluded=True),
                workloads=rows,
                sensitivities=[calculate(votes_per_minute=1000, vote_cap=None),
                    calculate(votes_per_minute=1000, vote_bytes=4096, event_bytes=8192),
                    calculate(votes_per_minute=10000, vote_cap=None, vote_bytes=4096, event_bytes=8192)],
                burst=dict(votes=10000, normal_votes_minute=100, capacity_votes_minute=288,
                           clear_minutes=10000/(288-100),
                           session_window_votes=255*24,
                           same_session_burst_admissible_upper_bound=6120,
                           same_session_burst_at_least_late=3880),
                binding=dict(proposed_limit=8192, measured_canonical_maximum=False,
                             media_limit=3145728, maximal_base64=2796204,
                             remaining_after_binding_and_native=243028))
