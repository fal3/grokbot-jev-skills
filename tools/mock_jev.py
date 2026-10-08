#!/usr/bin/env python3
"""A local stand-in for the Jev API, for checking success-path output shapes offline.

It checks the documented request shapes, then returns deterministic fixtures. A noul gets 0.9, or 0.05 when
the question is about injection or secrets. A choice gets its first option (0.95, with the
rest split). A score gets its top level. The answers are FAKE: never use them for real
decisions or to tune thresholds.

    python3 tools/mock_jev.py 8787
    TYPESAFE_BASE_URL=http://127.0.0.1:8787 jev search < request.json

The mock refuses Authorization headers and binds to 127.0.0.1 only. It tests wire
shapes, not model accuracy, probability calibration or every service validation rule.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOW_WORDS = ("inject", "aimed at", "hidden instruction", "steer", "secret")
MAX_REQUEST_BYTES = 1_000_000


def structured(value):
    return bool(value.strip()) if isinstance(value, str) else isinstance(value, (dict, list)) and bool(value)


def validate_request(body):
    """The documented System One shapes; invalid requests must not look successful."""
    if not isinstance(body, dict) or not isinstance(body.get("state"), (str, dict, list)):
        raise ValueError("state must be a string, object or array")
    if not isinstance(body.get("model"), str) or not body["model"].strip():
        raise ValueError("model is required")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty object")
    for question in questions.values():
        if not isinstance(question, dict) or not structured(question.get("instructions")):
            raise ValueError("each question needs instructions")
        kind, criteria = question.get("type"), question.get("criteria")
        if kind == "noul":
            if criteria is not None and (not isinstance(criteria, dict) or not criteria
                                        or not set(criteria) <= {"true", "false"}
                                        or not all(structured(v) for v in criteria.values())):
                raise ValueError("invalid noul criteria")
        elif kind == "choice":
            if (not isinstance(criteria, dict) or not 2 <= len(criteria) <= 255
                    or not all(v is None or structured(v) for v in criteria.values())):
                raise ValueError("choice needs 2 to 255 described options")
        elif kind == "score":
            if (not isinstance(criteria, list) or not 2 <= len(criteria) <= 10
                    or not all(structured(v) for v in criteria)):
                raise ValueError("score needs 2 to 10 described levels")
        else:
            raise ValueError("unknown question type")
    return questions


def answer(question):
    kind = question["type"]
    if kind == "noul":
        text = json.dumps(question.get("instructions", "")).lower()
        return {"type": "noul", "noul": 0.05 if any(word in text for word in LOW_WORDS) else 0.9}
    if kind == "choice":
        options = list(question["criteria"])
        rest = 0.05 / (len(options) - 1)
        probabilities = {option: (0.95 if index == 0 else rest) for index, option in enumerate(options)}
        confidence = (0.95 - 1 / len(options)) / (1 - 1 / len(options))
        return {"type": "choice", "choice": options[0], "probabilities": probabilities, "confidence": confidence}
    levels = len(question["criteria"])
    return {"type": "score", "score": float(levels - 1),
            "legend": {str(i): (level if isinstance(level, str) else json.dumps(level))
                       for i, level in enumerate(question["criteria"])},
            "probabilities": {str(i): (1.0 if i == levels - 1 else 0.0) for i in range(levels)},
            "confidence": 1.0}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802 - http.server naming
        if self.path != "/v1/systemone":
            self.reply(404, {"error": "unknown_endpoint"})
            return
        if self.headers.get("Authorization") is not None:
            self.reply(400, {"error": "mock_refuses_credentials"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(length))
            questions = validate_request(body)
        except (ValueError, UnicodeDecodeError):
            # Do not echo input: it may contain a credential or personal data.
            self.reply(422, {"error": "invalid_request"})
            return
        self.reply(200, {"model": "mock-jev", "answers": {name: answer(q) for name, q in questions.items()},
                         "usage": {"input_tokens": 100, "output_tokens": 0}})

    def log_message(self, *args):  # keep test output quiet
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
