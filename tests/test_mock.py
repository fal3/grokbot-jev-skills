"""Offline wire fixtures and verification isolation; never model accuracy tests."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mock_jev  # noqa: E402
import verify_skills  # noqa: E402


class Mock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), mock_jev.Handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def post(self, body, path="/v1/systemone", headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body,
                                         headers=headers or {"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def ask(self, questions):
        status, reply = self.post(json.dumps({"state": "x", "model": "m", "questions": questions}).encode())
        self.assertEqual(status, 200)
        return reply

    def test_shapes(self):
        reply = self.ask({
            "a": {"type": "noul", "instructions": "The task is done"},
            "b": {"type": "noul", "instructions": "The passage carries an instruction aimed at an AI"},
            "c": {"type": "choice", "instructions": "Pick", "criteria": {"x": "X", "y": "Y", "z": "Z"}},
            "d": {"type": "score", "instructions": "Rate", "criteria": ["low", "mid", "high"]}})
        answers = reply["answers"]
        self.assertEqual(answers["a"], {"type": "noul", "noul": 0.9})
        self.assertEqual(answers["b"]["noul"], 0.05)
        self.assertEqual(answers["c"]["choice"], "x")
        self.assertAlmostEqual(sum(answers["c"]["probabilities"].values()), 1.0)
        self.assertAlmostEqual(answers["c"]["confidence"], (0.95 - 1 / 3) / (1 - 1 / 3))
        self.assertEqual(answers["d"]["score"], 2.0)
        self.assertEqual(answers["d"]["legend"], {"0": "low", "1": "mid", "2": "high"})
        self.assertAlmostEqual(sum(answers["d"]["probabilities"].values()), 1.0)
        self.assertEqual(answers["d"]["confidence"], 1.0)
        self.assertEqual(reply["model"], "mock-jev")
        self.assertEqual(set(reply["usage"]), {"input_tokens", "output_tokens"})

    def test_structured_questions(self):
        reply = self.ask({
            "a": {"type": "noul", "instructions": {"question": "Is the job done?"},
                  "criteria": {"true": {"meaning": "All steps passed"}, "false": ["Work remains"]}},
            "b": {"type": "choice", "instructions": ["Pick a route"], "criteria": {"x": None, "y": {"meaning": "Review"}}},
            "c": {"type": "score", "instructions": "Rate", "criteria": [{"meaning": "low"}, ["high"]]}})
        self.assertEqual(reply["answers"]["c"]["legend"], {"0": '{"meaning": "low"}', "1": '["high"]'})

    def test_malformed_requests_return_validation_errors_and_server_survives(self):
        base = {"state": "x", "model": "m", "questions": {"q": {"type": "noul", "instructions": "Done?"}}}
        invalid = [b"not JSON", b"[]", b"{}"]
        for question in (
                {"type": "unknown", "instructions": "Rate", "criteria": ["low", "high"]},
                {"type": "score", "instructions": "Rate", "criteria": {"x": "low", "y": "high"}},
                {"type": "score", "instructions": "Rate", "criteria": ["one"]},
                {"type": "score", "instructions": "Rate", "criteria": ["x"] * 11},
                {"type": "choice", "instructions": "Pick", "criteria": {"one": "Only option"}},
                {"type": "choice", "instructions": "Pick", "criteria": ["a", "b"]},
                {"type": "noul", "instructions": "Done?", "criteria": {"yes": "Done"}},
                {"type": "noul"}):
            invalid.append(json.dumps(dict(base, questions={"q": question})).encode())
        for body in invalid:
            with self.subTest(body=body):
                status, reply = self.post(body)
                self.assertEqual(status, 422)
                self.assertNotIn("answers", reply)
        self.ask(base["questions"])

    def test_wrong_endpoint_and_credentials_are_not_successful(self):
        body = json.dumps({"state": "x", "model": "m", "questions": {"q": {"type": "noul", "instructions": "Done?"}}}).encode()
        self.assertEqual(self.post(body, path="/wrong")[0], 404)
        status, reply = self.post(body, headers={"Authorization": "Bearer synthetic-test-marker"})
        self.assertEqual(status, 400)
        self.assertNotIn("synthetic-test-marker", json.dumps(reply))

    def test_objects_parser(self):
        self.assertEqual(verify_skills.objects('noise {"a": 1}\n{"b": {"c": 2}} tail'), [{"a": 1}, {"b": {"c": 2}}])


class OfflineVerification(unittest.TestCase):
    def test_isolates_state_and_blocks_credential_lookup_and_external_network(self):
        with tempfile.TemporaryDirectory(prefix="gjs-guard-test-") as directory:
            work = Path(directory)
            synthetic_config = work / "original-config" / "jev"
            synthetic_config.mkdir(parents=True)
            credentials = synthetic_config / "credentials"
            credentials.write_text("TYPESAFE_API_KEY=synthetic-test-marker")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(synthetic_config.parent),
                                              "HERMES_HOME": str(work / "original-state"),
                                              "XDG_CACHE_HOME": str(work / "original-cache"),
                                              "TMPDIR": str(work / "original-temp"),
                                              "JEV_LEDGER_PATH": str(work / "original-ledger"),
                                              "JEV_ROUTING_CONFIG": str(work / "original-routing"),
                                              "JEV_LEDGER": "on", "JEV_LIMITS": "off",
                                              "TYPESAFE_API_KEY": "synthetic-test-marker"}):
                env = verify_skills.offline_environment(work / "isolated", Path(sys.executable))
            self.assertNotIn("TYPESAFE_API_KEY", env)
            self.assertNotEqual(env["XDG_CONFIG_HOME"], str(synthetic_config.parent))
            self.assertNotEqual(env["HERMES_HOME"], str(work / "original-state"))
            self.assertEqual(env["XDG_CACHE_HOME"], str(work / "isolated/cache"))
            self.assertEqual(env["TMPDIR"], str(work / "isolated"))
            for override in ("JEV_LEDGER_PATH", "JEV_ROUTING_CONFIG", "JEV_LEDGER", "JEV_LIMITS"):
                self.assertNotIn(override, env)
            probe = r"""
