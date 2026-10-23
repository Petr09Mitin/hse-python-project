import json
from http.server import BaseHTTPRequestHandler


class ScriptedHTTPHandler(BaseHTTPRequestHandler):
    """Локальный HTTP-контракт без настоящих ключей провайдеров."""

    def do_POST(self):
        self._respond()

    def do_GET(self):
        self._respond()

    def _respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.append((self.path, body, dict(self.headers)))
        response = self.server.responses.pop(0)
        status, payload = response[:2]
        content = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        for name, value in (response[2] if len(response) == 3 else {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return
