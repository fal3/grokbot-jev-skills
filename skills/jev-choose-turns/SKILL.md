---
name: jev-choose-turns
description: Use when a long transcript or message log (chat export, meeting log, support thread, agent transcript) must be cut to a fixed size and you need to choose which turns to keep verbatim, clip, or drop. Not for ordinary handoffs.
---

# Choosing turns with Jev

`jev compact-select` marks each turn `keep` (decisions, constraints, exact values, paths, ids, errors and unfinished work), `summarize` (background, clipped to its first 400 characters in the digest), or `drop` (chatter, superseded attempts). Jev writes no summary. You do.

**Measured caveat from the source repo:** for a *handoff*, giving the writer the whole dialogue beat this digest (58.7% recall versus 37.5%). Use this only when the size is truly fixed: a small context, a digest to skim, or a memory note with a hard limit. Otherwise give the writer the full text.

Requires the CLI (see `jev-setup-grok`). Run with Grok Bot's shell tool.

## Do this

1. Put the transcript in a file as `{"messages": [{"role", "content"}, ...]}` or a bare list.
2. Run:

```bash
cat > /tmp/jev-transcript.json <<'JEV_JSON_END'
{"messages": [
 {"role": "user", "content": "Let's migrate the reports job to the new scheduler."},
 {"role": "assistant", "content": "Okay. Decision: keep the cron expression 0 6 * * * and run it in UTC."},
 {"role": "user", "content": "thanks"},
 {"role": "assistant", "content": "Tried path /srv/jobs/old.sh, it failed with exit 127."},
 {"role": "user", "content": "Use /srv/jobs/reports.sh instead."},
 {"role": "assistant", "content": "Switched to /srv/jobs/reports.sh; dry run passed."},
 {"role": "user", "content": "Great, what's left?"},
 {"role": "assistant", "content": "Only enabling alerts remains."}]}
JEV_JSON_END
"$HOME/.local/bin/jev" compact-select --keep-last 2 --digest < /tmp/jev-transcript.json
```

3. If `status` is `ok`, write from `digest`: copy `[KEEP VERBATIM]` lines exactly, and treat `[background]` lines as context only. The digest keeps its last 24,000 characters.
4. If `status` is `fail_open`, or `partial` with `unjudged` covering turns you care about, **ignore the digest and work from the plain transcript.**

## Output shape (verified)

Without a key (exit 0):

```json
{"status": "fail_open",
 "fates": {"0": "summarize", "1": "summarize", "2": "summarize", "3": "summarize", "4": "summarize", "5": "summarize", "6": "keep", "7": "keep"},
 "counts": {"keep": 2, "summarize": 6, "drop": 0}, "jev_calls": 0, "errors": ["no_key"],
 "latency_ms": 0, "unjudged": [0, 1, 2, 3, 4, 5],
 "digest": "[background] user: Let's migrate ...\n\n[KEEP VERBATIM] assistant: Only enabling alerts remains."}
```

With Jev: `status: "ok"` (or `"partial"` if some batches failed), per-index `fates`, `jev_calls` ≥ 1 and an empty `unjudged`.

## Guarantees and fail-open

The last `--keep-last` messages (default 6) and system messages are always kept. A turn is dropped only on a confident (≥0.7) answer. Any turn Jev didn't judge stays `summarize`, never `drop`. With Jev down nothing is lost, but the digest is a worse input than the raw transcript, so use the raw transcript instead. It never blocks.

## What leaves the machine

The first and last 350 characters of each judged turn, redacted (emails, phones, tokens, long hex), 40 turns per request. Turns that look like they contain secrets are skipped. Don't run it over transcripts holding customer data or confidential content unless the user has OK'd it. Never include secrets.
