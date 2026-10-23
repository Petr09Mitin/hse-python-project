import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from openai import OpenAI

from receipt_bot.bootstrap.application_settings import ApplicationSettings


@pytest.fixture
def readiness_dependencies(monkeypatch):
    from receipt_bot.bootstrap import readiness

    state = SimpleNamespace(
        database_checked=False, schema_ready=True, model_ids=["vision-model"], requests=[], clients=[]
    )

    @contextmanager
    def database_connection(*args):
        state.database_checked = True
        row = {"receipts": "receipts", "events": "report_events" if state.schema_ready else None}
        yield SimpleNamespace(execute=lambda statement: SimpleNamespace(fetchone=lambda: row))

    def respond(request):
        state.requests.append(request)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": model, "object": "model", "created": 0, "owned_by": "test"} for model in state.model_ids
                ],
            },
        )

    def create_client(**kwargs):
        client = OpenAI(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))
        state.clients.append(client)
        return client

    monkeypatch.setattr(readiness, "connection", database_connection)
    monkeypatch.setattr(readiness, "OpenAI", create_client)
    return state


def api_settings(model_dir):
    return ApplicationSettings(
        {
            "TELEGRAM_API_KEY": "123:dummy",
            "POSTGRES_DSN": "unreachable-secret-dsn",
            "MODEL_DIR": str(model_dir),
            "OPENAI_BASE_URL": "https://models.example/api/v1",
            "OPENAI_MODEL": "vision-model",
            "OPENAI_API_KEY": "dummy-api-secret",
        }
    )


def test_api_readiness_checks_database_and_authenticated_model_without_local_files(tmp_path, readiness_dependencies):
    from receipt_bot.bootstrap.readiness import check_dependencies

    check_dependencies(api_settings(tmp_path))

    assert readiness_dependencies.database_checked
    assert len(readiness_dependencies.requests) == 1
    request = readiness_dependencies.requests[0]
    assert request.url == "https://models.example/api/v1/models"
    assert request.headers["authorization"] == "Bearer dummy-api-secret"
    assert readiness_dependencies.clients[0].is_closed()


def test_api_readiness_rejects_missing_selected_model_and_closes_client(tmp_path, readiness_dependencies):
    from receipt_bot.bootstrap.readiness import check_dependencies

    readiness_dependencies.model_ids = ["other-model"]

    with pytest.raises(RuntimeError, match="qwen_model_unavailable"):
        check_dependencies(api_settings(tmp_path))
    assert readiness_dependencies.clients[0].is_closed()


def test_api_readiness_still_requires_database_schema(tmp_path, readiness_dependencies):
    from receipt_bot.bootstrap.readiness import check_dependencies

    readiness_dependencies.schema_ready = False

    with pytest.raises(RuntimeError, match="schema_unavailable"):
        check_dependencies(api_settings(tmp_path))
    assert readiness_dependencies.requests == []


def test_missing_model_blocks_readiness_before_intake(tmp_path):
    from receipt_bot.bootstrap.readiness import check_dependencies

    settings = ApplicationSettings(
        {"TELEGRAM_API_KEY": "123:dummy", "POSTGRES_DSN": "unreachable-secret-dsn", "MODEL_DIR": str(tmp_path)}
    )
    with pytest.raises(RuntimeError, match="models_unavailable"):
        check_dependencies(settings)


def test_entrypoint_fails_safely_without_starting_telegram_when_settings_invalid(tmp_path):
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "receipt_bot"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "ERROR settings_invalid"
    assert result.stdout == ""
