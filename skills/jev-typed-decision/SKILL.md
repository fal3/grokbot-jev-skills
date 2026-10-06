---
name: jev-typed-decision
description: Use when a small classification inside a task can be a typed question instead of a model judgement — yes/no checks, pick one of N destinations, grade an output against a rubric, or check whether cited lines support a claim — answered by Jev in ~0.4 s.
---

# Typed decisions with Jev (decide / route-to / score / ask)

Jev answers three shapes about a state: **noul** (probability of yes), **choice** (one of 2–255 options you define) and **score** (a position on 2–10 ordered levels). It never writes text. Use it for repeatable, low-stakes calls where a calibrated number beats a guess, and where a wrong answer only costs a fallback. It never stands in for the user's approval.

Requires the CLI (see `jev-setup-grok`). Run with Grok Bot's shell tool, and keep states in files.

## 1. Up to 8 yes/no questions: `jev decide --question`

```bash
cat > /tmp/jev-state.json <<'JEV_JSON_END'
{"job": "daily competitor price check", "changes": "Widget Mini dropped from $25 to $19 (target $20)."}
JEV_JSON_END
"$HOME/.local/bin/jev" decide --state /tmp/jev-state.json \
  --question tell_owner="The owner would want to be told about this today" \
  --question needs_action="The owner must do something in response"
```

With Jev: `{"action": "answered", "status": "ok", "answers": {"tell_owner": {"kind": "noul", "p": 0.9, "unsure": false}}, "verdicts": {"tell_owner": "yes"}, "source": "jev", ...}`. A verdict is `yes` above 0.70, `no` below 0.30 and `unsure` in between. Take `unsure` to the user rather than re-asking.
Without a key (verified, exit 0): `{"action": "no_answer", "status": "error", "error": "no_key", "answers": {}, "verdicts": {}, "fallback_used": true, "source": "fallback", ...}`. Decide yourself.

## 2. Pick a destination: `jev route-to`

```bash
echo '{"billing": "Invoices, refunds, payment problems", "bugs": "Something in the product is broken", "sales": "Pricing questions and new purchases"}' > /tmp/jev-dest.json
echo '{"text": "I was charged twice for October, please refund one."}' > /tmp/jev-work.json
"$HOME/.local/bin/jev" route-to --destinations /tmp/jev-dest.json --state /tmp/jev-work.json --fallback human
```

With Jev: `{"action": "route", "dest": "billing", "routed": true, "pick": "billing", "confidence": 0.9, "margin": 0.87, "status": "ok", ...}`. It routes only when confidence ≥ 0.85 (`--floor`) and the lead over the runner-up is ≥ 0.25 (`--margin`). Otherwise it uses the fallback.
Without a key (verified, exit 0): `{"action": "fallback", "dest": "human", "routed": false, "pick": null, "confidence": null, "error": "no_key", "fallback_used": true, ...}`.

## 3. Grade an output: `jev score`

```bash
echo '{"task": "Summarize the release notes in 3 bullets", "output": "- Faster sync\n- New export\n- Bug fixes"}' > /tmp/jev-score.json
"$HOME/.local/bin/jev" score --state /tmp/jev-score.json --explain
```

This uses the `evaluator-default` policy: quality, relevance, completeness and risk scores plus evidence_present and asks_for_human. `action` is `human_review` (risk.norm > 0.8 or asks_for_human ≥ 0.7), `retry` (quality.norm < 0.7 or no evidence), `continue`, or `caller_default`. The `scores` map holds the readings. `--rubric` takes your own `{"name": {"instructions", "levels": [lowest..highest]}}`.
Without a key (verified, exit 0): `{"action": "caller_default", "status": "error", "error": "no_key", "scores": {}, "fallback_used": true, ...}`. Use your own judgement.

## 4. Raw typed questions: `jev ask` (does NOT fail open)

```bash
cat > /tmp/jev-ask.json <<'JEV_JSON_END'
{"state": "The deploy failed twice on the same migration step.",
 "questions": [
  {"id": "blocked", "type": "noul", "instructions": "The work cannot continue until a person steps in"},
  {"id": "next", "type": "choice", "instructions": "What should happen next?", "criteria": {"retry": "Run the same step again", "escalate": "Hand it to a person"}},
  {"id": "severity", "type": "score", "instructions": "How serious is this?", "criteria": ["Cosmetic", "Degraded", "Down"]}]}
JEV_JSON_END
"$HOME/.local/bin/jev" ask < /tmp/jev-ask.json
```

With Jev: `{"answers": {"blocked": {"type": "noul", "noul": 0.9}, "next": {"type": "choice", "choice": "retry", "probabilities": {...}, "confidence": 0.9}, "severity": {"type": "score", "score": 2.0, "probabilities": {...}, "spread_reported": true, "confidence": 0.95}}, "latency_ms": ..., "jev_model": "...", "provider": "typesafe"}`.
Without a key (verified): it prints `{"error": "no_key"}` and **exits 2**. Treat any `error` key or a non-zero exit as "no answer" and carry on. Don't retry in a loop. A malformed request gives `{"error": "invalid_request", "detail": ...}` and nothing is sent.

**Claim check** (does a cited source support a statement?): the state holds the claim plus only the cited lines, each prefixed `L<n>| `. Ask one choice with `not_enough` listed **first**, then `supports` and `contradicts`. Run one ask per claim. `not_enough` usually means the cited range is wrong, so find the text and re-ask.

## Writing questions that work

- Name the one deciding requirement in the question, and label everything else as a tie-breaker: "Judge only X; tone and length are preferences." Unlabelled attributes are read as requirements.
- The id names a question and `instructions` asks it. Instructions that just repeat the id are refused.
- Keep the state short: only the fields the question needs. Extra text makes answers worse and leaks more.

## What leaves the machine

The state (for `decide`/`route-to`/`score`, each object field redacted and capped at 1,500 characters; a non-object state is capped at 4,000), plus the questions or option descriptions. `--facts` values are never sent. A state that looks like it holds a secret is not sent and takes the fallback. `jev ask` sends the state and questions as given, capped at 60,000 characters, **with no redaction**, so redact it yourself. Never put customer data, personal records or secrets into any state. Policy decisions (without text) are logged locally to `$HERMES_HOME/logs/jev-ledger.jsonl`, under a $1/day default spend cap.
