"""HTTP server mínimo para liveness/readiness."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("middleware.health")


class HealthState:
    def __init__(self) -> None:
        self._ready = threading.Event()

    def mark_ready(self) -> None:
        self._ready.set()

    def mark_not_ready(self) -> None:
        self._ready.clear()

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()


def _make_handler(state: HealthState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._respond(200, b"ok")
            elif self.path == "/ready":
                if state.is_ready:
                    self._respond(200, b"ready")
                else:
                    self._respond(503, b"not-ready")
            else:
                self._respond(404, b"not-found")

        def _respond(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Evita poluir stdout com access log do http.server
            return

    return Handler


def start_health_server(port: int, state: HealthState) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, name="health", daemon=True)
    thread.start()
    log.info("health server iniciado", extra={"status": "started"})
    return server
