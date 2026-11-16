"""A tape recorder between OpenMinion and the model server.

Point OPENMINION at this proxy (port 8081) instead of llama-server (port 8080)
and it writes one line per request: how many bytes of system prompt were sent,
how many tools, and how big the whole payload was. Nothing is stored beyond
sizes and role names, so it is safe to keep the log in a proof folder.

    python tools/echo_proxy.py --listen 8081 --target http://127.0.0.1:8080 --log proof/proxy.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET = "http://127.0.0.1:8080"
LOG_PATH = "proxy.jsonl"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self._record(body)
        request = urllib.request.Request(
            TARGET + self.path,
            data=body,
            headers={k: v for k, v in self.headers.items() if k.lower() != "host"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                payload = response.read()
                code = response.status
                headers = dict(response.headers)
        except Exception as exc:  # noqa: BLE001
            payload = json.dumps({"error": str(exc)}).encode()
            code = 502
            headers = {"Content-Type": "application/json"}

        self.send_response(code)
        self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        request = urllib.request.Request(TARGET + self.path, method="GET")
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        return

    def _record(self, body: bytes) -> None:
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return
        messages = data.get("messages") or []
        system_chars = sum(
            len(str(m.get("content") or "")) for m in messages if m.get("role") == "system"
        )
        record = {
            "at": round(time.time(), 3),
            "path": self.path,
            "bytes": len(body),
            "messages": len(messages),
            "system_chars": system_chars,
            "other_chars": len(body) - system_chars,
            "tools": len(data.get("tools") or []),
            "tool_names": [
                str((item.get("function") or {}).get("name") or item.get("type") or "")
                for item in (data.get("tools") or [])
            ][:8],
            "tool_choice": type(data.get("tool_choice")).__name__,
            "system_sha": hashlib.sha1(
                "
".join(
                    str(m.get("content") or "") for m in messages if m.get("role") == "system"
                ).encode("utf-8", "replace")
            ).hexdigest()[:12],
            "max_tokens": data.get("max_tokens"),
            "stream": bool(data.get("stream")),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def main() -> None:
    global TARGET, LOG_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", type=int, default=8081)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--log", default=LOG_PATH)
    args = parser.parse_args()
    TARGET = args.target.rstrip("/")
    LOG_PATH = args.log
    server = ThreadingHTTPServer(("127.0.0.1", args.listen), Handler)
    print(f"recording {TARGET} on :{args.listen} -> {LOG_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
