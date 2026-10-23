import os

import pytest

from receipt_bot.bootstrap.application_settings import ApplicationSettings


def test_real_dependencies_are_ready_without_contacting_telegram():
    from receipt_bot.adapters.persistence.schema import prepare_schema
    from receipt_bot.bootstrap.readiness import check_dependencies

    names = ("TEST_POSTGRES_DSN", "TEST_QWEN_URL", "TEST_MODEL_DIR")
    if not all(os.environ.get(name) for name in names):
        pytest.skip("Нужны PostgreSQL, Qwen и подготовленные модели")
    settings = ApplicationSettings(
        {
            "TELEGRAM_API_KEY": "123:dummy-test-token",
            "POSTGRES_DSN": os.environ["TEST_POSTGRES_DSN"],
            "QWEN_URL": os.environ["TEST_QWEN_URL"],
            "MODEL_DIR": os.environ["TEST_MODEL_DIR"],
        }
    )
    prepare_schema(settings.postgres_dsn)
    check_dependencies(settings)
