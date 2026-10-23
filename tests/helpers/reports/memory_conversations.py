from threading import Lock


class MemoryConversations:
    def __init__(self):
        self.states = {}
        self.results = {}
        self.lock = Lock()

    def transition(self, owner_id, chat_id, event_id, change):
        with self.lock:
            event_key = (owner_id, chat_id, event_id)
            if event_key in self.results:
                return self.results[event_key]
            key = (owner_id, chat_id)
            state, resolution = change(self.states.get(key))
            self.states[key] = state
            self.results[event_key] = resolution
            return resolution
