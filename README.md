# grokbot-jev-skills

**Ten [Grok Bot](#license-and-credits) skills that hand an agent's small decisions to TypeSafe's Jev decision model.**

Jev answers typed questions about a piece of text: *pick one*, *score this*, *yes or no*. It returns [structured answers and probabilities](https://docs.typesafe.ai/api); Choice and Score also include confidence. These skills teach Grok Bot when to ask Jev, which exact `jev` command to run with its shell tool, what the reply means, and what to do when Jev isn't available. The `jev` CLI comes from the upstream project [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills). This repo adapts that project's skills to Grok Bot and installs the CLI pinned to a tested commit. Actual latency and decision quality depend on the provider, input and model version; the local checks do not benchmark either.

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

Every skill shows runnable commands with invented input, representative output shapes with and without a key, the fallback, and what data leaves the machine. They guide a caller; they do not install a Grok Bot runtime hook or enforce permissions in that runtime. The caller validates local ids/options and results, checks source evidence, and preserves existing user approvals before any consequential action. A classification never authorizes a send, deletion, payment, deployment or process intervention.

## Install in two commands

```bash
git clone https://github.com/fal3/grokbot-jev-skills ~/.local/share/grokbot-jev-skills
bash ~/.local/share/grokbot-jev-skills/install.sh
```

The installer:

- clones upstream into `~/.local/share/hermes-jev-skills` and checks out the tested commit `a6f6344` (upstream 0.22.1);
- writes a small launcher at `~/.local/bin/jev` that defaults jev's local decision log to `~/.local/state/jev`, while respecting an existing `HERMES_HOME`;
- embeds a narrow response validator for the pinned `jevkit`: reported Choice/Score confidence cannot exceed the statistic from its returned probabilities, Score needs every rubric probability, and oversized numeric replies take the normal typed-error/fallback path;
- copies the ten skills into Grok Bot's user skill folder, `/home/box/agent-data/workflows/<slug>/SKILL.md`, **only if that folder exists**. Otherwise it skips them unless you pass `--skills-dir DIR`, and `--no-skills` turns this step off;
- never asks for, reads or stores an API key, and never touches other agents' config.

Run `install.sh --check` first to see the plan without changing anything. Re-running refuses an upstream checkout with local changes or commits and preserves edited skills unless you pass `--force`; symbolic-link skill paths are skipped even with `--force`. Uninstall preserves adopted checkouts, ambiguous ownership markers from 0.1.0, and installer-created checkouts with local work or files (including ignored files and reflog-only commits). Other options are `--dir`, `--ref`, `--upstream` and `--bin-dir`; see `install.sh --help`. You need Python 3.9+ and git.

The upstream code is **not vendored**. The installer fetches it from upstream, so its licence and updates stay with upstream. The launcher validator is this repository's code and leaves that checkout unchanged; it never raises a provider's reported confidence. Its probability formulas follow the [TypeSafe confidence reference](https://docs.typesafe.ai/confidence) and still do not prove calibration or decision quality. A custom `--ref` with `jevkit` must preserve the tested validator interface; a custom `--upstream` without `jevkit` uses its own entrypoint without this validation. Pin/interface changes require the full regression suite.

## The API key

- Set **`TYPESAFE_API_KEY`** in the environment Grok Bot's shell commands run in, for example as a Grok Bot secret. The CLI reads the process environment first, then can consult its OS secret-store items and `~/.config/jev/credentials*`. An environment key alone is enough; clearing it does not disable stored credentials.
- **Never paste a key into a chat.** If one is pasted, rotate it.
- Use `jev doctor --offline` to inspect the resolved provider/source without an API call. Plain `jev doctor` sends a live probe and can consume credits; run it only when that provider use is authorized.
- The pinned CLI includes TypeSafe, OpenRouter, Venice and OpenCode Zen endpoints. Verify current account availability, model access and prices with the provider; this repository does not guarantee signup eligibility or a free tier.
- **Fallback caveat:** if no TypeSafe credential is resolved, jev tries OpenRouter, Venice, then Zen, including their stored credentials. A key set for another tool can therefore carry your Jev calls. At this pin, `JEV_PROVIDER=typesafe|openrouter|venice|zen` is a preference **only when that provider has a credential**, not a strict pin. Before a live call, require the provider in `jev doctor --offline` to match the account authorized for this task, and check any `TYPESAFE_BASE_URL` override. If it does not match, skip Jev and use your local fallback. Available credentials are not permission to send private data or use another billing account.

## Fail-open, and the two exceptions

The decision commands handle missing keys and ordinary provider failures with the fallbacks below. These are conservative defaults for classification, not equivalent decisions or proof that waiting, silence or a retry is safe. Check exit status, output shape, error/fallback fields and local candidate membership before use; missing or unusable output requires the authorized local baseline.

| Command | Fallback |
|---|---|
| `jev search` | `decision: unknown`, plus the locally screened head of your list |
| `jev rerank` | `screening: local-only`, plus your list minus pattern-caught injections |
| `jev mail` | every message `needs_attention: true`, no lane |
| `jev triage` | route `today` |
| `jev decide --policy cron-wake` | `wake` |
| `jev decide --question` / `route-to` / `score` | `no_answer` / your `--fallback` / `caller_default` |
| `jev compact-select` | judged turns default to `summarize`; system/recent turns marked `keep` (retain the raw transcript) |
| `jev supervise` | local activity signals (`keep_waiting` or `nudge`); a known exit is handled locally |

**The two exceptions:**

1. `jev ask` (raw typed questions) prints `{"error": "<code>"}` and **exits 2**, so check for `error` before using an answer.
2. `jev doctor` **exits 1** when no key is present and no valid endpoint override can be probed. That is by design, because it is the setup check. Its exit 0 alone does not establish reachability; inspect the `jev` result.

**One caveat:** `jev triage --preset urgency` falls back to `normal_queue`; this supplies no urgency assessment. Check each item's `status`, `error` and `fallback_used` and assess the source locally before deprioritizing it. Malformed input can exit 2 and should be corrected; arbitrary runtime/installation failures are not promised a fallback. Independently confirmed alerts and existing approval requirements still apply during an outage.

## What data leaves the machine

Jev is a cloud API. Most helpers redact and clip selected text and skip input matching their credential patterns. This is heuristic filtering, not anonymization or a guarantee that every secret or personal identifier is withheld. The listed limits are nominal text caps (a truncation marker adds a few characters), not a cap on the whole request. Field names, ids, roles, question instructions and option descriptions can remain unchanged: use locally defined opaque ids and fixed schemas, and inspect every outbound field. Never supply secrets or private data that the task does not permit sending.

- **search**: the date, question, tried and candidate queries, and nominally 900 characters per result. Reranking substitutes `P0`, `P1`, …, but sufficiency checking can send original result ids as field names. Candidate query descriptions can also appear in question instructions; prepare safe queries and opaque ids locally.
- **social research**: the handle-free projection passed to `search`. The caller must apply the skill's local privacy gate and skip the call for identifying/private material; this repository has no separate runtime gate enforcing that instruction.
- **rerank**: the query and nominally 900 characters per passage. Ids and extra metadata are substituted/omitted; names, paths and sources embedded in the text may remain.
- **mail**: the subject, nominally 2,500 characters of body, the sender's domain, a sender class, the timestamp and a few flags. There is no separate display-name field in the outbound state, but names and other identifiers in subject/body text may remain.
- **triage**: the subject, body and sender domain, plus a redacted `to` field.
- **decide / route-to / score**: policy-selected state values, nominally 1,500 characters per text value (4,000 for a non-object state), plus questions and option descriptions. Object field names are not redacted. `--facts` are never sent.
- **compact-select**: redacted first/last fragments of turns selected for judging, nominally 350 characters each, plus their role strings. The returned digest is local and can contain raw retained text; clipping and its final 24,000-character tail cap can still lose necessary constraints even with `status: ok`.
- **supervise**: the redacted goal (nominally 600 characters), the last 3,000 output characters before redaction, timing and repetition signals. A known process exit is handled locally without this request.
- **`jev ask` does no redaction.** It sends exactly what you give it.

Policy logs omit raw state/prompt bodies but retain caller-defined policy, feature and action metadata; keep those free of private data too. The CLI's default estimated daily limiter applies to policy decisions, not all commands, and is not a hard provider billing cap. The details are in each skill and the pinned upstream implementation.

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

`verify_skills.py` strips provider keys, uses temporary HOME/config/state/example directories, and loads a test-only Python guard that blocks the pinned CLI's credential-store lookup and external connections. `--mock` permits only its loopback fake server; that server refuses Authorization headers and returns deterministic fixtures, **not real decisions**. This is isolation for the trusted pinned Python CLI and bundled examples, not a sandbox for arbitrary shell code or custom launchers. Only run trusted examples. Passing checks establishes offline command/output compatibility, not live Grok Bot loading, provider access, classification accuracy or injection resistance.

## Contributing, security, conduct

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [CHANGELOG.md](CHANGELOG.md). Releases follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## License and credits

MIT, copyright (c) 2026 Alex Fallah; see [LICENSE](LICENSE). The skills are adapted from [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills) (MIT, copyright (c) 2026 Steve Darlow); [NOTICE](NOTICE) maps each skill to its upstream source and carries the required notices.

Jev and TypeSafe are products of TypeSafe AI. Grok Bot is a product of its maker. This project is independent and is not affiliated with or endorsed by either.
