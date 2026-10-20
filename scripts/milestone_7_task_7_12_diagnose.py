"""Offline Task 7.12 worker diagnostics; does not access chain state."""
from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import platform
import shutil
import sys
import tempfile
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import PIL
from PIL import Image
from media_technical_validation import _decode_image_worker, validate_media_bytes


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--temp-root', type=Path)
    args = parser.parse_args()
    if args.temp_root:
        tempfile.tempdir = str(args.temp_root.resolve(strict=True))
    print(json.dumps({'python': sys.version, 'platform': platform.platform(),
                      'pillow': PIL.__version__, 'temp_root': tempfile.gettempdir()}, indent=2), flush=True)
    buffer = io.BytesIO()
    Image.new('RGB', (3, 2), (12, 34, 56)).save(buffer, format='PNG')
    directory = tempfile.mkdtemp(prefix='zoidberg-media-worker-diagnostic-')
    print('directory:', directory, 'stat:', os.stat(directory), flush=True)
    context = multiprocessing.get_context('spawn' if os.name == 'nt' else 'fork')
    executor = ProcessPoolExecutor(max_workers=1, mp_context=context)
    processes = []
    try:
        future = executor.submit(_decode_image_worker, buffer.getvalue(), 'image/png', 268435456, directory)
        processes = list(executor._processes.values())
        try:
            print('decoded:', future.result(timeout=5), flush=True)
        except Exception:
            traceback.print_exc()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        print('worker exit codes:', [p.exitcode for p in processes], flush=True)
        try:
            shutil.rmtree(directory)
            print('cleanup: complete', flush=True)
        except OSError:
            traceback.print_exc()
    try:
        print('admission:', validate_media_bytes(buffer.getvalue()).result['outcome'], flush=True)
    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    main()
