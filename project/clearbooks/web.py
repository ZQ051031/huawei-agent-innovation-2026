import base64
import binascii
import json
import logging
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import agent
from .extract import MAX_BYTES

STATIC = Path(__file__).resolve().parent
ASSETS = {"/": ("index.html", "text/html"), "/ui.js": ("ui.js", "text/javascript"),
          "/ui.css": ("ui.css", "text/css")}
MAX_REQUEST = ((MAX_BYTES + 2) // 3) * 4 + 8000


def create_server(ledger, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content_type, data):
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def json(self, status, result):
            self.send(status, "application/json", json.dumps(result, ensure_ascii=False).encode())

        def local(self):
            port = self.server.server_port
            hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
            if port == 80:
                hosts |= {"localhost", "127.0.0.1"}
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            if host not in hosts or origin not in {None, f"http://{host}"} or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.json(403, {"error": "Use this app from its localhost address."})
                return False
            return True

        def do_GET(self):
            if not self.local():
                return
            path = urlsplit(self.path)
            try:
                if path.path in ASSETS:
                    file, kind = ASSETS[path.path]
                    self.send(200, kind, (STATIC / file).read_bytes())
                elif path.path == "/api/summary":
                    months = ledger.months()
                    month = parse_qs(path.query).get("month", [months[0] if months else date.today().isoformat()[:7]])[0]
                    self.json(200, {"months": months, **ledger.summary(month)})
                else:
                    self.json(404, {"error": "Not found."})
            except ValueError as exc:
                self.json(400, {"error": str(exc)})
            except Exception:
                logging.exception("Local request failed")
                self.json(500, {"error": "Local request failed; see server log."})

        def read_body(self):
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected application/json.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST:
                raise ValueError("Request is empty or exceeds the local upload limit.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not all(isinstance(v, str) for v in body.values()):
                raise ValueError("Expected a JSON object containing string values.")
            return body

        def do_POST(self):
            if not self.local():
                return
            try:
                body = self.read_body()
                month = body.get("month", "2026-11")
                lang = body.get("lang", "en")
                if self.path == "/api/import":
                    if "data" in body:
                        data = base64.b64decode(body["data"], validate=True)
                    else:
                        data = body.get("text", "").encode()
                    result = ledger.ingest(body.get("name", "pasted.txt"), data)
                elif self.path == "/api/demo":
                    result = {"imports": ledger.demo()}
                elif self.path == "/api/budget":
                    ledger.set_budget(month, body.get("category", ""), body.get("currency", ""), body.get("amount", ""))
                    result = {"saved": True}
                elif self.path == "/api/ask":
                    result = agent.ask(ledger, body.get("question", ""), month, lang)
                elif self.path == "/api/report":
                    result = agent.report(ledger, month, lang)
                else:
                    self.json(404, {"error": "Not found."})
                    return
                self.json(200, result)
            except (ValueError, binascii.Error) as exc:
                self.json(400, {"error": str(exc)})
            except Exception:
                logging.exception("Local request failed")
                self.json(500, {"error": "Local request failed; see server log."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
