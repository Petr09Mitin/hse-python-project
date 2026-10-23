import os
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep

import pytest


def test_supervisor_kills_stuck_app_and_native_descendant_within_deadline(tmp_path):
    from receipt_bot.bootstrap.supervisor import supervise

    assert callable(supervise)
    child = tmp_path / "stuck.py"
    pid_file = tmp_path / "pids"
    child.write_text(
        "import os, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *args: None)\n"
        "native = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()) + ' ' + str(native.pid))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    project_src = str(Path(__file__).resolve().parents[3] / "src")
    environment = dict(os.environ, PYTHONPATH=project_src)
    script = (
        "import sys; from receipt_bot.bootstrap.supervisor import supervise; "
        "sys.exit(supervise([sys.executable, sys.argv[1]], 0.2))"
    )
    process = subprocess.Popen([sys.executable, "-c", script, str(child)], env=environment)
    pids = []
    try:
        deadline = monotonic() + 3
        while not pid_file.exists():
            if monotonic() >= deadline:
                raise AssertionError("App не стартовал")
            sleep(0.01)
        pids = [int(value) for value in pid_file.read_text().split()]
        start = monotonic()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=3) == 124
        assert monotonic() - start < 2
        for pid in pids:
            deadline = monotonic() + 1
            while monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                status = Path(f"/proc/{pid}/stat")
                if sys.platform == "linux" and status.exists() and status.read_text().split()[2] == "Z":
                    break
                sleep(0.01)
            else:
                raise AssertionError("Процесс остался жив после deadline")
    finally:
        process.kill() if process.poll() is None else None
        process.wait()
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_supervisor_returns_app_exit_status():
    from receipt_bot.bootstrap.supervisor import supervise

    assert supervise([sys.executable, "-c", "raise SystemExit(7)"], 0.2) == 7


@pytest.mark.parametrize("code", ["print('safe')", "raise ValueError('private-token-and-text')"])
def test_app_process_does_not_echo_exception_payloads_in_logs(code, capsys):
    import logging

    from receipt_bot.bootstrap.safe_logging import configure_logging

    configure_logging()
    logging.getLogger("openai").error(code)
    logging.getLogger("telebot").error("https://api.telegram.org/bot123:secret")
    logging.getLogger("receipt_bot.bootstrap").error("application_failed")
    captured = capsys.readouterr()
    assert "application_failed" in captured.err
    assert "private-token" not in captured.err
    assert "api.telegram.org" not in captured.err
    assert "print" not in captured.err
