"""Narrow response validation for the pinned CLI, embedded in our launcher.

The external jevkit source remains unchanged. Confidence is bounded by the
documented distribution statistic; invalid numeric conversions become JevError
so the upstream command takes its normal fallback. No keys or network are read
by this module. Only a trusted upstream checkout may be loaded.
"""
import os
import sys
from pathlib import Path


def install_validation(client):
    original = client._check_answer
    original_ask = client.ask

    def checked(name, question, answer):
        if question["type"] == "score" and isinstance(answer, dict):
            # Require canonical wire indices before upstream's int conversion:
            # aliases such as "01" can otherwise collapse probability mass,
            # and Unicode isdigit strings need not be valid int strings.
            raw = answer.get("probabilities")
            expected = {str(i) for i in range(len(question["criteria"]))}
            if not isinstance(raw, dict) or set(raw) != expected:
                raise client.JevError("invalid_response", "score distribution is incomplete or noncanonical")
        try:
            result = original(name, question, answer)
        except (OverflowError, ValueError):
            raise client.JevError("malformed", "answer numeric value is out of range") from None
        kind = question["type"]
        if kind == "noul":
            return result
        probabilities = result["probabilities"]
        if kind == "choice":
            count = len(question["criteria"])
            derived = (max(probabilities.values()) - 1 / count) / (1 - 1 / count)
        else:
            count = len(question["criteria"])
            if set(probabilities) != set(range(count)):
                raise client.JevError("invalid_response", "score distribution is incomplete")
            peak = max(probabilities, key=probabilities.get)
            spread = sum(p * abs(i - peak) for i, p in probabilities.items())
            uniform = sum(abs(i - (count - 1) / 2) for i in range(count)) / count
            derived = 1 - spread / uniform
        # Never promote confidence. Rounding and provider differences may lower
        # a reported value, but cannot make it exceed the available distribution.
        result["confidence"] = min(result["confidence"], max(0.0, min(1.0, derived)))
        return result

    client._check_answer = checked

    def ask(*args, **kwargs):
        try:
            return original_ask(*args, **kwargs)
        except OverflowError:
            # Usage metadata is converted after answer validation in this pin.
            # It must not escape the same caller fallback as a malformed answer.
            raise client.JevError("malformed", "reply numeric value is out of range") from None

    client.ask = ask


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    upstream = Path(args.pop(0))
    # Custom --upstream fixtures/CLIs retain their own entrypoint. Our validator
    # supports the pinned jevkit contract, not arbitrary external implementations.
    if not (upstream / "jevkit" / "cli.py").is_file():
        os.execv(str(upstream / "bin" / "jev"), [str(upstream / "bin" / "jev")] + args)
    sys.path.insert(0, str(upstream))
    from jevkit import client, cli
    install_validation(client)
    return cli.main(args)


if __name__ == "__main__":
    sys.exit(main())
