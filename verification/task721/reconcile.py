"""Read-only integer reconciliation of frozen Task 7.20 evidence."""
from collections import defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def reconcile():
    frozen = json.loads((ROOT/'benchmarks/task720_v1/records.json').read_bytes())
    rows = frozen['rows'] + frozen['sensitivity_rows']
    prefix = '$/envelope/payload/admission_certificate'
    outputs = []
    for row in rows:
        ledger = row['field_ledger']
        assert row['encoded_bytes'] <= row['original_bytes']
        assert row['descriptor_bytes'] <= row['identity_descriptor_bytes']
        assert row['record_bytes'] <= row['identity_record_bytes']
        assert row['base64_media_bytes'] == 4*((row['encoded_bytes']+2)//3)
        assert sum(ledger.values()) == row['record_bytes'] == sum(row['partition'].values())
        assert [k for k in ledger if k.endswith('/media/payload/@content')] == ['$/envelope/payload/media/payload/@content']
        # Every mandatory certificate member is charged, including its key and
        # all nested signed messages/technical observations/digests/signatures.
        from canonical_v3.evidence import CERTIFICATE_FIELDS
        members = {}
        for field in CERTIFICATE_FIELDS:
            base = prefix+'/'+field
            values = {k: v for k, v in ledger.items() if k == base or k.startswith(base+'/')}
            assert values and base+'/@key' in values
            members[field] = sum(values.values())
        structure = ledger[prefix+'/@structure']
        certificate_value = sum(members.values())+structure
        assert certificate_value == row['certificate_value_bytes']
        certificate_member = certificate_value+ledger[prefix+'/@key']
        assert certificate_member == row['partition']['certificate_bytes']
        outputs.append(dict(population=row['population'], id=row['id'], original_sha256=row['original_sha256'],
            original_bytes=row['original_bytes'], encoded_bytes=row['encoded_bytes'],
            base64_bytes=row['base64_media_bytes'], base64_expansion=row['base64_media_bytes']-row['encoded_bytes'],
            descriptor_framing=row['partition']['serialized_media_representation_bytes']-row['base64_media_bytes'],
            media_representation_bytes=row['partition']['serialized_media_representation_bytes'],
            complete_record_bytes=row['record_bytes'], codec=row['codec'],
            certificate_value_bytes=certificate_value, certificate_member_bytes=certificate_member,
            certificate_key_bytes=ledger[prefix+'/@key'], certificate_structure_bytes=structure,
            mandatory_certificate_member_bytes=members, media_payload_occurrences=1))
    groups = {}
    for population in sorted({r['population'] for r in outputs} | {'all-78-records'}):
        selected = outputs if population == 'all-78-records' else [r for r in outputs if r['population'] == population]
        unique = defaultdict(list)
        for r in selected:
            unique[r['original_sha256']].append(r)
        # Different sensitivity representations of the same original are not
        # added into the unique-object payload total. Report their ranges.
        fields = ('original_bytes', 'encoded_bytes', 'base64_bytes', 'media_representation_bytes',
                  'complete_record_bytes', 'certificate_value_bytes', 'certificate_member_bytes',
                  'certificate_key_bytes', 'base64_expansion', 'descriptor_framing')
        groups[population] = dict(records=len(selected), unique_objects=len(unique),
            per_record_totals={k:sum(r[k] for r in selected) for k in fields},
            per_unique_object_totals={k:dict(min=sum(min(r[k] for r in variants) for variants in unique.values()),
                                            max=sum(max(r[k] for r in variants) for variants in unique.values())) for k in fields})
    current = groups['production-like']['per_record_totals']
    assert current['original_bytes'] == 11521163
    assert current['encoded_bytes'] == 11002892
    assert current['media_representation_bytes'] == 14678466
    assert current['certificate_member_bytes'] == 1073154
    return dict(status='PASS', primary_records=len(frozen['rows']), sensitivity_records=len(frozen['sensitivity_rows']),
        explanation='36 historical + 34 new primary records; 8 sensitivity records reuse 4 new originals. '
                    'Published new totals cover 34 primary objects only. Base64 plus framing explains expansion; '
                    'no selected encoded or descriptor expansion and one media payload per record.',
        groups=groups, rows=outputs)


if __name__ == '__main__':
    import sys
    target = Path(sys.argv[1])
    target.write_text(json.dumps(reconcile(),indent=2,sort_keys=True)+'\n', encoding='utf-8')
