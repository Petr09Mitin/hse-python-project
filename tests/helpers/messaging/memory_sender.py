from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome


class MemorySender:
    def __init__(self):
        self.messages = []
        self.outcome = DeliveryOutcome("delivered")

    def send(self, outgoing):
        self.messages.append(outgoing)
        return self.outcome
