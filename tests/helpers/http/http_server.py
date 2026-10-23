from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from threading import Thread

from tests.helpers.http.scripted_http_handler import ScriptedHTTPHandler


@contextmanager
def scripted_server(responses):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedHTTPHandler)
    server.requests = []
    server.responses = list(responses)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
