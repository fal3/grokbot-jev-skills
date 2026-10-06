"""The mock answers every question shape the way the real API does."""
import json
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import verify_skills  # noqa: E402


class Mock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = verify_skills.free_port()
        cls.proc = subprocess.Popen([sys.executable, str(REPO / "tools" / "mock_jev.py"), str(cls.port)])
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/", timeout=0.2)
            except urllib.error.HTTPError:
                break  # GET is not served, but the socket answered
            except OSError:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)

    def ask(self, questions):
        body = json.dumps({"state": "x", "model": "m", "questions": questions}).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/systemone", data=body,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

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
        self.assertEqual(answers["d"]["score"], 2.0)
        self.assertAlmostEqual(sum(answers["d"]["probabilities"].values()), 1.0)
        self.assertEqual(reply["model"], "mock-jev")

    def test_objects_parser(self):
        self.assertEqual(verify_skills.objects('noise {"a": 1}\n{"b": {"c": 2}} tail'), [{"a": 1}, {"b": {"c": 2}}])


if __name__ == "__main__":
    unittest.main()
