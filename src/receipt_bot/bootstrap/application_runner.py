import logging
import math
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
from receipt_bot.application.messaging.message_receiver import MessageReceiver

logger = logging.getLogger(__name__)


class ApplicationRunner:
    """Управляет обработчиками и ограничивает число принятых запросов."""

    def __init__(
        self,
        receiver: MessageReceiver,
        dispatcher: MessageDispatcher,
        workers: int = 4,
        capacity: int = 16,
        shutdown_timeout: float = 30,
        retry_delay: float = 1,
        close: Callable[[], None] | None = None,
        initialize_worker: Callable[[], None] | None = None,
    ):
        if type(workers) is not int or type(capacity) is not int or not 1 <= workers <= capacity <= 100:
            raise ValueError("Нужны 1 <= workers <= capacity <= 100")
        for timeout in (shutdown_timeout, retry_delay):
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("Сроки должны быть конечными и положительными")
        self.receiver = receiver
        self.dispatcher = dispatcher
        self.workers = workers
        self.capacity = capacity
        self.shutdown_timeout = shutdown_timeout
        self.retry_delay = retry_delay
        self.close = close
        self.initialize_worker = initialize_worker
        self.stopped = Event()
        self.deadline = None
        self.futures = {}
        self.retries = deque()
        self.retrying = set()
        self.errors = []

    def stop(self) -> None:
        if self.deadline is None:
            self.deadline = monotonic() + self.shutdown_timeout
        self.stopped.set()

    def run(self) -> None:
        pool = ThreadPoolExecutor(
            max_workers=self.workers, thread_name_prefix="receipt", initializer=self.initialize_worker
        )
        pending_message = None
        try:
            while not self.stopped.is_set():
                self._collect()
                if self.stopped.is_set():
                    break
                if self.retries or self.retrying:
                    if self.retries and not self.retrying:
                        if self.stopped.wait(self.retry_delay):
                            break
                        prepared = self.retries.popleft()
                        future = pool.submit(self.dispatcher.dispatch, prepared)
                        self.futures[future] = prepared
                        self.retrying.add(future)
                    else:
                        self.stopped.wait(0.005)
                    continue
                if pending_message is None:
                    # Резервируем место до приёма запроса и держим его до передачи работнику.
                    if len(self.futures) >= self.capacity:
                        self.stopped.wait(0.005)
                        continue
                    pending_message = self.receiver.receive()
                    if self.stopped.is_set():
                        break
                    continue
                prepared = self._prepare(pending_message)
                pending_message = None
                if prepared is not None and not self.stopped.is_set():
                    self.futures[pool.submit(self.dispatcher.dispatch, prepared)] = prepared
        finally:
            self.stop()
            self.receiver.stop()
            while self.futures and monotonic() < self.deadline:
                self._collect()
                if self.futures:
                    sleep(0.005)
            self._collect()
            for future in self.futures:
                future.cancel()
                future.add_done_callback(self._observe_unfinished)
            pool.shutdown(wait=not self.futures, cancel_futures=True)
            if not self.futures and self.close is not None:
                self.close()
        if self.errors:
            raise self.errors[0]
        if self.futures:
            raise TimeoutError("application_shutdown_incomplete")

    def _prepare(self, message):
        while not self.stopped.is_set():
            try:
                return self.dispatcher.prepare(message)
            except StorageError:
                logger.warning("storage_prepare_retry")
                self._collect()
                self.stopped.wait(self.retry_delay)
        return None

    def _collect(self) -> None:
        for future, prepared in list(self.futures.items()):
            if not future.done():
                continue
            del self.futures[future]
            self.retrying.discard(future)
            if future.cancelled():
                continue
            error = future.exception()
            if isinstance(error, StorageError):
                logger.warning("storage_dispatch_retry")
                if not self.stopped.is_set():
                    self.retries.append(prepared)
            elif error is not None:
                logger.error("dispatch_failed")
                self.errors.append(error)
                self.stop()
            else:
                for outcome in future.result():
                    if outcome.status != "delivered":
                        logger.warning(f"delivery_{outcome.status} {outcome.error_code}")
                self.receiver.acknowledge(prepared.message)

    def _observe_unfinished(self, future: Future) -> None:
        if not future.cancelled() and future.exception() is not None:
            logger.error("unfinished_dispatch_failed")
