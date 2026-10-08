"""Test-only Python startup guard for the pinned CLI's offline example checks.

The verifier copies this file as sitecustomize.py into a temporary PYTHONPATH.
It blocks credential lookup and all sockets except its one loopback mock. This
guards the trusted Python CLI; it is not a sandbox for arbitrary shell examples.
"""
import os
import sys
from pathlib import Path


def install():
    port = int(os.environ.get("GJS_OFFLINE_PORT", "0"))

    def guard(event, args):
        if event == "subprocess.Popen":
            executable = os.fsdecode(args[0])
            if Path(executable).name in ("security", "secret-tool"):
                raise PermissionError("offline checks disable OS credential lookup")
        elif event == "open":
            filename = args[0]
            if isinstance(filename, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(filename))
                if path.parent.name == "jev" and (path.name == "credentials" or path.name.startswith("credentials-")):
                    raise PermissionError("offline checks disable credential files")
        elif event == "socket.getaddrinfo":
            if not (port and args[:2] == ("127.0.0.1", port)):
                raise PermissionError("offline checks disable external DNS lookups")
        elif event == "socket.connect":
            address = args[1]
            if not (port and isinstance(address, tuple) and address[:2] == ("127.0.0.1", port)):
                raise PermissionError("offline checks allow only their loopback mock")

    sys.addaudithook(guard)
    os.environ["GJS_OFFLINE_GUARD_ACTIVE"] = "1"


install()
