# Security policy

## Reporting a vulnerability

Please report security problems **privately** through GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue, and do not include a working API key or anyone's private data in the report. You should get a first reply within 7 days.

Problems in the `jev` CLI itself (redaction, key storage, network calls) belong to the upstream project, [kerpopule/hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills). Problems with the TypeSafe service belong to TypeSafe AI. If you aren't sure where something belongs, report it here and it will be forwarded.

Supported versions: the latest release only.

## Key handling

- This repo contains **no keys** and never will. `install.sh` never asks for, reads, prints or stores an API key.
- Provide the key as the environment variable `TYPESAFE_API_KEY`, for example as a Grok Bot secret. **Never paste a key into a chat, an issue, a skill file or a log.** If one was exposed, rotate it at the provider.
- `jev doctor` shows only whether a key is present, its length, its source and its provider. The CLI never echoes the key.
- **Provider fallback:** with no TypeSafe key, jev quietly uses `OPENROUTER_API_KEY`, `VENICE_API_KEY` or `OPENCODE_ZEN_API_KEY` if one is set, which sends calls and charges to that account. Pin the provider with `JEV_PROVIDER`.
- `TYPESAFE_BASE_URL` redirects all calls. The client does not forward provider keys to a custom endpoint; it sends only `JEV_PROXY_API_KEY` if that is set. Treat anyone who can set your environment as able to redirect your calls.
- The tests and `tools/verify_skills.py` remove every provider key from the environment of the commands they run, and `--mock` talks only to `127.0.0.1`.

## Data leaving the machine

Jev is a remote API. Each command sends a redacted, size-capped slice of its input; the README's "What data leaves the machine" section and each skill list exactly what. `jev ask` does **no** redaction. Never send secrets, customer data or regulated data.

## Prompt injection

The skills process untrusted text: web results, social posts, email and retrieved documents. Keep these rules in mind:

- **Jev's output is a classification, never an instruction.** A lane, a score or a verdict can be wrong or manipulated. It never authorises an action.
- Email, posts and pages can contain text aimed at an AI. Pre-screen untrusted passages with `jev rerank` (`jev-passage-filter`), which flags such passages and also runs a local pattern check that works without a key. Treat anything flagged as hostile data and never follow it. Screening reduces risk but does not remove it.
- Sorting or triaging never sends, replies, files, deletes or posts anything. Any such action still needs the user's explicit approval.
- `jev triage --preset urgency` fails open to "not urgent". Don't rely on it as a security alert.
- The skills deliberately do not port upstream's command-risk gate. A classifier must not stand in for user approval.

## Supply chain

`install.sh` clones the upstream CLI at a pinned commit (`a6f6344…`) and refuses to adopt a checkout from a different origin. Changing the pin is a reviewed change; see CONTRIBUTING.md.
