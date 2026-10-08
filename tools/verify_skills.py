#!/usr/bin/env python3
"""Run every ```bash block in every skill and check the documented output shapes.

Modes:
  (default)  no key: provider keys, stored credential lookup and external network
             access are disabled, so each command takes its fail-open path.
  --mock     same, plus TYPESAFE_BASE_URL pointed at tools/mock_jev.py on a free local
             port, so each command takes its success path with fake, deterministic answers.

Blocks that install or update (they contain `git ` or `install.sh`) are skipped.
The skills call "$HOME/.local/bin/jev"; pass --home DIR to select that installed launcher.
Each run uses a temporary HOME, config, state and example-file directory. Only trusted
skill examples should be run: the Python guard is not a sandbox for arbitrary shell code.

Usage: python3 tools/verify_skills.py [--mock] [--home DIR] [--skills DIR]
Exit 0 when every check passes.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from http.server import ThreadingHTTPServer
from mock_jev import Handler

REPO = Path(__file__).resolve().parents[1]
STRIP = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "VENICE_API_KEY", "OPENCODE_ZEN_API_KEY",
         "TYPESAFE_BASE_URL", "JEV_PROXY_API_KEY", "JEV_PROVIDER", "TYPESAFE_MODEL",
         "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "BASH_ENV", "ENV",
         "JEV_LEDGER_PATH", "JEV_ROUTING_CONFIG", "JEV_LEDGER", "JEV_LIMITS")


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


def offline_environment(work, launcher, port=0):
    """Never let a check consult the real user's keys or write their Jev state."""
    home = work / "home"
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "jev").symlink_to(launcher)
    guard_dir = work / "python-guard"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text((REPO / "tools" / "offline_guard.py").read_text())
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(work / "config"),
               XDG_CACHE_HOME=str(work / "cache"), TMPDIR=str(work),
               XDG_STATE_HOME=str(work / "state"), HERMES_HOME=str(work / "state"),
               PYTHONPATH=str(guard_dir), GJS_OFFLINE_PORT=str(port),
               PATH=str(bin_dir) + os.pathsep + env.get("PATH", os.defpath))
    # A stale inherited marker must not claim that a startup guard actually loaded.
    env.pop("GJS_OFFLINE_GUARD_ACTIVE", None)
    if port:
        env["TYPESAFE_BASE_URL"] = f"http://127.0.0.1:{port}"
    return env


def example_command(skill, block, work):
    """Keep the examples' fixed /tmp files private to this block/run."""
    return (PRELUDE.get(skill, "") + block).replace("/tmp/", str(work) + "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="check success paths against tools/mock_jev.py")
    parser.add_argument("--home", help="HOME to run the blocks under (where .local/bin/jev lives)")
    parser.add_argument("--skills", default=str(REPO / "skills"))
    args = parser.parse_args()

    jev = Path(args.home or os.environ.get("HOME", "~")).expanduser() / ".local" / "bin" / "jev"
    if not jev.exists():
        print(f"FAIL: {jev} not found; install first (bash install.sh) or pass --home")
        return 1

    jev = jev.absolute()
    mock = None
    if args.mock:
        # Bind port 0 once and keep the socket; free_port()+Popen had a bind race.
        mock = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=mock.serve_forever, daemon=True).start()

    failures = passes = 0
    try:
        with tempfile.TemporaryDirectory(prefix="gjs-verify-") as directory:
            work = Path(directory)
            env = offline_environment(work, jev, mock.server_port if mock else 0)
            guard_check = subprocess.run(["python3", "-c", "import os; assert os.environ.get('GJS_OFFLINE_GUARD_ACTIVE') == '1'"],
                                         env=env, capture_output=True, text=True, timeout=10)
            if guard_check.returncode:
                print("FAIL: offline Python guard could not be loaded")
                return 1
            paths = sorted(Path(args.skills).glob("*/SKILL.md"))
            if not paths:
                print(f"FAIL: no skill files found under {args.skills}")
                return 1
            for path in paths:
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
                    block_work = work / f"{skill}-{index}"
                    block_work.mkdir()
                    proc = None
                    block_env = dict(env, TMPDIR=str(block_work))
                    try:
                        proc = subprocess.run(["bash", "-c", example_command(skill, block, block_work)], capture_output=True,
                                              text=True, env=block_env, cwd=block_work, timeout=120)
                        check(objects(proc.stdout), proc.returncode)
                        passes += 1
                        print(f"PASS {skill} block {index} (exit {proc.returncode})")
                    except subprocess.TimeoutExpired:
                        failures += 1
                        print(f"FAIL {skill} block {index}: timed out after 120 seconds")
                    except Exception as error:  # noqa: BLE001 - report every failure, keep going
                        failures += 1
                        detail = f"\n  stdout: {proc.stdout[:600]}\n  stderr: {proc.stderr[:600]}" if proc else ""
                        print(f"FAIL {skill} block {index}: {error!r}{detail}")
    finally:
        if mock is not None:
            mock.shutdown()
            mock.server_close()
    print(f"{'mock' if args.mock else 'no-key'} mode: {passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
