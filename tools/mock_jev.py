#!/usr/bin/env python3
"""A local stand-in for the Jev API, for checking success-path output shapes offline.

It answers every question with a valid, deterministic reply. A noul gets 0.9, or 0.05 when
the question is about injection or secrets. A choice gets its first option (0.9, with the
rest split). A score gets its top level. The answers are FAKE: never use them for real
decisions or to tune thresholds.

    python3 tools/mock_jev.py 8787
    TYPESAFE_BASE_URL=http://127.0.0.1:8787 jev search < request.json

The jev client never forwards a provider key to a TYPESAFE_BASE_URL endpoint, so no key
reaches this server. It binds to 127.0.0.1 only.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOW_WORDS = ("inject", "aimed at", "hidden instruction", "steer", "secret")


def answer(question):
    kind = question["type"]
    if kind == "noul":
        text = json.dumps(question.get("instructions", "")).lower()
        return {"type": "noul", "noul": 0.05 if any(word in text for word in LOW_WORDS) else 0.9}
    if kind == "choice":
        options = list(question["criteria"])
        rest = 0.1 / (len(options) - 1)
        probabilities = {option: (0.9 if index == 0 else rest) for index, option in enumerate(options)}
        return {"type": "choice", "choice": options[0], "probabilities": probabilities, "confidence": 0.9}
    levels = len(question["criteria"])
    return {"type": "score", "score": float(levels - 1),
            "probabilities": {str(i): (1.0 if i == levels - 1 else 0.0) for i in range(levels)},
            "confidence": 0.95}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server naming
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        questions = body.get("questions") or {}
        payload = json.dumps({"model": "mock-jev",
                              "answers": {name: answer(q) for name, q in questions.items()},
                              "usage": {"input_tokens": 100}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep test output quiet
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
