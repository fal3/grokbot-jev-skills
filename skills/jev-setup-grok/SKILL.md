---
name: jev-setup-grok
description: Use when installing, verifying, updating or fixing the `jev` CLI (TypeSafe's Jev decision model) for Grok Bot, or when any jev command reports no_key, auth_failed or a missing binary.
---

# Set up the Jev CLI for Grok Bot

Jev is TypeSafe's decision model. It answers typed questions (pick one, score, yes/no) rather than writing prose; latency depends on the provider and network. The other `jev-*` skills reach it only through the `jev` CLI, which comes from github.com/kerpopule/hermes-jev-skills (stdlib-only Python). Run everything below with Grok Bot's shell tool.

## 1. Check first

Check the configured provider and the task's permission to make a live API call before using the example below: `doctor` sends a connectivity probe and may use provider credits. For installation or troubleshooting that must stay offline, use `doctor --offline` instead and report connectivity as unverified. Do not silently switch providers or billing accounts to make a check pass.

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

For the intended environment-key setup, ready means the authorized `key.provider`, `key.present: true`, `key.source: "environment"` and `jev.reachable: true`. Exit 0 alone does not prove reachability: with a key present, `doctor` can still exit 0 while `jev.reachable` is false. Without a key and without an endpoint override it exits 1 and has no `jev` block. `jev.error` can include `auth_failed`, `credits_exhausted`, `rate_limited`, `network` or `timeout`. `doctor --offline` reports credential/configuration state without an API probe; it does not authenticate the key. Check any `endpoint_override` against the authorized destination; a valid custom endpoint can be probed without a provider key and uses a separate proxy-credential flow. Ignore the `routing` block for Grok Bot model switching, but preserve any existing configuration.

## 2. Install (only if the binary is missing)

Use this project's installer. It pins the upstream CLI to a tested commit, writes a launcher at `~/.local/bin/jev`, never touches the key, and leaves other agents' config alone. Do **not** run upstream's `install.py`: it installs skills into other agents' folders and edits their config.

```bash
git clone https://github.com/fal3/grokbot-jev-skills "$HOME/.local/share/grokbot-jev-skills"
bash "$HOME/.local/share/grokbot-jev-skills/install.sh" --check   # preview, changes nothing
bash "$HOME/.local/share/grokbot-jev-skills/install.sh"           # install
```

The launcher defaults `HERMES_HOME` to `~/.local/state/jev` when unset, and respects an existing value; ledger-path overrides can move the log too. It needs Python 3.9+ and git. Uninstall removes unchanged managed files and clean checkouts whose ownership is known; it retains adopted checkouts, ambiguous legacy markers and any local work, including ignored files. Linked workflow files/directories are skipped even with `--force`.

## 3. The key: an environment variable, never the chat

- The CLI reads **`TYPESAFE_API_KEY`** from the process environment first. That is enough; without it the CLI can consult macOS Keychain or Linux `secret-tool`, then `~/.config/jev/credentials` (or the configured XDG location). The installer itself does not read keys. Let the CLI report only presence/source; never inspect the underlying secrets yourself.
- Ask the user to add the key as a Grok Bot secret or environment variable named `TYPESAFE_API_KEY`, so it reaches shell commands. **Never ask for the key in chat.** If they paste one anyway, don't repeat or store it, tell them to rotate it, and point them to the secret.
- Other providers expose Jev through the same typed interface; exact answers, availability and pricing can differ. Their environment keys are `OPENROUTER_API_KEY`, `VENICE_API_KEY` and `OPENCODE_ZEN_API_KEY`; they can also have stored credentials. Without a resolvable TypeSafe key, jev scans them in that order. **Caution:** a key supplied for another tool may be used for Jev. `JEV_PROVIDER=typesafe|openrouter|venice|zen` is only a preference: an unknown or keyless preference falls back to the normal scan. Check that `key.provider` in `doctor --offline` actually matches the authorized provider before any live call. If it does not, stop Jev calls and use local fallback; do not silently adopt another account. Check endpoint overrides separately.
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

Policy commands (`decide`, `score`, `route-to`, non-support `triage --preset`, `batch`) record decisions without state or question text in the local ledger; caller-defined policy/feature/action identifiers are retained, so keep them public. The default path is `$HERMES_HOME/logs/jev-ledger.jsonl`, but it can be moved/disabled. Policy counters normally live under `$HERMES_HOME/jev/` with a $1/day **estimated** default brake. Missing token counts, concurrent calls, disabled limits or inaccessible counters can bypass/undercount it; it is not a provider billing cap. `search`, `rerank`, `mail`, support `triage`, `compact-select`, `supervise`, raw `ask` and live `doctor` probes bypass that limiter. Bound calls and use provider-side budget controls where needed. `jev ledger --total` reports the policy ledger estimate, not all account charges.

## Fallbacks and errors

Decision commands are intended to fail open when Jev is unavailable, and each skill says what its fallback is. Check the actual exit code and parsed output before using it: malformed local input or an unexpected runtime failure supplies no usable decision. `jev ask` returns `{"error": code}` with exit 2, and `jev doctor` exits 1 when there is no key and no valid endpoint override. Continue through the caller's authorized local fallback, preserving all existing approval and safety requirements; do not wait indefinitely for Jev.
