import pytest

from receipt_bot.bootstrap.application_settings import ApplicationSettings


def test_composition_uses_bounded_sdk_and_pipeline_settings_without_network(tmp_path):
    from receipt_bot.bootstrap.build_application import build_application

    for name in ("PP-OCRv3_mobile_det", "cyrillic_PP-OCRv3_mobile_rec"):
        (tmp_path / name).mkdir()
    settings = ApplicationSettings(
        {
            "TELEGRAM_API_KEY": "123:dummy-test-token",
            "POSTGRES_DSN": "postgresql://receipt:password@postgres/receipt",
            "MODEL_DIR": str(tmp_path),
            "CAPACITY": "7",
            "WORKERS": "2",
            "MAX_ATTACHMENTS": "3",
            "MAX_FILE_BYTES": "12345",
            "MAX_PDF_PAGES": "9",
            "SEND_TIMEOUT": "4",
            "QWEN_TIMEOUT": "11",
        }
    )
    runner = build_application(settings)
    try:
        assert (runner.workers, runner.capacity, runner.receiver.max_buffered_updates) == (2, 7, 7)
        assert runner.receiver.bot.threaded is False
        assert runner.dispatcher.sender.timeout == 4
        processor = runner.dispatcher.receipts
        assert (processor.max_attachments, processor.max_file_bytes) == (3, 12345)
        assert processor.downloader.max_bytes == 12345
        assert processor.extractor.max_pages == processor.extractor.pdf_reader.max_pages == 9
        assert processor.classifier.client.timeout == 11
        assert processor.classifier.client.max_tokens == 2048
        assert processor.classifier.client.sdk.max_retries == 0
    finally:
        runner.close()
    assert processor.classifier.client.sdk.is_closed()


def test_api_composition_uses_one_authenticated_client_for_ocr_and_llm_without_local_models(tmp_path):
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner
    from receipt_bot.bootstrap.build_application import build_application

    settings = ApplicationSettings(
        {
            "TELEGRAM_API_KEY": "123:dummy-test-token",
            "POSTGRES_DSN": "postgresql://receipt:password@postgres/receipt",
            "MODEL_DIR": str(tmp_path),
            "OPENAI_BASE_URL": "https://models.example/api/v1",
            "OPENAI_MODEL": "vision-model",
            "OPENAI_API_KEY": "dummy-api-secret",
        }
    )

    runner = build_application(settings)
    try:
        processor = runner.dispatcher.receipts
        client = processor.classifier.client
        assert isinstance(processor.extractor.ocr_runner, QwenOCRRunner)
        assert processor.extractor.ocr_runner.client is client
        assert processor.structurer.client is processor.item_classificator.client is client
        assert client.model == "vision-model"
        assert client.max_tokens == 8192
        assert str(client.sdk.base_url) == "https://models.example/api/v1/"
        assert client.sdk.api_key == "dummy-api-secret"
    finally:
        runner.close()
    assert client.sdk.is_closed()


def test_failed_ocr_composition_closes_created_model_client(monkeypatch):
    import receipt_bot.bootstrap.build_application as composition
    from receipt_bot.adapters.recognition.qwen_client import QwenClient

    clients = []

    def create_client(*args, **kwargs):
        client = QwenClient(*args, **kwargs)
        clients.append(client)
        return client

    def fail_ocr(client):
        raise ValueError("ocr_configuration_invalid")

    monkeypatch.setattr(composition, "QwenClient", create_client)
    monkeypatch.setattr(composition, "QwenOCRRunner", fail_ocr, raising=False)
    settings = ApplicationSettings(
        {
            "TELEGRAM_API_KEY": "123:dummy-test-token",
            "POSTGRES_DSN": "postgresql://receipt:password@postgres/receipt",
            "OPENAI_BASE_URL": "https://models.example/v1",
            "OPENAI_MODEL": "vision-model",
            "OPENAI_API_KEY": "dummy-api-secret",
        }
    )

    with pytest.raises(ValueError, match="ocr_configuration_invalid"):
        composition.build_application(settings)
    assert len(clients) == 1
    assert clients[0].sdk.is_closed()
