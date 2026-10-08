"""Installed launcher regressions against the real pinned CLI and owned loopback replies."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import test_install as install_tests

REPO = install_tests.REPO

sys.path.insert(0, str(REPO / "tools"))
import verify_skills  # noqa: E402
import mock_jev  # noqa: E402


class ReplyHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/v1/systemone" or self.headers.get("Authorization"):
            self.send_error(400)
            return
        response = {"model": "jev-1.13.0", "usage": {"input_tokens": self.server.input_tokens, "output_tokens": 0},
                    "answers": {name: (self.server.answer(question) if callable(self.server.answer)
                                       else self.server.answer)
                                for name, question in request["questions"].items()}}
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Runtime(install_tests.InstallCase):
    # Same pinned clone policy as installation tests, including mandatory CI coverage.
    setUpClass = install_tests.Install.__dict__["setUpClass"]

    def setUp(self):
        super().setUp()
        self.run_install("--no-skills")
        self.launcher = self.home / ".local/bin/jev"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ReplyHandler)
        self.server.input_tokens = 0
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.env = verify_skills.offline_environment(self.home / "isolated", self.launcher,
                                                     self.server.server_port)

    def command(self, *args, state=None, exit_code=0):
        proc = subprocess.run([str(self.launcher), *args], input=json.dumps(state or {"task": "Invented fixture"}),
                              capture_output=True, text=True, env=self.env, cwd=self.home, timeout=20)
        self.assertEqual(proc.returncode, exit_code, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        return json.loads(proc.stdout)

    def route(self, probabilities, confidence):
        self.server.answer = {"type": "choice", "choice": "alpha", "probabilities": probabilities,
                              "confidence": confidence}
        destinations = self.home / "destinations.json"
        destinations.write_text(json.dumps({"alpha": "First queue", "beta": "Second queue"}))
        return self.command("route-to", "--destinations", str(destinations), "--fallback", "human")

    def ask_score(self, answer, exit_code=0):
        self.server.answer = answer
        return self.command("ask", state={"state": "Invented fixture", "questions": {
            "q": {"type": "score", "instructions": "Rate completeness", "criteria": ["low", "mid", "high"]}}},
                            exit_code=exit_code)

    def test_contradictory_confidence_cannot_pass_route_floor(self):
        result = self.route({"alpha": 0.6, "beta": 0.3, "none_fits": 0.1}, 1.0)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["routed"])
        self.assertEqual(result["dest"], "human")
        self.assertAlmostEqual(result["confidence"], 0.4)

    def test_coherent_confident_route_still_succeeds(self):
        result = self.route({"alpha": 0.95, "beta": 0.025, "none_fits": 0.025}, 0.925)
        self.assertTrue(result["routed"])
        self.assertEqual(result["dest"], "alpha")

    def test_distribution_never_promotes_reported_confidence(self):
        result = self.route({"alpha": 1.0, "beta": 0.0, "none_fits": 0.0}, 0.1)
        self.assertFalse(result["routed"])
        self.assertEqual(result["confidence"], 0.1)

    def test_flat_score_has_zero_confidence(self):
        result = self.ask_score({"type": "score", "score": 1, "confidence": 1,
                                 "probabilities": {"0": 1 / 3, "1": 1 / 3, "2": 1 / 3}})
        self.assertAlmostEqual(result["answers"]["q"]["confidence"], 0.0)

    def test_score_requires_every_rubric_probability(self):
        for probabilities in (None, {"2": 1.0}):
            with self.subTest(probabilities=probabilities):
                answer = {"type": "score", "score": 2, "confidence": 1}
                if probabilities is not None:
                    answer["probabilities"] = probabilities
                result = self.ask_score(answer, exit_code=2)
                self.assertEqual(result["error"], "invalid_response")

    def test_oversized_numeric_answer_returns_policy_fallback(self):
        self.server.answer = {"type": "noul", "noul": 10 ** 1000}
        result = self.command("decide", "--policy", "cron-wake")
        self.assertEqual(result["action"], "wake")
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["error"], "malformed")

    def test_oversized_score_returns_typed_error(self):
        result = self.ask_score({"type": "score", "score": 10 ** 1000, "confidence": 1,
                                 "probabilities": {"0": 1.0, "1": 0.0, "2": 0.0}}, exit_code=2)
        self.assertEqual(result["error"], "malformed")

    def test_oversized_usage_returns_policy_fallback(self):
        self.server.input_tokens = 10 ** 400
        self.server.answer = mock_jev.answer
        result = self.command("decide", "--policy", "cron-wake")
        self.assertEqual(result["action"], "wake")
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["error"], "malformed")

    def test_score_rejects_aliases_and_unicode_probability_indices(self):
        for probabilities in ({"0": 0.14, "01": 0.7, "1": 0.01, "2": 0.15},
                              {"0": 0.0, "1": 1.0, "²": 0.0}):
            with self.subTest(probabilities=probabilities):
                result = self.ask_score({"type": "score", "score": 0.31, "confidence": 1,
                                         "probabilities": probabilities}, exit_code=2)
                self.assertEqual(result["error"], "invalid_response")

    def test_malformed_legend_returns_typed_error(self):
        result = self.ask_score({"type": "score", "score": 1, "confidence": 1,
                                 "probabilities": {"0": 0.0, "1": 1.0, "2": 0.0},
                                 "legend": {"²": "Invented label"}}, exit_code=2)
        self.assertEqual(result["error"], "malformed")


if __name__ == "__main__":
    import unittest
    unittest.main()
