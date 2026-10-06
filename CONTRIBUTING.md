# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Ground rules

- **No keys, ever.** Never commit or paste an API key, token or real personal data, including in examples, tests and issue text. Example data must be invented.
- **Don't vendor upstream code.** The `jev` CLI belongs to [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills), and `install.sh` fetches it. Fixes to the CLI go upstream.
- **Keep skills generic.** No personal paths, names, accounts or project details. Invoke the CLI as `"$HOME/.local/bin/jev"`.
- Skills only classify. Never write a skill that sends, deletes, posts or buys something based on a Jev answer without the user's approval.

## Skill format

Each skill is `skills/<slug>/SKILL.md` with YAML frontmatter containing exactly `name` (equal to the slug) and `description` (starting with "Use ", at most 300 characters, and no `": "`). The body should include:

- when to use it, and when not to;
- a runnable ```bash example with real input;
- the output with Jev and without a key, both verified;
- a "Fail-open" section saying what the fallback is;
- a "## What leaves the machine" section.

If you add or change a ```bash block, add or update its entry in `CHECKS` in `tools/verify_skills.py`.

## Checks to run before a PR

```bash
python3 -m unittest discover -s tests -v     # no key needed; installer tests need network
python3 tools/verify_skills.py               # no-key mode
python3 tools/verify_skills.py --mock        # mock mode
shellcheck install.sh                        # if installed
```

None of these need a key, and none should be run with one. The tests remove provider keys from the environment they use. If you have a key and changed an example, run the block once by hand and paste only the output's shape (never the key) into the PR.

## Updating the upstream pin

1. Read the upstream diff since the current pin, especially the network, redaction and key handling.
2. Change `PINNED_REF` in `install.sh` to a full commit SHA (not a branch).
3. Run every check above, and re-verify the documented output shapes and "What leaves the machine" claims against the new version.
4. Update NOTICE (version adapted), README and CHANGELOG.

## Releases

Follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Versioning is semver: skill behaviour or installer interface changes are minor before 1.0, and fixes are patches.

By contributing, you agree that your contribution is licensed under the MIT License (see LICENSE), and you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
