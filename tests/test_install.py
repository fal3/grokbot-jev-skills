"""install.sh end to end, in throwaway HOME folders. No key; jev calls fail open or hit the mock.

Upstream is cloned once from GitHub (or taken from $GJS_UPSTREAM, a local clone) and each
install then clones from that copy. Without network the tests skip, unless
GJS_REQUIRE_NETWORK=1 (set in CI), in which case they fail.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
UPSTREAM_URL = "https://github.com/kerpopule/hermes-jev-skills"
STRIP = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "VENICE_API_KEY", "OPENCODE_ZEN_API_KEY",
         "TYPESAFE_BASE_URL", "JEV_PROXY_API_KEY", "JEV_PROVIDER", "GROKBOT_SKILLS_DIR",
         "JEV_UPSTREAM_DIR", "JEV_UPSTREAM_REF", "JEV_UPSTREAM_URL", "JEV_BIN_DIR", "XDG_STATE_HOME")
SENTINEL = "tsk-sentinel-value-that-must-never-be-written-0000"


class Install(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="gjs-install-"))
        local = os.environ.get("GJS_UPSTREAM")
        if local:
            cls.upstream = local
            return
        cls.upstream = str(cls.work / "upstream-cache")
        proc = subprocess.run(["git", "clone", "--quiet", UPSTREAM_URL, cls.upstream], capture_output=True, text=True)
        if proc.returncode != 0:
            if os.environ.get("GJS_REQUIRE_NETWORK") == "1":
                raise RuntimeError(f"could not clone upstream: {proc.stderr}")
            raise unittest.SkipTest("no network to clone upstream; set GJS_UPSTREAM to a local clone")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="home-", dir=self.work))
        self.skills = self.home / "grokbot-workflows"
        self.env = {k: v for k, v in os.environ.items() if k not in STRIP}
        self.env.update(HOME=str(self.home), TYPESAFE_API_KEY=SENTINEL,
                        GROKBOT_DEFAULT_SKILLS_PROBE=str(self.home / "no-such-grokbot-dir"))

    def run_install(self, *args, check=True):
        proc = subprocess.run(["bash", str(INSTALL), "--upstream", self.upstream, *args],
                              capture_output=True, text=True, env=self.env, timeout=300)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn(SENTINEL, proc.stdout + proc.stderr)
        return proc

    def verify(self, *args):
        env = {k: v for k, v in self.env.items() if k != "TYPESAFE_API_KEY"}
        proc = subprocess.run([sys.executable, str(REPO / "tools" / "verify_skills.py"), "--home", str(self.home), *args],
                              capture_output=True, text=True, env=env, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def files_under_home(self):
        return sorted(p for p in self.home.rglob("*") if ".git" not in p.parts)

    def assert_sentinel_never_written(self):
        for path in self.home.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                self.assertNotIn(SENTINEL, path.read_text(errors="replace"), path)

    def test_check_changes_nothing(self):
        proc = self.run_install("--check", "--skills-dir", str(self.skills))
        self.assertIn("would clone", proc.stdout)
        self.assertIn("would copy 10 skills", proc.stdout)
        self.assertEqual(self.files_under_home(), [])

    def test_full_cycle(self):
        proc = self.run_install("--skills-dir", str(self.skills))
        self.assertIn("jev       0.22.1", proc.stdout)
        launcher = self.home / ".local" / "bin" / "jev"
        self.assertTrue(os.access(launcher, os.X_OK))
        head = subprocess.run(["git", "-C", str(self.home / ".local/share/hermes-jev-skills"), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, "a6f6344bae3411b2afaabd640dc28cda736e8894")
        helped = subprocess.run([str(launcher), "--help"], capture_output=True, text=True, env=self.env)
        self.assertEqual(helped.returncode, 0)
        self.assertIn("search", helped.stdout)
        self.assertEqual(sorted(p.name for p in self.skills.iterdir()), sorted(p.name for p in (REPO / "skills").iterdir()))

        self.verify()            # no key: documented fail-open shapes
        self.verify("--mock")    # mock: documented success shapes
        self.assertFalse((self.home / ".hermes").exists(), "launcher must keep jev state out of ~/.hermes")

        again = self.run_install("--skills-dir", str(self.skills))
        self.assertEqual(again.stdout.count("(unchanged)"), 10)

        edited = self.skills / "jev-watch-run" / "SKILL.md"
        edited.write_text(edited.read_text() + "\nlocal note\n")
        third = self.run_install("--skills-dir", str(self.skills))
        self.assertIn("jev-watch-run SKIPPED", third.stdout)
        self.assertTrue(edited.read_text().endswith("local note\n"))

        self.assert_sentinel_never_written()
        gone = self.run_install("--uninstall", "--skills-dir", str(self.skills))
        self.assertIn("kept      " + str(edited), gone.stdout)
        self.assertFalse(launcher.exists())
        self.assertFalse((self.home / ".local/share/hermes-jev-skills").exists())
        self.assertEqual([p.name for p in self.skills.iterdir()], ["jev-watch-run"])

    def test_refuses_foreign_launcher(self):
        launcher = self.home / ".local" / "bin" / "jev"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\necho someone else's jev\n")
        proc = self.run_install("--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not written by this installer", proc.stderr)
        self.assertEqual(launcher.read_text(), "#!/bin/sh\necho someone else's jev\n")
        self.run_install("--uninstall")
        self.assertTrue(launcher.exists())

    def test_default_skills_dir_only_if_it_exists(self):
        proc = self.run_install("--check")
        self.assertIn("skills    none", proc.stdout)
        probe = self.home / "grokbot-default"
        probe.mkdir()
        self.env["GROKBOT_DEFAULT_SKILLS_PROBE"] = str(probe)
        self.run_install()
        self.assertTrue((probe / "jev-search-loop" / "SKILL.md").is_file())
        self.run_install("--uninstall")
        self.assertEqual(list(probe.iterdir()), [])

    def test_no_skills(self):
        probe = self.home / "grokbot-default"
        probe.mkdir()
        self.env["GROKBOT_DEFAULT_SKILLS_PROBE"] = str(probe)
        proc = self.run_install("--no-skills")
        self.assertIn("skills    not installed", proc.stdout)
        self.assertEqual(list(probe.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
