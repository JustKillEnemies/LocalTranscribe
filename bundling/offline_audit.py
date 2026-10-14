"""Optional test instrumentation; inactive during ordinary application startup."""

import os
import sys

audit_file = os.environ.get("LOCAL_TRANSCRIBER_OFFLINE_AUDIT")
if audit_file:
    with open(audit_file, "a", encoding="utf-8") as output:
        output.write("ACTIVE\n")

    def audit(event, arguments):
        if event not in {"socket.connect", "socket.getaddrinfo"}:
            return
        address = arguments[1] if event == "socket.connect" else arguments[0]
        host = address[0] if isinstance(address, tuple) else address
        allowed = host in {"localhost", "127.0.0.1", "::1", b"localhost", b"127.0.0.1", b"::1"}
        with open(audit_file, "a", encoding="utf-8") as output:
            output.write("LOOPBACK\n" if allowed else "REMOTE_ATTEMPT\n")
        if not allowed:
            raise RuntimeError("Offline smoke forbids external Python connections")

    sys.addaudithook(audit)
