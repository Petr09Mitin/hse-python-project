from types import SimpleNamespace

import pytest
from telebot import apihelper

from receipt_bot.adapters.telegram.telegram_message_sender import TelegramMessageSender
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage


def test_sender_respects_server_retry_after_before_next_attempt(monkeypatch):
    clock = [0]
    calls = []

    def send_message(*args, **kwargs):
        calls.append(clock[0])
        if clock[0] < 10:
            raise apihelper.ApiTelegramException(
                "sendMessage",
                SimpleNamespace(),
                {"error_code": 429, "description": "retry later", "parameters": {"retry_after": 10}},
            )

    monkeypatch.setattr(
        "receipt_bot.adapters.telegram.telegram_message_sender.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    sender = TelegramMessageSender(SimpleNamespace(send_message=send_message))
    outcome = sender.send(OutgoingMessage(1, "Готово"))
    assert outcome.status == "delivered" and outcome.attempts == 2
    assert calls == [0, 10]


@pytest.mark.parametrize("retry_after", [float("inf"), float("nan"), -1, "10", True, None])
def test_invalid_server_retry_delay_uses_finite_local_delay(monkeypatch, retry_after):
    clock = [0]
    calls = []

    def send_message(*args, **kwargs):
        calls.append(clock[0])
        raise apihelper.ApiTelegramException(
            "sendMessage",
            SimpleNamespace(),
            {"error_code": 429, "description": "retry later", "parameters": {"retry_after": retry_after}},
        )

    monkeypatch.setattr(
        "receipt_bot.adapters.telegram.telegram_message_sender.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    sender = TelegramMessageSender(SimpleNamespace(send_message=send_message), retry_delay=0.25)
    outcome = sender.send(OutgoingMessage(1, "Готово"))
    assert outcome.status == "exhausted" and outcome.attempts == 3
    assert calls == [0, 0.25, 0.5]
