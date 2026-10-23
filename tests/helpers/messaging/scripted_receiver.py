from collections import deque
from threading import Event


class ScriptedReceiver:
    def __init__(self, messages=(), receive_hook=None):
        self.messages = deque(messages)
        self.receive_hook = receive_hook
        self.received = []
        self.acknowledged = []
        self.stopped = Event()
        self.idle = Event()

    def receive(self):
        if self.receive_hook is not None:
            self.receive_hook()
        if self.messages:
            message = self.messages.popleft()
            self.received.append(message.event_id if message is not None else None)
            return message
        self.idle.set()
        self.stopped.wait(0.005)
        return None

    def acknowledge(self, message):
        self.acknowledged.append(message.event_id)

    def stop(self):
        self.stopped.set()
