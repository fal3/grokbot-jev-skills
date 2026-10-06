---
name: jev-routine-wake
description: Use inside a scheduled routine or monitor run (price watch, inbox check, status poll) to decide whether this run's findings are worth notifying the user about, or should stay silent, using Jev's cron-wake policy.
---

# Should this routine run notify the user? (Jev cron-wake)

Routines that report every tick train people to ignore them. The shipped `cron-wake` policy asks Jev four questions about what changed: worth waking, owner must act, problem, and urgency. Code applies the thresholds and returns `wake` or `skip`. Facts you compute yourself (source failed, first run) decide without Jev and are never sent.

Requires the CLI (see `jev-setup-grok`). Run it with Grok Bot's shell tool at the end of the routine's check, before deciding to message the user.

## Do this

1. Do the routine's normal work: fetch, compare with last time, and summarize what changed in a sentence or two.
2. Write the state. Only these four fields are sent: `job`, `purpose`, `changes`, `last_report`. Put facts in a separate file.

```bash
cat > /tmp/jev-wake-state.json <<'JEV_JSON_END'
{"job": "daily competitor price check",
 "purpose": "Tell the owner when a tracked price drops below target",
 "changes": "Widget Pro price unchanged at $49; Widget Mini dropped from $25 to $19 (target $20).",
 "last_report": "No changes yesterday."}
JEV_JSON_END
echo '{"first_run": false, "source_failed": false}' > /tmp/jev-wake-facts.json
"$HOME/.local/bin/jev" decide --policy cron-wake --state /tmp/jev-wake-state.json --facts /tmp/jev-wake-facts.json
```

3. Act on `action`:
   - `wake`: notify the user through the routine's normal channel. If `annotations` contains `"urgent"`, say so up front.
   - `skip`: stay silent. Record the run locally so the next run's `last_report` is accurate.
4. **Your own valve (code, not Jev):** if the routine has stayed silent for N hours (say 6), wake once anyway with a short "all quiet" note, then reset the counter.

`source_failed: true` (the fetch broke) or `first_run: true` always gives `wake` with `"source": "code"` and sends nothing.

## Output shape (verified)

Without a key (exit 0) it fails open to **wake**:

```json
{"action": "wake", "rule_action": null, "matched_rule": null, "fired_rules": [], "annotations": [],
 "unsure": [], "answers": {}, "jev_model": null, "status": "error", "error": "no_key",
 "fallback_used": true, "sent_to_jev": false, "source": "fallback",
 "policy": "cron-wake@1#0e629d9f", "feature": "cron_wake", "mode": "live", "cost_usd": 0.0, "...": "..."}
```

With Jev: `status: "ok"`, `source: "jev"`, `fired_rules` / `matched_rule`, `annotations` (e.g. `["urgent"]`), and `answers` such as `{"worth_waking": {"kind": "noul", "p": 0.9, "unsure": false}, "urgency": {"kind": "score", "score": 4.0, "norm": 1.0, ...}}`. It wakes if worth_waking ≥ 0.3, owner_must_act ≥ 0.3, problem ≥ 0.4, or urgency.norm ≥ 0.75. Otherwise it skips. `--explain` shows each rule's readings. Bad input gives `{"error": "invalid_request", ...}` with exit 2.

## Fail-open, never block

On any error, drift or spend-cap hit, the answer is `wake`. That costs at most an extra notification and never a missed one. The policy is shipped as "not yet backtested", so if skips look wrong, keep the routine waking and tell the user.

## What leaves the machine

Only `job`, `purpose`, `changes` and `last_report`, each redacted (emails, phones, tokens, long hex) and capped at 1,500 characters. Facts are never sent. A state that looks like it contains a secret is not sent. Keep customer data, personal records and secrets out of `changes`: describe them ("3 new orders over $500"), don't paste them. Decisions (without text) are logged to `$HERMES_HOME/logs/jev-ledger.jsonl`.
