---
name: jev-setup-grok
description: Use when installing, verifying, updating or fixing the `jev` CLI (TypeSafe's Jev decision model) for Grok Bot, or when any jev command reports no_key, auth_failed or a missing binary.
---

# Set up the Jev CLI for Grok Bot

Jev is TypeSafe's decision model. It answers typed questions (pick one, score, yes/no) in about 0.4 s and never writes prose. The other `jev-*` skills reach it only through the `jev` CLI, which comes from the upstream project github.com/kerpopule/hermes-jev-skills (stdlib-only Python). Run everything below with Grok Bot's shell tool.

## 1. Check first

```bash
command -v jev; ls -l "$HOME/.local/bin/jev"
"$HOME/.local/bin/jev" --version
"$HOME/.local/bin/jev" doctor
```

`doctor` prints JSON and never prints the key:

```json
{"version": "0.22.1",
 "key": {"present": false, "provider": "absent", "source": "absent", "length": 0},
 "routing": {"config": "...", "privacy_mode": "redacted-text", "tiers_configured": []},
 "hermes_home": null}
```

Ready means `key.present: true`, `key.source: "environment"` and `jev.reachable: true`, with exit 0. Without a key it exits 1 and has no `jev` block. That is expected, not broken. `jev.error` can be `auth_failed`, `credits_exhausted`, `rate_limited`, `network` or `timeout`. `jev doctor --offline` checks only that a key is present and makes no network call. Ignore the `routing` block: model routing doesn't apply to Grok Bot.

## 2. Install (only if the binary is missing)

Use this project's installer. It pins the upstream CLI to a tested commit, writes a launcher at `~/.local/bin/jev`, never touches the key, and leaves other agents' config alone. Do **not** run upstream's `install.py`: it installs skills into other agents' folders and edits their config.

```bash
git clone https://github.com/fal3/grokbot-jev-skills "$HOME/.local/share/grokbot-jev-skills"
bash "$HOME/.local/share/grokbot-jev-skills/install.sh" --check   # preview, changes nothing
bash "$HOME/.local/share/grokbot-jev-skills/install.sh"           # install
```

The launcher keeps jev's local decision ledger and spend counters in `~/.local/state/jev` instead of `~/.hermes`. It needs Python 3.9+ and git. `install.sh --uninstall` removes only what the installer created.

## 3. The key: an environment variable, never the chat

- The CLI reads the key from the process environment variable **`TYPESAFE_API_KEY`**. It checks there first, and that alone is enough: no keychain or credentials file is needed. (Its fallbacks are `secret-tool`, when installed, then `~/.config/jev/credentials`.)
- Ask the user to add the key as a Grok Bot secret or environment variable named `TYPESAFE_API_KEY`, so it reaches shell commands. **Never ask for the key in chat.** If they paste one anyway, don't repeat or store it, tell them to rotate it, and point them to the secret.
- Other providers serve the same Jev with the same answers. Their keys go in `OPENROUTER_API_KEY`, `VENICE_API_KEY` or `OPENCODE_ZEN_API_KEY` (OpenCode Zen has a free tier). With no TypeSafe key, jev falls back to them in that order. **Caution:** an `OPENROUTER_API_KEY` set for some other purpose will then quietly be used for Jev calls. Set `JEV_PROVIDER=typesafe|openrouter|venice|zen` to pin one, and check `key.provider` in `doctor`.
- Never `echo` the variable, never read secret or credential files to "check" it, and never put a key on a command line. `jev doctor` reports only whether it is present and its length.
- Don't run `jev setup-key`. That flow is for desktops; for Grok Bot the key comes from the environment.

## 4. Update

```bash
git -C "$HOME/.local/share/grokbot-jev-skills" pull --ff-only
bash "$HOME/.local/share/grokbot-jev-skills/install.sh"
"$HOME/.local/bin/jev" --version && "$HOME/.local/bin/jev" doctor
```

After an update, re-run one example from each jev skill you rely on, because output fields can change between versions.

## Local state and spend brake

The policy commands (`jev decide`, `score`, `route-to`, `triage --preset`, `batch`) append decisions only, with no prompt text, to `$HERMES_HOME/logs/jev-ledger.jsonl`. They also keep a rate and spend counter in `$HERMES_HOME/jev/`, with a default cap of $1.00/day; once the cap is hit, live calls take their fallback. `jev ledger --total` shows spend. The launcher sets `$HERMES_HOME` to `~/.local/state/jev`.

## Everything fails open

No key, a timeout, a rate limit or a malformed reply never blocks. Every decision command the jev skills use (`search`, `rerank`, `mail`, `triage`, `compact-select`, `supervise`, `decide`, `route-to`, `score`) exits 0 with a usable fallback answer, and each skill says what that fallback is. Two commands behave differently: `jev ask` returns `{"error": code}` with exit 2, and `jev doctor` exits 1 when there is no key. Never stall a task waiting on Jev.
