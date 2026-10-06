#!/usr/bin/env python3
"""Run every ```bash block in every skill and check the documented output shapes.

Modes:
  (default)  no key: every provider key and endpoint override is stripped from the
             environment, so each command takes its documented fail-open path.
  --mock     same, plus TYPESAFE_BASE_URL pointed at tools/mock_jev.py on a free local
             port, so each command takes its success path with fake, deterministic answers.

Blocks that install or update (they contain `git ` or `install.sh`) are skipped.
The skills call "$HOME/.local/bin/jev"; pass --home DIR to use a jev installed under DIR.

Usage: python3 tools/verify_skills.py [--mock] [--home DIR] [--skills DIR]
Exit 0 when every check passes.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STRIP = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "VENICE_API_KEY", "OPENCODE_ZEN_API_KEY",
         "TYPESAFE_BASE_URL", "JEV_PROXY_API_KEY", "JEV_PROVIDER", "TYPESAFE_MODEL")


def objects(text):
    """Every top-level JSON object printed to stdout, in order."""
    decoder, index, out = json.JSONDecoder(), 0, []
    while True:
        start = text.find("{", index)
        if start < 0:
            return out
        try:
            obj, end = decoder.raw_decode(text, start)
            out.append(obj)
            index = end
        except json.JSONDecodeError:
            index = start + 1


def expect(condition, detail):
    if not condition:
        raise AssertionError(detail)


def rows_ok(o, rc, test):
    expect(rc == 0, f"exit {rc}")
    expect(o, "no JSON on stdout")
    test(o)


# One entry per runnable bash block, in file order. Each is (no-key check, mock check).
CHECKS = {
    "jev-search-loop": [(
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "fail_open" and o[0]["decision"] == "unknown" and o[0]["screening"] == "local-only"
            and o[0]["selected_ids"] == ["r1", "r2"] and o[0]["dropped_injection_ids"] == ["r3"], o[0])),
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "ok" and o[0]["decision"] == "answer" and o[0]["screening"] == "jev+local"
            and o[0]["selected_ids"] == ["r1", "r2"] and o[0]["dropped_injection_ids"] == ["r3"]
            and isinstance(o[0]["sufficiency"], float), o[0])),
    )],
    "jev-social-research": [(
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "fail_open" and o[0]["decision"] == "unknown" and o[0]["selected_ids"] == ["s1", "s2"], o[0])),
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "ok" and o[0]["screening"] == "jev+local" and o[0]["selected_ids"] == ["s1", "s2"], o[0])),
    )],
    "jev-passage-filter": [(
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "fail_open" and o[0]["screening"] == "local-only"
            and o[0]["selected_ids"] == ["note-1", "note-2", "note-4"] and o[0]["dropped_injection_ids"] == ["note-3"], o[0])),
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "ok" and o[0]["screening"] == "jev+local" and "note-3" in o[0]["dropped_injection_ids"]
            and set(o[0]["scores"]) == {"note-1", "note-2", "note-4"} and "answerable" in o[0], o[0])),
    )],
    "jev-mailbox-sort": [(
        lambda o, rc: rows_ok(o, rc, lambda o: (
            expect(len(o) == 2, f"{len(o)} JSON objects"),
            expect(all(m["needs_attention"] and m["lane"] is None and not m["sent_to_jev"] for m in o[0]["messages"]), o[0]),
            expect(o[0]["messages"][2]["injection"] == "instruction", o[0]["messages"][2]),
            expect(o[1]["messages"] == 3 and o[1]["lanes"]["unsorted"] == 3, o[1]))),
        lambda o, rc: rows_ok(o, rc, lambda o: (
            expect(len(o) == 2, f"{len(o)} JSON objects"),
            expect(all(m["sent_to_jev"] and m["lane"] in ("needs_reply", "updates", "promotional", "sales", "spam")
                       for m in o[0]["messages"]), o[0]),
            expect(o[0]["messages"][2]["injection"] == "instruction", o[0]["messages"][2]),
            expect(o[1]["messages"] == 3 and o[1]["not_sent_to_jev"] == 0, o[1]))),
    )],
    "jev-support-triage": [
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["summary"]["routes"]["today"] == 2 and o[0]["messages"][0]["known_customer"] is True
            and o[0]["messages"][0]["route"] == "today" and "routes" in o[-1] and "messages" in o[-1], o)),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             all(m["sent_to_jev"] and m["route"] in ("now", "today", "queue", "ignore") and m["kind"]
                 for m in o[0]["messages"]), o[0]))),
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["preset"] == "urgency" and o[0]["items"][0]["action"] == "normal_queue"
            and o[0]["items"][0]["fallback_used"] is True, o[0])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             o[0]["preset"] == "urgency" and o[0]["items"][0]["action"] in ("escalate", "normal_queue")
             and o[0]["items"][0]["status"] == "ok", o[0]))),
    ],
    "jev-routine-wake": [(
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[-1]["action"] == "wake" and o[-1]["source"] == "fallback" and o[-1]["error"] == "no_key", o[-1])),
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[-1]["action"] in ("wake", "skip") and o[-1]["source"] == "jev" and o[-1]["status"] == "ok"
            and "worth_waking" in o[-1]["answers"], o[-1])),
    )],
    "jev-typed-decision": [
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(o[-1]["action"] == "no_answer" and o[-1]["verdicts"] == {}, o[-1])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             o[-1]["action"] == "answered" and set(o[-1]["verdicts"]) == {"tell_owner", "needs_action"}, o[-1]))),
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[-1]["action"] == "fallback" and o[-1]["dest"] == "human" and o[-1]["routed"] is False, o[-1])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             o[-1]["status"] == "ok" and "dest" in o[-1] and "confidence" in o[-1], o[-1]))),
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(o[-1]["action"] == "caller_default" and o[-1]["scores"] == {}, o[-1])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             o[-1]["status"] == "ok" and {"quality", "relevance", "completeness", "risk"} <= set(o[-1]["scores"]), o[-1]))),
        (lambda o, rc: (expect(rc == 2, f"exit {rc}"), expect(o and o[-1] == {"error": "no_key"}, o)),
         lambda o, rc: rows_ok(o, rc, lambda o: expect(
             set(o[-1]["answers"]) == {"blocked", "next", "severity"}, o[-1]))),
    ],
    "jev-choose-turns": [(
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "fail_open" and o[0]["counts"] == {"keep": 2, "summarize": 6, "drop": 0}
            and o[0]["unjudged"] == [0, 1, 2, 3, 4, 5] and "digest" in o[0], o[0])),
        lambda o, rc: rows_ok(o, rc, lambda o: expect(
            o[0]["status"] == "ok" and o[0]["unjudged"] == [] and o[0]["jev_calls"] >= 1, o[0])),
    )],
    "jev-watch-run": [
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(o[-1]["action"] == "keep_waiting" and o[-1]["jev_error"] == "no_key", o[-1])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect("progressing" in o[-1] and o[-1]["action"] in
                                                      ("keep_waiting", "answer_question", "nudge", "escalate", "collect"), o[-1]))),
        (lambda o, rc: rows_ok(o, rc, lambda o: expect(o[-1]["action"] == "keep_waiting" and o[-1]["elapsed_s"] == 300.0, o[-1])),
         lambda o, rc: rows_ok(o, rc, lambda o: expect("progressing" in o[-1] and o[-1]["elapsed_s"] == 300.0, o[-1]))),
    ],
    "jev-setup-grok": [
        (lambda o, rc: (expect(rc == 1, f"exit {rc}"),
                        expect(o and o[-1]["key"] == {"present": False, "provider": "absent", "source": "absent", "length": 0}, o)),
         lambda o, rc: (expect(rc == 0, f"exit {rc}"), expect(o and o[-1]["jev"]["reachable"] is True, o))),
    ],
}

# Setup a block needs that the skill leaves to the reader.
PRELUDE = {
    "jev-watch-run": "printf 'Epoch 3/10 loss=0.41\\nEpoch 4/10 loss=0.39\\n' > /tmp/job.log\n",
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="check success paths against tools/mock_jev.py")
    parser.add_argument("--home", help="HOME to run the blocks under (where .local/bin/jev lives)")
    parser.add_argument("--skills", default=str(REPO / "skills"))
    args = parser.parse_args()

    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    if args.home:
        env["HOME"] = args.home
    jev = Path(env.get("HOME", "~")).expanduser() / ".local" / "bin" / "jev"
    if not jev.exists():
        print(f"FAIL: {jev} not found; install first (bash install.sh) or pass --home")
        return 1

    mock = None
    if args.mock:
        port = free_port()
        mock = subprocess.Popen([sys.executable, str(REPO / "tools" / "mock_jev.py"), str(port)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        env["TYPESAFE_BASE_URL"] = f"http://127.0.0.1:{port}"

    failures = passes = 0
    try:
        for path in sorted(Path(args.skills).glob("*/SKILL.md")):
            skill = path.parent.name
            blocks = [b for b in re.findall(r"```bash\n(.*?)```", path.read_text(), re.S)
                      if "git " not in b and "install.sh" not in b]
            checks = CHECKS.get(skill)
            if checks is None:
                print(f"FAIL {skill}: no checks defined")
                failures += 1
                continue
            if len(blocks) != len(checks):
                print(f"FAIL {skill}: {len(blocks)} runnable blocks but {len(checks)} checks")
                failures += 1
                continue
            for index, (block, pair) in enumerate(zip(blocks, checks)):
                check = pair[1] if args.mock else pair[0]
                proc = subprocess.run(["bash", "-c", PRELUDE.get(skill, "") + block], capture_output=True,
                                      text=True, env=env, cwd="/tmp", timeout=120)
                try:
                    check(objects(proc.stdout), proc.returncode)
                    passes += 1
                    print(f"PASS {skill} block {index} (exit {proc.returncode})")
                except Exception as error:  # noqa: BLE001 - report every failure, keep going
                    failures += 1
                    print(f"FAIL {skill} block {index}: {error!r}\n  stdout: {proc.stdout[:600]}\n  stderr: {proc.stderr[:600]}")
    finally:
        if mock is not None:
            mock.terminate()
            mock.wait(timeout=5)
    print(f"{'mock' if args.mock else 'no-key'} mode: {passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
