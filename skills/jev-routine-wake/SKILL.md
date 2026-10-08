---
name: jev-routine-wake
description: Use inside a scheduled routine or monitor run (price watch, inbox check, status poll) to decide whether this run's findings are worth notifying the user about, or should stay silent, using Jev's cron-wake policy.
---

# Should this routine run notify the user? (Jev cron-wake)

Routines that report every tick train people to ignore them. The shipped `cron-wake` policy asks Jev four questions about what changed: worth waking, owner must act, problem, and urgency. Code applies the thresholds and returns `wake` or `skip`. Facts you compute yourself (source failed, first run) decide without Jev and are never sent.

Requires the CLI (see `jev-setup-grok`). Run it with Grok Bot's shell tool at the end of the routine's check, before deciding to message the user.

Before a live call, confirm that the task permits sending the listed data to the configured provider (see the offline checks in `jev-setup-grok`). An available API key is not permission to use a different provider or billing account. If sending the data is not authorized, skip Jev and use the local fallback.

## Do this

1. Do the routine's normal work: fetch, compare with last time, and summarize what changed in a sentence or two. Preserve its authorized notification channel, conditions and quiet policy. Enforce exact thresholds and mandatory alerts in code; Jev may advise on ambiguous findings but may not suppress a confirmed trigger or grant notification permission.
2. Write the state with a file-writing tool or JSON encoder; never paste fetched content into shell source, even a quoted heredoc. Only these four fields are sent: `job`, `purpose`, `changes`, `last_report`. Put facts in a separate file. The example uses invented static input and private scratch files.

```bash
set -e
umask 077
jev_work_dir="$(mktemp -d "${TMPDIR:-/tmp}/jev-wake.XXXXXX")" || exit 1
trap 'rm -rf "$jev_work_dir"' EXIT
cat > "$jev_work_dir/state.json" <<'JEV_JSON_END'
{"job": "daily competitor price check",
 "purpose": "Tell the owner when a tracked price drops below target",
 "changes": "Widget Pro price unchanged at $49; Widget Mini dropped from $25 to $19 (target $20).",
 "last_report": "No changes yesterday."}
JEV_JSON_END
echo '{"first_run": false, "source_failed": false}' > "$jev_work_dir/facts.json"
"$HOME/.local/bin/jev" decide --policy cron-wake --state "$jev_work_dir/state.json" --facts "$jev_work_dir/facts.json"
```

3. Check the exit code, JSON shape and allowed `action`, then apply the routine's own notification rules:
   - `wake`: evaluate a notification through the routine's authorized channel. Verify the findings locally, especially `urgent` annotations, before presenting them as fact. A fallback wake signals classifier unavailability, not a confirmed change or emergency.
   - `skip`: stay silent. Record the run locally so the next run's `last_report` is accurate.
4. If Jev fails or the reply is invalid, apply your local notification policy and record the failure. Do not add periodic "all quiet" notices unless the user requested periodic updates; do not let a Jev `skip` override an independently confirmed notification condition.

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

Recognized provider/policy errors, drift or a spend-cap hit return `wake`. Malformed input or an unexpected runtime failure can instead exit nonzero without a decision. Apply the authorized local notification policy in either case. A successful classifier call can still miss a change. The policy is shipped as "not yet backtested", so independently verify important conditions and record incorrect skips.

## What leaves the machine

Only the named state fields `job`, `purpose`, `changes` and `last_report`, plus the shipped question definitions. Keep these fields simple public strings: their text is pattern-redacted under nominal 1,500-character limits, with head/tail and a five-character clipping marker for long values. Arbitrary nested field names, numbers and private prose are not generally scrubbed. Facts are not sent unless copied into state. State matching the sensitive-pattern gate is withheld; unrecognized secrets can pass it. Describe aggregate changes ("3 new orders over $500") instead of pasting customer or personal records, and never include secrets in any field. Policy decisions are logged without state/question text in the local ledger, unless disabled or moved by its environment options. The policy uses a best-effort estimated-spend brake, not a guaranteed account billing cap.
