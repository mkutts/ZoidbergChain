"""Task 7.12: real image worker lifecycle and local-failure boundaries."""
import errno
import io
import os
import tempfile
import time
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest
from PIL import Image

import media_technical_validation as technical
from media_admission_policy import REASON_MALFORMED_MEDIA, REASON_RESOURCE_LIMIT_TERMINATED


def _image(fmt='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', (3, 2), (12, 34, 56)).save(buffer, format=fmt)
    return buffer.getvalue()


def _permission_worker(*args):
    raise PermissionError(errno.EACCES, 'injected worker permission denial')


def _crash_worker(*args):
    os._exit(23)


def _timeout_worker(*args):
    time.sleep(30)


def _decode_os_error_worker(error_number, *args):
    def denied(*a, **k):
        raise OSError(error_number, 'injected decoder OS failure')
    Image.open = denied
    return technical._decode_image_worker(*args)


def _observing_worker(payload, mime, memory, directory):
    original_open = Image.open
    def checked_open(*args, **kwargs):
        assert Path.cwd() == Path(directory)
        assert os.listdir(directory) == []
        return original_open(*args, **kwargs)
    Image.open = checked_open
    try:
        result = technical._decode_image_worker(payload, mime, memory, directory)
    finally:
        Image.open = original_open
    return {**result, 'pid': os.getpid(), 'directory': directory,
            'entries': os.listdir(directory)}


@pytest.fixture
def worker_root(tmp_path, monkeypatch):
    root = tmp_path / 'operator-temp'
    root.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(root))
    return root


@pytest.mark.parametrize('fmt,mime', [('JPEG', 'image/jpeg'), ('PNG', 'image/png'),
                                      ('WEBP', 'image/webp'), ('GIF', 'image/gif')])
def test_valid_admission_preserves_exact_bytes_and_cleans_worker(fmt, mime, worker_root):
    raw = _image(fmt)
    accepted = technical.validate_media_bytes(raw, declared_mime_type=mime)
    assert accepted.raw_media_bytes == raw
    assert accepted.result['outcome'] == 'ACCEPT'
    assert accepted.result['width_pixels'] == 3
    assert list(worker_root.iterdir()) == []


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP', 'GIF'])
def test_truncated_rejected(fmt, worker_root):
    with pytest.raises(technical.TechnicalMediaValidationError) as exc:
        technical.validate_media_bytes(_image(fmt)[:-2])
    assert REASON_MALFORMED_MEDIA in exc.value.result['reason_codes']
    assert list(worker_root.iterdir()) == []


def test_corrupt_stream_rejected_inside_worker(worker_root):
    # A complete GIF container passes the header gate but cannot be decoded.
    raw = b'GIF89a' + b'\x03\x00\x02\x00' + b'\x00' * 10 + b';'
    with pytest.raises(technical._MalformedImageError):
        technical._run_isolated_decoder(raw, 'image/gif', timeout_seconds=2, memory_limit=268435456)
    with pytest.raises(technical.TechnicalMediaValidationError) as exc:
        technical.validate_media_bytes(raw)
    assert REASON_MALFORMED_MEDIA in exc.value.result['reason_codes']
    assert list(worker_root.iterdir()) == []


def test_mime_mismatch_skips_worker(monkeypatch, worker_root):
    monkeypatch.setattr(technical, '_run_isolated_decoder', lambda *a, **k: pytest.fail('worker reached'))
    with pytest.raises(technical.TechnicalMediaValidationError) as exc:
        technical.validate_media_bytes(_image(), declared_mime_type='image/jpeg')
    assert exc.value.result['reason_codes'] == ['DECLARED_MIME_MISMATCH']


@pytest.mark.parametrize('worker,cause', [(_permission_worker, PermissionError),
                                        (_crash_worker, BrokenProcessPool)])
def test_real_worker_local_failures_are_not_media_verdicts(worker, cause, monkeypatch, worker_root):
    monkeypatch.setattr(technical, '_decode_image_worker', worker)
    with pytest.raises(technical.MediaValidationUnavailable) as exc:
        technical.validate_media_bytes(_image())
    assert isinstance(exc.value.__cause__, cause)
    assert not isinstance(exc.value, ValueError)
    assert list(worker_root.iterdir()) == []


