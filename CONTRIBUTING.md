# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Ground rules

- **No keys, ever.** Never commit or paste an API key, token or real personal data, including in examples, tests and issue text. Example data must be invented.
- **Don't vendor upstream code.** The `jev` CLI belongs to [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills), and `install.sh` fetches it. CLI source fixes belong upstream; this repository's launcher validation stays narrow, tied to the tested pin and covered by installed-command regressions.
- **Keep skills generic.** No personal paths, names, accounts or project details. Invoke the CLI as `"$HOME/.local/bin/jev"`.
- Skills only classify. Never write a skill that sends, deletes, posts or buys something based on a Jev answer without the user's approval.

## Skill format

Each skill is `skills/<slug>/SKILL.md` with YAML frontmatter containing exactly `name` (equal to the slug) and `description` (starting with "Use ", at most 300 characters, and no `": "`). The body should include:

- when to use it, and when not to;
- a runnable ```bash example with invented static input;
- representative output shapes checked against the mock and without a key, with live validation labelled separately;
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

None of these need a key. The verifier isolates state and blocks the pinned Python CLI's stored-credential lookup and external connections; clearing environment keys alone is insufficient. Mock success does not measure classification accuracy. A live example check is optional and requires explicit authorization for the provider, billing account and outbound data; report any untested live behavior rather than making a paid call to complete a PR.

## Updating the upstream pin

1. Read the upstream diff since the current pin, especially the network, redaction and key handling.
2. Change `PINNED_REF` in `install.sh` to a full commit SHA (not a branch).
3. Run every check above, and re-verify the documented output shapes and "What leaves the machine" claims against the new version.
   Check `tools/jev_runtime.py` against the new `jevkit` interface and probability semantics; the launcher embeds that adapter and its tests must pass through the actual installed command.
4. Update NOTICE (version adapted), README and CHANGELOG.

## Releases

Follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Versioning is semver: skill behaviour or installer interface changes are minor before 1.0, and fixes are patches.

By contributing, you agree that your contribution is licensed under the MIT License (see LICENSE), and you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
