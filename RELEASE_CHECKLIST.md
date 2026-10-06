# Release checklist

Run each item from the repository root, **without** a provider key exported for the test commands. Record pass or fail. Never search the tree for a real key's value; that would require reading the key.

| # | Item | How |
|---|---|---|
| 1 | LICENSE present (MIT, correct holder and year) | `head -3 LICENSE` |
| 2 | NOTICE present (upstream MIT notice, per-skill mapping, non-affiliation) | `grep -c "Steve Darlow" NOTICE` and read it |
| 3 | Secret scan | `gitleaks detect --no-git --source . -v` (or `gitleaks git .` after the commit); otherwise trufflehog; otherwise a regex scan for key prefixes (`sk-`, `sk-or-`, `ghp_`, `github_pat_`, `AKIA`, `xox[bp]-`, `AIza`, PEM headers, `Bearer` plus a long token) and high-entropy strings (≥ 32 chars, Shannon entropy ≥ 4.0) |
| 4 | No personal paths, emails or names besides the author line | `grep -rnI -e '/home/' -e '/Users/' -e '@' .`; the only allowed `/home/box/agent-data/workflows` is the documented Grok Bot default; the only allowed personal name is the author/copyright holder and the credited upstream authors |
| 5 | Tests pass | `env -u TYPESAFE_API_KEY python3 -m unittest discover -s tests -v` (set `GJS_REQUIRE_NETWORK=1` so installer tests can't silently skip) |
| 6 | verify_skills passes against the mock | `python3 tools/verify_skills.py --mock --home <temp HOME with jev installed>` (and without `--mock`) |
| 7 | `install.sh --check` works in a clean temp HOME and changes nothing | `HOME=$(mktemp -d) bash install.sh --check` and confirm that HOME is still empty |
| 8 | Full install into a temp HOME works and `jev --help` runs | `H=$(mktemp -d); HOME=$H bash install.sh --skills-dir $H/skills && HOME=$H $H/.local/bin/jev --help`, then `--uninstall` |
| 9 | Frontmatter valid for all 10 skills | covered by `tests/test_skills.py`; also parse each with a YAML parser |
| 10 | README (and other docs) relative links resolve | check that every relative link target exists |
| 11 | CI YAML is valid | parse `.github/**/*.yml` with a YAML parser; check the job keys |
| 12 | shellcheck passes on install.sh | `shellcheck install.sh` (if available) |
| 13 | CHANGELOG has this version and date; the version tag matches | `grep "## \[0.1.0\]" CHANGELOG.md` |
| 14 | Clean tree: no stray files, caches or keys staged | `git status --short`, `git ls-files` |
