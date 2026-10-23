from collections import Counter

from receipt_bot.application.messaging.prepared_message import PreparedMessage


class ScriptedDispatcher:
    def __init__(self, dispatch_hook=None, prepare_hook=None):
        self.dispatch_hook = dispatch_hook
        self.prepare_hook = prepare_hook
        self.prepared = []
        self.dispatched = []
        self.attempts = Counter()

    def prepare(self, message):
        self.prepared.append(message.event_id)
        if self.prepare_hook is not None:
            self.prepare_hook(message)
        return PreparedMessage(message, "help")

    def dispatch(self, prepared):
        message = prepared.message
        self.attempts[message.event_id] += 1
        if self.dispatch_hook is not None:
            self.dispatch_hook(message)
        self.dispatched.append(message.event_id)
        return ()
