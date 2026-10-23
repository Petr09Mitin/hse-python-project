from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest

from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from tests.helpers.messaging.scripted_dispatcher import ScriptedDispatcher
from tests.helpers.messaging.scripted_receiver import ScriptedReceiver


def messages(count):
    return [IncomingMessage(1, 1, str(index), "/report") for index in range(count)]


def runner_for(receiver, dispatcher, **kwargs):
    from receipt_bot.bootstrap.application_runner import ApplicationRunner

    return ApplicationRunner(receiver, dispatcher, retry_delay=0.01, shutdown_timeout=0.3, **kwargs)


def wait_until(predicate, timeout=2):
    deadline = monotonic() + timeout
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("Событие не наступило")
        sleep(0.005)


def test_none_does_not_end_intake_and_prepare_keeps_ingress_order():
    receiver = ScriptedReceiver([None, *messages(3)])
    dispatcher = ScriptedDispatcher()
    runner = runner_for(receiver, dispatcher)
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        wait_until(lambda: len(receiver.acknowledged) == 3)
        runner.stop()
        result.result(timeout=2)
    assert dispatcher.prepared == ["0", "1", "2"]
    assert set(receiver.acknowledged) == {"0", "1", "2"}
    assert receiver.stopped.is_set()


def test_capacity_is_reserved_before_receive_and_workers_are_bounded():
    release = Event()
    started = []

    def dispatch(message):
        started.append(message.event_id)
        assert release.wait(2)

    receiver = ScriptedReceiver(messages(8))
    dispatcher = ScriptedDispatcher(dispatch)
    runner = runner_for(receiver, dispatcher, workers=2, capacity=3)
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        try:
            wait_until(lambda: len(dispatcher.prepared) == 3)
            sleep(0.03)
            assert receiver.received == ["0", "1", "2"]
            assert len(started) == 2
            runner.stop()
        finally:
            release.set()
        result.result(timeout=2)
    assert set(receiver.acknowledged) == {"0", "1", "2"}


def test_storage_prepare_failure_pauses_receive_and_keeps_same_event_first():
    restored = Event()
    failed = Event()

    def prepare(message):
        if message.event_id == "0" and not restored.is_set():
            failed.set()
            raise StorageError("storage_unavailable")

    receiver = ScriptedReceiver(messages(2))
    dispatcher = ScriptedDispatcher(prepare_hook=prepare)
    runner = runner_for(receiver, dispatcher)
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        assert failed.wait(2)
        try:
            sleep(0.03)
            assert receiver.received == ["0"]
            assert receiver.acknowledged == []
        finally:
            restored.set()
        wait_until(lambda: len(receiver.acknowledged) == 2)
        runner.stop()
        result.result(timeout=2)
    assert dispatcher.prepared[-2:] == ["0", "1"]


def test_storage_dispatch_is_retried_without_ack_and_new_intake_pauses():
    restored = Event()
    failed = Event()

    def dispatch(message):
        if not restored.is_set():
            failed.set()
            raise StorageError("storage_unavailable")

    receiver = ScriptedReceiver(messages(3))
    dispatcher = ScriptedDispatcher(dispatch)
    runner = runner_for(receiver, dispatcher, workers=1, capacity=1)
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        assert failed.wait(2)
        try:
            sleep(0.03)
            assert receiver.received == ["0"]
            assert receiver.acknowledged == []
        finally:
            restored.set()
        wait_until(lambda: len(receiver.acknowledged) == 3)
        runner.stop()
        result.result(timeout=2)
    assert dispatcher.attempts["0"] > 1
    assert dispatcher.prepared == ["0", "1", "2"]


def test_unexpected_future_error_is_raised_and_never_acknowledged():
    def dispatch(message):
        raise LookupError("private-receipt-text")

    receiver = ScriptedReceiver(messages(1))
    runner = runner_for(receiver, ScriptedDispatcher(dispatch))
    with pytest.raises(LookupError, match="private-receipt-text"):
        runner.run()
    assert receiver.acknowledged == []
    assert receiver.stopped.is_set()


def test_stop_while_receive_returns_does_not_dispatch_or_ack_new_message():
    receiver = ScriptedReceiver(messages(1))
    dispatcher = ScriptedDispatcher()
    runner = runner_for(receiver, dispatcher)
    receiver.receive_hook = runner.stop
    runner.run()
    assert dispatcher.prepared == []
    assert receiver.acknowledged == []


def test_shutdown_cancels_queued_work_without_ack_or_closing_active_resources():
    from receipt_bot.bootstrap.application_runner import ApplicationRunner

    release = Event()
    started = Event()
    closed = []

    def dispatch(message):
        started.set()
        release.wait(2)

    receiver = ScriptedReceiver(messages(2))
    dispatcher = ScriptedDispatcher(dispatch)
    runner = ApplicationRunner(
        receiver, dispatcher, workers=1, capacity=2, shutdown_timeout=0.03, close=lambda: closed.append(True)
    )
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        try:
            assert started.wait(2)
            wait_until(lambda: len(dispatcher.prepared) == 2)
            runner.stop()
            with pytest.raises(TimeoutError):
                result.result(timeout=2)
            assert receiver.acknowledged == []
            assert closed == []
        finally:
            release.set()
    assert dispatcher.dispatched == ["0"]


@pytest.mark.parametrize(
    "status,code", [("permanent_failure", "telegram_403"), ("exhausted", "telegram_network_error")]
)
def test_terminal_delivery_failure_is_logged_and_acknowledged(status, code, caplog):
    from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome
    from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
    from tests.helpers.messaging.memory_sender import MemorySender

    sender = MemorySender()
    sender.outcome = DeliveryOutcome(status, code, 3)
    dispatcher = MessageDispatcher(None, None, None, sender)
    receiver = ScriptedReceiver([IncomingMessage(1, 1, "event", "/unknown")])
    runner = runner_for(receiver, dispatcher)
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        try:
            wait_until(lambda: receiver.acknowledged == ["event"])
        finally:
            runner.stop()
        result.result(timeout=2)
    assert "delivery_" + status in caplog.text
    assert code in caplog.text


def test_storage_failure_during_receive_holds_next_prepare_until_recovery():
    receiving_second = Event()
    failed = Event()
    restored = Event()

    def dispatch(message):
        if message.event_id == "0" and not restored.is_set():
            assert receiving_second.wait(2)
            failed.set()
            raise StorageError("storage_unavailable")

    receiver = ScriptedReceiver(messages(2))
    dispatcher = ScriptedDispatcher(dispatch)
    runner = runner_for(receiver, dispatcher, workers=1, capacity=2)

    def receive_hook():
        if receiver.received == ["0"]:
            receiving_second.set()
            assert failed.wait(2)
            wait_until(lambda: any(future.done() for future in runner.futures))

    receiver.receive_hook = receive_hook
    with ThreadPoolExecutor(1) as thread:
        result = thread.submit(runner.run)
        try:
            assert failed.wait(2)
            sleep(0.03)
            observed_prepared = list(dispatcher.prepared)
        finally:
            restored.set()
        wait_until(lambda: len(receiver.acknowledged) == 2)
        runner.stop()
        result.result(timeout=2)
    assert observed_prepared == ["0"]