def test_real_worker_timeout_is_local_and_cleanup_waits_for_exit(monkeypatch, worker_root):
    monkeypatch.setattr(technical, '_decode_image_worker', _timeout_worker)
    with pytest.raises(technical.TechnicalMediaValidationError) as exc:
        technical.validate_media_bytes(_image(), local_defense_overrides={'structural_decode_wall_time_seconds': 1})
    assert exc.value.result['reason_codes'] == [REASON_RESOURCE_LIMIT_TERMINATED]
    assert exc.value.result['local_resource_defense_failure'] is True
    assert list(worker_root.iterdir()) == []


def test_temp_setup_failure_is_local(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(errno.EACCES, 'temp setup denied')
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', denied)
    with pytest.raises(technical.MediaValidationUnavailable) as exc:
        technical.validate_media_bytes(_image())
    assert isinstance(exc.value.__cause__, PermissionError)


@pytest.mark.parametrize('error_number', [errno.EACCES, errno.EIO])
def test_os_errors_during_decode_are_not_wrapped_as_malformed(error_number, monkeypatch, worker_root):
    original_executor = technical.ProcessPoolExecutor
    class ErrorExecutor(original_executor):
        def submit(self, fn, *args):
            return super().submit(_decode_os_error_worker, error_number, *args)
    monkeypatch.setattr(technical, 'ProcessPoolExecutor', ErrorExecutor)
    with pytest.raises(technical.MediaValidationUnavailable) as exc:
        technical.validate_media_bytes(_image())
    assert isinstance(exc.value.__cause__, OSError)
    assert exc.value.__cause__.errno == error_number
    assert list(worker_root.iterdir()) == []


def test_cleanup_failure_withholds_acceptance(monkeypatch, worker_root):
    original_directory = tempfile.TemporaryDirectory
    class CleanupFailure(original_directory):
        def __exit__(self, *args):
            super().__exit__(*args)
            raise PermissionError(errno.EACCES, 'injected cleanup failure')
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', CleanupFailure)
    with pytest.raises(technical.MediaValidationUnavailable) as exc:
        technical.validate_media_bytes(_image())
    assert isinstance(exc.value.__cause__, PermissionError)
    assert list(worker_root.iterdir()) == []


def test_process_and_empty_directory_isolation(monkeypatch, worker_root):
    # Keep the original callable available in the child; only replace submit.
    original_executor = technical.ProcessPoolExecutor
    class ObservedExecutor(original_executor):
        def submit(self, fn, *args):
            return super().submit(_observing_worker, *args)
    monkeypatch.setattr(technical, 'ProcessPoolExecutor', ObservedExecutor)
    before = Path.cwd()
    result = technical._run_isolated_decoder(_image(), 'image/png', timeout_seconds=2, memory_limit=268435456)
    assert result['pid'] != os.getpid()
    assert result['entries'] == []
    assert Path(result['directory']).parent == worker_root
    assert not Path(result['directory']).exists()
    assert Path.cwd() == before


def test_public_upload_local_failure_is_503_and_persists_nothing(blockchain, wallets, monkeypatch):
    from fastapi.testclient import TestClient
    import api
    api.limiter.reset()
    api.blockchain = blockchain
    def denied(*a, **k):
        raise PermissionError(errno.EACCES, 'private internal path')
    monkeypatch.setattr(technical, '_run_isolated_decoder', denied)
    response = TestClient(api.app).post('/content/upload',
        data={'submitted_by': wallets['owner'].public_key},
        files={'file': ('valid.png', _image(), 'image/png')})
    assert response.status_code == 503
    assert response.json()['code'] == 'MEDIA_VALIDATION_UNAVAILABLE'
    assert 'private internal path' not in response.text
    assert blockchain.content_objects == []
    assert blockchain.submissions == []
    assert blockchain.originality_evidence == []
