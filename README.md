# grokbot-jev-skills

**Ten [Grok Bot](#license-and-credits) skills that hand an agent's small decisions to TypeSafe's Jev decision model.**

Jev answers typed questions about a piece of text: *pick one*, *score this*, *yes or no*. It replies in about 0.4 s with calibrated probabilities and never writes prose. These skills teach Grok Bot when to ask Jev, which exact `jev` command to run with its shell tool, what the reply means, and what to do when Jev isn't available. The `jev` CLI comes from the upstream project [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills). This repo adapts that project's skills to Grok Bot and installs the CLI pinned to a tested commit.

## What Jev decides here

| Skill | Use it when… | Jev decides |
|---|---|---|
| [`jev-setup-grok`](skills/jev-setup-grok/SKILL.md) | installing, checking or fixing the `jev` CLI, or a command reports `no_key` / `auth_failed` | nothing (setup and `jev doctor`) |
| [`jev-search-loop`](skills/jev-search-loop/SKILL.md) | a web or connector search returned several results, before you open pages or search again | which results to read, whether the evidence is enough, which of *your* candidate queries to run next |
| [`jev-social-research`](skills/jev-social-research/SKILL.md) | researching social posts, reactions, creators or trends | which discovered posts to open, and whether the opened evidence answers the question (behind a local privacy gate) |
| [`jev-passage-filter`](skills/jev-passage-filter/SKILL.md) | more than ~5 retrieved passages need narrowing, or untrusted text needs screening for prompt injection | relevance per passage, plus which passages carry instructions aimed at an AI |
| [`jev-mailbox-sort`](skills/jev-mailbox-sort/SKILL.md) | sorting a batch of the user's email | needs-reply / updates / promotional / sales / spam, and what needs a person |
| [`jev-support-triage`](skills/jev-support-triage/SKILL.md) | messages arrive at a queue someone works, or items need an urgency ranking | now / today / queue / ignore, kind, blocked, deadline |
| [`jev-routine-wake`](skills/jev-routine-wake/SKILL.md) | a scheduled routine must decide whether to notify the user | wake or stay silent |
| [`jev-typed-decision`](skills/jev-typed-decision/SKILL.md) | a small yes/no, pick-one-of-N, grade-an-output or claim-check step | your own typed questions |
| [`jev-choose-turns`](skills/jev-choose-turns/SKILL.md) | a long transcript must be cut to a fixed size | keep / clip / drop per turn |
| [`jev-watch-run`](skills/jev-watch-run/SKILL.md) | a long background job is running | keep waiting / answer a question / nudge / escalate / collect |

Every skill shows a runnable command with real input, the exact output with and without a key, the fail-open answer, and what data leaves the machine.

## Install in two commands

```bash
git clone https://github.com/fal3/grokbot-jev-skills ~/.local/share/grokbot-jev-skills
bash ~/.local/share/grokbot-jev-skills/install.sh
```

The installer:

- clones upstream into `~/.local/share/hermes-jev-skills` and checks out the tested commit `a6f6344` (upstream 0.22.1);
- writes a small launcher at `~/.local/bin/jev` that keeps jev's local decision log in `~/.local/state/jev`;
- copies the ten skills into Grok Bot's user skill folder, `/home/box/agent-data/workflows/<slug>/SKILL.md`, **only if that folder exists**. Otherwise it skips them unless you pass `--skills-dir DIR`, and `--no-skills` turns this step off;
- never asks for, reads or stores an API key, and never touches other agents' config.

Run `install.sh --check` first to see the plan without changing anything. Re-running the installer is safe, and it won't overwrite a skill file you have edited unless you pass `--force`. `--uninstall` removes only what it created. Other options are `--dir`, `--ref`, `--upstream` and `--bin-dir`; see `install.sh --help`. You need Python 3.9+ and git.

The upstream code is **not vendored**. The installer fetches it from upstream, so its licence and updates stay with upstream.

## The API key

- Set **`TYPESAFE_API_KEY`** in the environment Grok Bot's shell commands run in, for example as a Grok Bot secret. The CLI reads the process environment first, and that alone is enough: no keychain or credentials file is needed.
- **Never paste a key into a chat.** If one is pasted, rotate it.
- Check it with `jev doctor`, which reports only whether a key is present and its length, plus whether Jev answered.
- **Signup caveat:** a comment in the upstream client says TypeSafe isn't accepting new signups. The same Jev is also served through OpenRouter, Venice and OpenCode Zen (which has a free tier).
- **Fallback caveat:** if there is no TypeSafe key, jev uses `OPENROUTER_API_KEY`, then `VENICE_API_KEY`, then `OPENCODE_ZEN_API_KEY`, whichever exists. So an `OPENROUTER_API_KEY` set for some other tool will quietly carry your Jev calls. Set `JEV_PROVIDER=typesafe|openrouter|venice|zen` to pin a provider, and check `key.provider` in `jev doctor`.

## Fail-open, and the two exceptions

No key, a timeout, a rate limit or a malformed reply never blocks a task. Every decision command the skills use exits 0 with a usable fallback:

| Command | Fallback |
|---|---|
| `jev search` | `decision: unknown`, plus the locally screened head of your list |
| `jev rerank` | `screening: local-only`, plus your list minus pattern-caught injections |
| `jev mail` | every message `needs_attention: true`, no lane |
| `jev triage` | route `today` |
| `jev decide --policy cron-wake` | `wake` |
| `jev decide --question` / `route-to` / `score` | `no_answer` / your `--fallback` / `caller_default` |
| `jev compact-select` | everything `summarize` (use the raw transcript) |
| `jev supervise` | `keep_waiting` |

**The two exceptions:**

1. `jev ask` (raw typed questions) prints `{"error": "<code>"}` and **exits 2**, so check for `error` before using an answer.
2. `jev doctor` **exits 1** when no key is present. That is by design, because it is the setup check.

**One caveat:** `jev triage --preset urgency` falls back to `normal_queue`, so a failure reads as "not urgent". Check each item's `status` and `error` before trusting a quiet result. Any command also exits 2 on malformed input, which is your bug, not an outage.

## What data leaves the machine

Jev is a cloud API. Each command sends only a redacted, capped slice. Emails, phone numbers, tokens and long hex strings are masked, and text that looks like a credential is not sent at all.

- **search**: the date, question, tried and candidate queries, and up to 900 characters per result. Result ids are replaced by `P0`, `P1`, …
- **social research**: only the handle-free projection passed to `search`, after a local gate that skips the call entirely for anything person-identifying or private.
- **rerank**: the query and up to 900 characters per passage, with ids, paths and sources replaced.
- **mail**: the subject, up to 2,500 characters of body, the sender's domain (never the mailbox), a sender class, the timestamp and a few flags. **Display names are sent as written.**
- **triage**: the subject, body and sender domain, plus a redacted `to` field.
- **decide / route-to / score**: only the named state fields, each capped at 1,500 characters. `--facts` are never sent.
- **compact-select**: the first and last 350 characters of each turn.
- **supervise**: the goal and the last 3,000 characters of output.
- **`jev ask` does no redaction.** It sends exactly what you give it.

Logs hold decisions only, never prompt text. Never send customer data, regulated data or secrets. The details are in each skill and in upstream's README.

## Not ported, and why

| Upstream piece | Reason |
|---|---|
| Model routing (`jev route`, `models`, pools, dashboard, `replay`, `spend`) | Grok Bot can't switch its own model per turn and has no pre-LLM hook. |
| Lanes (`jev lane`) and the Claude Code lane subagents | They choose the model for a delegated worker; Grok Bot can't. |
| Frontier ladder (`jev ladder`) | It manages paid model seats across a fleet. Its supervision half is ported as `jev-watch-run`. |
| Hermes plugin hooks, including automatic web-result screening | They need plugin seams Grok Bot doesn't have. `jev-passage-filter` and `jev-search-loop` do the screening on demand. |
| Computer use and browser use (`jev choose`, `plan`, the runners) | Jev picks each GUI step inside the driving loop, and Grok Bot's browser/desktop work runs in a subagent Jev can't be plugged into. |
| Skill selection (`jev pick-skill`) | Grok Bot already has its skill catalog in context; a call would add latency and save nothing. |
| Handoff compaction plugin | Grok Bot manages its own context. Only fixed-size turn selection is ported (`jev-choose-turns`). |
| Command risk gate (`jev gate`) | Grok Bot has its own approvals, and a classifier must never stand in for the user's yes. |

## Verify

```bash
python3 -m unittest discover -s tests        # skills, mock and installer tests; no key needed
python3 tools/verify_skills.py               # runs every skill example with no key: fail-open shapes
python3 tools/verify_skills.py --mock        # same, against tools/mock_jev.py: success shapes
```

`verify_skills.py` strips every provider key from the environment. `--mock` points `TYPESAFE_BASE_URL` at a local fake server whose answers are deterministic and **not real decisions**. The jev client never forwards a key to such an endpoint. For 0.1.0, every example was also run once against the live API (TypeSafe provider), and each returned `status: ok` or a real decision.

## Contributing, security, conduct

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [CHANGELOG.md](CHANGELOG.md). Releases follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## License and credits

MIT, copyright (c) 2026 Alex Fallah; see [LICENSE](LICENSE). The skills are adapted from [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills) (MIT, copyright (c) 2026 Steve Darlow); [NOTICE](NOTICE) maps each skill to its upstream source and carries the required notices.

Jev and TypeSafe are products of TypeSafe AI. Grok Bot is a product of its maker. This project is independent and is not affiliated with or endorsed by either.
