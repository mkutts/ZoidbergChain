"""Fail-closed checks for the historical identity/observation distinction."""
from copy import deepcopy
import json

import pytest

from scripts import milestone_7_task_7_3_corpus as corpus


@pytest.fixture(scope='module')
def frozen_and_actual():
    return json.loads(corpus.MANIFEST_PATH.read_bytes()), corpus.make_manifest()


def test_current_observations_are_not_historical_corpus_identity(monkeypatch, frozen_and_actual):
    frozen, actual = frozen_and_actual
    monkeypatch.setattr(corpus, 'make_manifest', lambda: actual)
    assert corpus.verify_manifest(frozen) == corpus.image_statistics(frozen)


@pytest.mark.parametrize('mutation', ['sha256', 'original_byte_size', 'id', 'category', 'dimensions',
                                    'sample_order', 'missing_sample', 'environment', 'schema', 'extra_field', 'missing_observation'])
def test_identity_environment_and_schema_drift_fail_closed(monkeypatch, frozen_and_actual, mutation):
    frozen, actual = frozen_and_actual
    changed = deepcopy(actual)
    if mutation == 'sample_order':
        changed['samples'][0], changed['samples'][1] = changed['samples'][1], changed['samples'][0]
    elif mutation == 'missing_sample':
        changed['samples'].pop()
    elif mutation == 'environment':
        changed['environment']['pillow'] = 'different'
    elif mutation == 'schema':
        changed['corpus_version'] = 'different'
    elif mutation == 'extra_field':
        changed['samples'][0]['new_unrecognized_field'] = True
    elif mutation == 'missing_observation':
        changed['samples'][0].pop('accepted_byte_size')
    else:
        changed['samples'][0][mutation] = 'different'
    monkeypatch.setattr(corpus, 'make_manifest', lambda: changed)
    with pytest.raises(ValueError, match='Manifest does not match'):
        corpus.verify_manifest(frozen)
