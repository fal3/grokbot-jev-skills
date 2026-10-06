## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `python3 -m unittest discover -s tests` passes
- [ ] `python3 tools/verify_skills.py` and `python3 tools/verify_skills.py --mock` pass
- [ ] `shellcheck install.sh` is clean (if install.sh changed)
- [ ] New or changed ```bash blocks have matching entries in `CHECKS` in `tools/verify_skills.py`
- [ ] Documented outputs were verified by running the command, not written from memory
- [ ] "What leaves the machine" is still accurate for any skill touched
- [ ] No keys, tokens, personal paths or real personal data anywhere in the diff
- [ ] No upstream jevkit code is copied in
- [ ] CHANGELOG.md updated under "Unreleased"
