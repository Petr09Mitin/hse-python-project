import os
import signal
import subprocess
from time import monotonic


def supervise(command: list[str], shutdown_timeout: float) -> int:
    """Запускает приложение с дочерними процессами в отдельной группе."""
    deadline = None
    requested_signal = None

    def request_stop(signum, frame):
        nonlocal deadline, requested_signal
        if deadline is None:
            deadline = monotonic() + shutdown_timeout
            requested_signal = signum

    previous = {signum: signal.signal(signum, request_stop) for signum in (signal.SIGTERM, signal.SIGINT)}
    child = None
    try:
        child = subprocess.Popen(command, start_new_session=True)
        forwarded = False
        while child.poll() is None:
            if deadline is not None:
                if not forwarded:
                    child.send_signal(requested_signal)
                    forwarded = True
                if monotonic() >= deadline:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    return 124
            try:
                child.wait(timeout=0.02)
            except subprocess.TimeoutExpired:
                continue
        return child.returncode if child.returncode >= 0 else 128 - child.returncode
    finally:
        if child is not None:
            # Удаляет дочерние процессы и после аварийного завершения приложения.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
