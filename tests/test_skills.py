"""Static checks on the skill files. No network, no key, no jev needed."""
import re
import sys
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


if __name__ == "__main__":
    unittest.main()
