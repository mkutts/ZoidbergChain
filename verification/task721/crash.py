"""Deliberate process exit during inherited V3Store writes; disposable DB only."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_v3.admission import TestOnlyConfig
from codec_prototype.isolated_decoder import IsolatedDecoder
from scripts.milestone_7_task_7_11_storage import CTX, FIXTURES
from verification.task721.bridge import DisposableStore


def main():
    stage, path = sys.argv[1:]
    with IsolatedDecoder() as decoder, DisposableStore(path, TestOnlyConfig(CTX, True), decoder=decoder) as store:
        put_indexes = store._put_indexes
        def interrupted(connection, record):
            if stage == 'after-blob':
                os._exit(83)
            put_indexes(connection, record)
            if stage == 'after-index':
                os._exit(83)
        store._put_indexes = interrupted
        store.insert((FIXTURES/'block-identity.json').read_bytes())
        os._exit(83)  # COMMIT completed but acknowledgement lost.


if __name__ == '__main__':
    main()
