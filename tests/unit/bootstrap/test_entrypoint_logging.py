import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module,code,changes",
    [
        ("prepare_models", "models_failed", {}),
        ("readiness", "dependencies_unavailable", {}),
        ("app_process", "application_failed", {"SHUTDOWN_TIMEOUT": "invalid"}),
    ],
)
def test_real_module_entrypoint_logs_safe_failure_code(module, code, changes):
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
        "TELEGRAM_API_KEY": "123:dummy-private-token",
        "POSTGRES_DSN": "postgresql://private:password@private-db.invalid/receipts",
        "QWEN_URL": "http://private-qwen.invalid/v1",
        "MODEL_DIR": "/dev/null",
    }
    environment.update(changes)
    result = subprocess.run(
        [sys.executable, "-m", f"receipt_bot.bootstrap.{module}"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == f"ERROR {code}"
    assert result.stdout == ""
    assert "private" not in result.stderr
    assert "http" not in result.stderr
