"""Fresh-process oracle comparison; reconstruct exclusively from canonical DB."""
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_v3.admission import TestOnlyConfig
from canonical_v3 import media
from codec_prototype.isolated_decoder import IsolatedDecoder
from scripts.milestone_7_task_7_11_storage import CTX
from verification.task721.bridge import DisposableStore, retrieve


def main():
    expected = json.load(sys.stdin)  # Comparison oracle only; never decode input.
    def forbidden(_):
        raise AssertionError('restart retrieval attempted recompression')
    media._compress_default = forbidden
    config = TestOnlyConfig(CTX, True)
    with IsolatedDecoder() as decoder, DisposableStore(sys.argv[1], config, decoder=decoder) as store:
        rows = []
        for identity, original in expected.items():
            result = retrieve(store, identity, config, decoder=decoder)
            assert result.body == base64.b64decode(original)
            rows.append(dict(block_hash=identity, original_sha256=result.original_sha256,
                             original_size=result.original_size, mime_type=result.mime_type, exact=True))
        # Every expected record was authenticated above; the count detects
        # unexpected extras without repeating all native decoder operations.
        assert store.connection.execute('SELECT count(*) FROM blocks').fetchone()[0] == len(expected)
        print(json.dumps(dict(status='PASS', fresh_process=True, rows=rows)))


if __name__ == '__main__':
    main()
