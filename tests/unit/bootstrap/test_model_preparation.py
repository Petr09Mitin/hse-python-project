import hashlib

import pytest

from tests.helpers.http.http_server import scripted_server


def test_model_download_retries_temporary_error_and_uses_verified_cache(tmp_path):
    from receipt_bot.bootstrap.prepare_models import download_model

    content = b"known-model-content"
    destination = tmp_path / "models" / "model.bin"
    checksum = hashlib.sha256(content).hexdigest()
    with scripted_server([(503, b"unavailable"), (200, content)]) as (server, url):
        download_model(url + "/model", destination, checksum, timeout=2, retry_delay=0)
        assert destination.read_bytes() == content
        assert len(server.requests) == 2
        download_model(url + "/model", destination, checksum, timeout=2, retry_delay=0)
        assert len(server.requests) == 2
    assert list(destination.parent.iterdir()) == [destination]


def test_invalid_download_keeps_previous_file_and_removes_partial(tmp_path):
    from receipt_bot.bootstrap.prepare_models import download_model

    destination = tmp_path / "model.bin"
    destination.write_bytes(b"old-model")
    with scripted_server([(200, b"broken")] * 3) as (server, url):
        with pytest.raises(RuntimeError, match="model_download_failed"):
            download_model(url, destination, "0" * 64, timeout=2, retry_delay=0)
        assert len(server.requests) == 3
    assert destination.read_bytes() == b"old-model"
    assert list(tmp_path.iterdir()) == [destination]


def test_permanent_http_failure_is_not_retried(tmp_path):
    from receipt_bot.bootstrap.prepare_models import download_model

    with scripted_server([(404, b"not found")]) as (server, url):
        with pytest.raises(RuntimeError, match="model_download_failed"):
            download_model(url, tmp_path / "missing", "0" * 64, timeout=2, retry_delay=0)
        assert len(server.requests) == 1
