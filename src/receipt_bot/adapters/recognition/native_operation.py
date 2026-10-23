import multiprocessing
import os
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory

from receipt_bot.application.errors.file_processing_error import FileProcessingError


def _execute_native(operation, arguments: tuple, result_path: str) -> None:
    with open(os.devnull, "w") as output:
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
        try:
            result = (True, operation(*arguments))
        except FileProcessingError as error:
            result = (False, str(error))
        with open(result_path, "wb") as destination:
            pickle.dump(result, destination)


def run_native(operation, arguments: tuple, timeout: float):
    """Запускает тяжёлую операцию с ограничением времени и очисткой дочернего процесса."""
    with TemporaryDirectory(prefix="receipt-native-") as directory:
        result_path = str(Path(directory) / "result.pickle")
        process = multiprocessing.get_context("spawn").Process(
            target=_execute_native, args=(operation, arguments, result_path)
        )
        process.start()
        try:
            process.join(timeout)
            if process.is_alive():
                raise FileProcessingError("native_timeout")
            if process.exitcode != 0 or not Path(result_path).is_file():
                raise FileProcessingError("native_failed")
            with open(result_path, "rb") as source:
                successful, result = pickle.load(source)
            if not successful:
                raise FileProcessingError(result)
            return result
        finally:
            if process.is_alive():
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
            process.close()
