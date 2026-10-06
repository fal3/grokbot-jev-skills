# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [semantic versioning](https://semver.org/).

## [0.1.0] - 2026-10-06

### Added

- Ten Grok Bot skills adapted from kerpopule/hermes-jev-skills 0.22.1: `jev-setup-grok`, `jev-search-loop`, `jev-social-research`, `jev-passage-filter`, `jev-mailbox-sort`, `jev-support-triage`, `jev-routine-wake`, `jev-typed-decision`, `jev-choose-turns` and `jev-watch-run`. Each has runnable examples, verified output with and without a key, fail-open behaviour and a "what leaves the machine" section.
- `install.sh`, an idempotent installer:
  - pins the upstream CLI to commit `a6f6344` (0.22.1), with `--ref` to choose another;
  - writes a `~/.local/bin/jev` launcher that keeps local state in `~/.local/state/jev`;
  - copies skills into Grok Bot's skill folder only if it exists, or into `--skills-dir`;
  - tracks the files it installs with a manifest, so edited skills are kept unless `--force` is given;
  - supports `--check` and `--uninstall`;
  - never handles API keys.
- `tools/verify_skills.py`, which runs every skill example in no-key mode or against `tools/mock_jev.py`, a local deterministic fake of the Jev endpoint.
- Tests that run with plain `python3 -m unittest` and need no key, plus GitHub Actions CI on Python 3.9 and 3.12.
- README, NOTICE (upstream credit and the per-skill mapping), SECURITY, CONTRIBUTING, Code of Conduct and the release checklist.

[0.1.0]: https://github.com/fal3/grokbot-jev-skills/releases/tag/v0.1.0
