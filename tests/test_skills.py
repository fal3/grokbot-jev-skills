"""Static checks on the skill files. No network, no key, no jev needed."""
import re
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import verify_skills  # noqa: E402

EXPECTED = {"jev-setup-grok", "jev-search-loop", "jev-social-research", "jev-passage-filter",
            "jev-mailbox-sort", "jev-support-triage", "jev-routine-wake", "jev-typed-decision",
            "jev-choose-turns", "jev-watch-run"}


def frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(": ")
        if not sep:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        fields[key] = value
    return fields


class SkillFiles(unittest.TestCase):
    def setUp(self):
        self.skills = {p.parent.name: p.read_text(encoding="utf-8") for p in (REPO / "skills").glob("*/SKILL.md")}

    def test_all_ten_present(self):
        self.assertEqual(set(self.skills), EXPECTED)

    def test_frontmatter(self):
        for slug, text in self.skills.items():
            with self.subTest(slug):
                fields = frontmatter(text)
                self.assertIsNotNone(fields, "missing --- frontmatter ---")
                self.assertEqual(set(fields), {"name", "description"})
                self.assertEqual(fields["name"], slug)
                self.assertTrue(fields["description"].startswith("Use "), "description should say when to use it")
                self.assertLessEqual(len(fields["description"]), 300)
                self.assertNotRegex(fields["description"], r"^[`'\"&*!|>%@\[{]", "unsafe YAML plain scalar start")
                self.assertNotIn(": ", fields["description"], "': ' breaks a YAML plain scalar")

    def test_invocation_and_contract(self):
        for slug, text in self.skills.items():
            with self.subTest(slug):
                self.assertIn('"$HOME/.local/bin/jev"', text)
                self.assertRegex(text, r"(?i)fail[- ]open|fails open")
                if slug != "jev-setup-grok":
                    self.assertIn("## What leaves the machine", text)
                    self.assertRegex(text, r"(?i)secret")

    def test_no_box_specific_paths(self):
        for slug, text in self.skills.items():
            with self.subTest(slug):
                self.assertNotIn("/home/", text)
                self.assertNotRegex(text, r"(?i)\bthe box\b|on the box")

    def test_every_runnable_block_has_a_check(self):
        for slug, text in self.skills.items():
            with self.subTest(slug):
                blocks = [b for b in re.findall(r"```bash\n(.*?)```", text, re.S)
                          if "git " not in b and "install.sh" not in b]
                self.assertIn(slug, verify_skills.CHECKS)
                self.assertEqual(len(blocks), len(verify_skills.CHECKS[slug]))

    def test_heredoc_json_is_valid(self):
        for slug, text in self.skills.items():
            for body in re.findall(r"<<'JEV_JSON_END'\n(.*?)\nJEV_JSON_END", text, re.S):
                with self.subTest(slug):
                    import json
                    json.loads(body)

    def test_example_request_files_are_private_and_removed(self):
        """Exercise the documented shell paths without an API or real credentials."""
        with tempfile.TemporaryDirectory(prefix="gjs-skill-files-") as directory:
            work = Path(directory)
            home = work / "home"
            launcher = home / ".local/bin/jev"
            launcher.parent.mkdir(parents=True)
            trace = work / "trace.jsonl"
            launcher.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, stat\n"
                "root = pathlib.Path(os.environ['TMPDIR'])\n"
                "rows = []\n"
                "for folder in root.glob('jev-*'):\n"
                "    if folder.is_dir():\n"
                "        rows.append({'path': str(folder), 'mode': stat.S_IMODE(folder.stat().st_mode)})\n"
                "        for file in folder.rglob('*'):\n"
                "            if file.is_file():\n"
                "                rows.append({'path': str(file), 'mode': stat.S_IMODE(file.stat().st_mode)})\n"
                "with open(os.environ['GJS_FILE_TRACE'], 'a') as output:\n"
                "    output.write(json.dumps(rows) + '\\n')\n"
                "print('{}')\n"
                "if os.environ.get('GJS_STUB_FAILURE'):\n"
                "    raise SystemExit(2)\n"
            )
            launcher.chmod(0o755)
            env = {k: v for k, v in os.environ.items()
                   if k not in verify_skills.STRIP and k not in ("BASH_ENV", "ENV", "PYTHONPATH", "PYTHONHOME")}
            env.update(HOME=str(home), TMPDIR=str(work), GJS_FILE_TRACE=str(trace))
            job_log = work / "job.log"
            job_log.write_text("Epoch 3/10 loss=0.41\n")
            exercised = 0
            multiple_calls = []
            for slug, text in self.skills.items():
                blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
                for block in blocks:
                    if "mktemp" not in block:
                        continue
                    with self.subTest(slug=slug):
                        proc = subprocess.run(
                            ["bash", "-c", "umask 022\n" + block.replace("/tmp/job.log", str(job_log))],
                            capture_output=True, text=True, env=env, cwd=work, timeout=10,
                        )
                        self.assertEqual(proc.returncode, 0, proc.stderr)
                        self.assertEqual(list(work.glob("jev-*")), [], "private request files must be cleaned up")
                        exercised += 1
                        if block.count('"$HOME/.local/bin/jev"') > 1:
                            multiple_calls.append((slug, block))
            for slug, block in multiple_calls:
                with self.subTest(slug=slug, failure=True):
                    before = len(trace.read_text().splitlines())
                    proc = subprocess.run(
                        ["bash", "-c", block], capture_output=True, text=True,
                        env=dict(env, GJS_STUB_FAILURE="1"), cwd=work, timeout=10,
                    )
                    self.assertEqual(proc.returncode, 2)
                    self.assertEqual(len(trace.read_text().splitlines()), before + 1,
                                     "a failed first call must not run a later call and hide its exit status")
                    self.assertEqual(list(work.glob("jev-*")), [], "cleanup must also run on command failure")
            self.assertGreater(exercised, 0)
            records = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertTrue(records)
            self.assertTrue(all(record for record in records), "stub must observe the request files before cleanup")
            for record in records:
                for entry in record:
                    self.assertEqual(entry["mode"] & 0o077, 0, entry["path"])


if __name__ == "__main__":
    unittest.main()
