---
name: jev-support-triage
description: Use when classifying messages arriving at a queue someone works (support inbox, ticket feed, alerts, form submissions) into now / today / queue / ignore with kind, blocked and deadline signals, or when ranking any text items by urgency.
---

# Support / queue triage with Jev

`jev triage` reads each message and returns a route: `now`, `today`, `queue` or `ignore`. It also returns the message kind and calibrated signals (needs a human, sender blocked, deadline, actionable, frustrated). Code applies the thresholds and Jev supplies the readings. For one person's mailbox ("is this for me?") use `jev-mailbox-sort` instead.

Requires the CLI (see `jev-setup-grok`). Run with Grok Bot's shell tool.

## Support messages

Fields per message: `id`, `subject`, `content` (or `body`; note that `snippet` is **not** read here, so map it to `content`), `sender` (or `from`), and optionally `to` and `received`. `--customer-domain` marks senders whose problem reports should never be filed away. Repeat it for each domain.

```bash
cat > /tmp/jev-tickets.json <<'JEV_JSON_END'
[{"id": "t1", "subject": "Checkout is down for all users", "content": "Since 9am nobody can pay. Please help ASAP.", "sender": "ops@customer.example"},
 {"id": "t2", "subject": "Feature idea", "content": "Would be nice to have dark mode someday.", "sender": "fan@example.org"}]
JEV_JSON_END
"$HOME/.local/bin/jev" triage --file /tmp/jev-tickets.json --customer-domain customer.example
"$HOME/.local/bin/jev" triage --file /tmp/jev-tickets.json --summary   # counts only
```

Without a key (verified, exit 0), every message defaults to `today`:

```json
{"summary": {"messages": 2, "routes": {"now": 0, "today": 2, "queue": 0, "ignore": 0}, "kinds": {},
   "confident_share": 0.0, "needs_review": [], "not_sent_to_jev": 2,
   "latency_ms": {"p50": null, "p90": null}, "cost_estimate_usd": 0.00013},
 "messages": [{"route": "today", "urgency": null, "kind": null, "confidence": 0.0,
   "reason": "Jev unavailable (no_key); defaulted to today", "automated": false, "sent_to_jev": false,
   "id": "t1", "subject": "Checkout is down for all users", "sender": "ops@customer.example",
   "received": null, "known_customer": true}]}
```

With Jev, each row adds `urgency` (0–4), `urgency_confidence`, `kind` (problem/request/question/billing/scheduling/...), `kind_confidence`, `needs_human`, `blocked`, `deadline`, `actionable`, `frustrated` (all 0–1), and a `reason` like `"problem, urgency 4.0/4, sender blocked"`. `summary.needs_review` lists low-confidence rows.

How to act: surface `now` immediately, list `today`, batch `queue`, and only mention the count of `ignore`. A message that looks like it holds a secret routes to `now` and is not sent. An empty message routes to `ignore`.

## Urgency only, for any text items

```bash
echo '[{"text": "Payroll export failed, salaries due tomorrow"}]' | "$HOME/.local/bin/jev" triage --preset urgency
```

This returns `{"preset": "urgency", "counts": {...}, "items": [{"action": "escalate" | "normal_queue", "answers": {...}, "status": ..., "error": ..., "index": 0}]}`. It escalates only when normalized urgency is at least 0.90. Without a key (verified) every item comes back `"action": "normal_queue"` with `"error": "no_key"` and `"fallback_used": true`. **So on this preset, fail-open does not escalate**: never treat `normal_queue` with `fallback_used: true` as "not urgent".

## Fail-open, never block

Support mode fails to `today`, so nothing is silently ignored. The urgency preset fails to `normal_queue`. The command always exits 0 with a row per message. Bad input gives `{"error": "invalid_request", ...}` with exit 2.

## What leaves the machine

Support mode: the subject (≤300 characters) and body (≤2,500), redacted; the sender's domain only; the `to` field, redacted and ≤120 characters; and a local "looks automated" flag. The urgency preset sends the state you give it, redacted, capped at 1,500 characters per field. Messages that look like secrets are never sent. Don't run it over customer data unless the user has approved sending redacted text to TypeSafe. Never include secrets. About $0.00006 per message.

Triage only classifies. Replying, assigning or closing anything still needs the user's explicit OK.
