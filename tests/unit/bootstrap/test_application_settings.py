import pytest


def settings_for(**changes):
    from receipt_bot.bootstrap.application_settings import ApplicationSettings

    environment = {"TELEGRAM_API_KEY": "123:dummy-secret", "POSTGRES_DSN": "postgresql://user:pass@db/receipts"}
    environment.update(changes)
    return ApplicationSettings(environment)


def test_settings_default_limits_and_v1_endpoint():
    settings = settings_for(QWEN_URL="http://llm:8080/v1/")
    assert (settings.workers, settings.capacity) == (4, 16)
    assert (settings.max_attachments, settings.max_file_bytes, settings.max_pdf_pages) == (8, 10485760, 20)
    assert settings.qwen_url == "http://llm:8080/v1"
    assert (settings.use_api_model, settings.qwen_model, settings.qwen_api_key) == (False, "qwen3-1.7b", "local")
    assert "dummy-secret" not in repr(settings)


def test_api_settings_override_local_model_and_credentials():
    settings = settings_for(
        OPENAI_BASE_URL=" https://models.example/api/v1/ ",
        OPENAI_MODEL=" vision-model ",
        OPENAI_API_KEY=" dummy-api-secret ",
        QWEN_URL="http://unused:8080/v1",
    )

    assert settings.use_api_model is True
    assert settings.qwen_url == "https://models.example/api/v1"
    assert settings.qwen_model == "vision-model"
    assert settings.qwen_api_key == "dummy-api-secret"
    assert "dummy-api-secret" not in repr(settings)


@pytest.mark.parametrize("key", ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_api_mode_requires_complete_nonblank_configuration(key, value):
    environment = {
        "OPENAI_BASE_URL": "https://models.example/v1",
        "OPENAI_MODEL": "vision-model",
        "OPENAI_API_KEY": "dummy-api-secret",
    }
    if value is None:
        del environment[key]
    else:
        environment[key] = value

    with pytest.raises(ValueError, match=key) as caught:
        settings_for(**environment)
    assert "dummy-api-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "models.example/v1",
        "ftp://models.example/v1",
        "https:///v1",
        "https://models.example/v1?key=dummy-api-secret",
        "https://models.example/v1#fragment",
        "https://user:dummy-api-secret@models.example/v1",
        "https://models.example:bad/v1",
        "https://models.example:70000/v1",
        "https://models.example:0/v1",
        "https://model host/v1",
        "https://[invalid/v1",
        "https://models.example/\nv1",
    ],
)
def test_api_settings_reject_invalid_urls_without_disclosing_credentials(url):
    with pytest.raises(ValueError, match="OPENAI_BASE_URL") as caught:
        settings_for(OPENAI_BASE_URL=url, OPENAI_MODEL="vision-model", OPENAI_API_KEY="dummy-api-secret")
    assert "dummy-api-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"TELEGRAM_API_KEY": ""},
        {"POSTGRES_DSN": ""},
        {"WORKERS": "0"},
        {"CAPACITY": "101"},
        {"WORKERS": "5", "CAPACITY": "4"},
        {"QWEN_URL": "http://llm:8080"},
        {"OCR_TIMEOUT": "nan"},
        {"SHUTDOWN_TIMEOUT": "inf"},
        {"DOWNLOAD_TIMEOUT": "0"},
        {"MAX_FILE_BYTES": "-1"},
    ],
)
def test_settings_reject_unsafe_values_without_echoing_secrets(changes):
    with pytest.raises(ValueError) as caught:
        settings_for(**changes)
    assert "dummy-secret" not in str(caught.value)
    assert "user:pass" not in str(caught.value)


def test_default_shutdown_deadline_fits_compose_grace_period():
    assert settings_for().shutdown_timeout == 30


@pytest.mark.parametrize("timeout", ["30.0001", "60"])
def test_shutdown_deadline_cannot_exceed_supported_maximum(timeout):
    with pytest.raises(ValueError, match="SHUTDOWN_TIMEOUT"):
        settings_for(SHUTDOWN_TIMEOUT=timeout)