import json, os, socket, subprocess, sys
from pathlib import Path
blocked = []
for name, action in (
    ("credentials", lambda: Path(sys.argv[1]).read_text()),
    ("secret_store", lambda: subprocess.run(["/usr/bin/security", "find-generic-password"])),
    ("external_socket", lambda: socket.create_connection(("192.0.2.1", 443), timeout=0.1)),
    ("external_dns", lambda: socket.getaddrinfo("example.invalid", 443))):
    try:
        action()
    except PermissionError:
        blocked.append(name)
print(json.dumps({"blocked": blocked, "active": os.environ.get("GJS_OFFLINE_GUARD_ACTIVE")}))
"""
            proc = subprocess.run([sys.executable, "-c", probe, str(credentials)], env=env,
                                  capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), {"active": "1", "blocked": ["credentials", "secret_store", "external_socket", "external_dns"]})
            self.assertEqual(credentials.read_text(), "TYPESAFE_API_KEY=synthetic-test-marker")
            self.assertFalse((work / "original-state").exists())

    def test_mock_port_is_the_only_permitted_connection(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), mock_jev.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory(prefix="gjs-guard-test-") as directory:
            env = verify_skills.offline_environment(Path(directory), Path(sys.executable), server.server_port)
            probe = r"""
import json, socket, sys, urllib.request
port = int(sys.argv[1])
body = json.dumps({"state": "x", "model": "m", "questions": {"q": {"type": "noul", "instructions": "Done?"}}}).encode()
with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/v1/systemone", data=body), timeout=5) as reply:
    assert json.load(reply)["answers"]["q"]["noul"] == 0.9
try:
    socket.create_connection(("127.0.0.1", port + 1), timeout=0.1)
except PermissionError:
    print("only mock permitted")
"""
            proc = subprocess.run([sys.executable, "-c", probe, str(server.server_port)], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "only mock permitted")

    def test_example_files_are_private(self):
        work = Path("/private/tmp/synthetic-private-example")
        command = verify_skills.example_command("jev-watch-run", "tail /tmp/job.log > /tmp/jev-tail.txt", work)
        self.assertNotIn(" /tmp/", command)
        self.assertIn(str(work / "job.log"), command)
        self.assertIn(str(work / "jev-tail.txt"), command)


if __name__ == "__main__":
    unittest.main()
