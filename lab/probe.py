"""Measure new or established synthetic TCP flows. Every event is recorded individually."""
import json
import socket
import sys
import time

ip = sys.argv[1]
mode = sys.argv[2]
connection = None
if mode == "established":
    connection = socket.create_connection((ip, 9300), timeout=0.4)
    connection.sendall(b'{"sequence":0}\n')
    connection.recv(4096)
    print(json.dumps({"ready": True}), flush=True)
    sys.stdin.readline()  # Parent installs rules before allowing the next application record.

results = []
for sequence in range(1, 6):
    current = connection
    start = time.monotonic()
    record = {"sequence": sequence, "mode": mode, "delivered": False}
    try:
        if current is None:
            current = socket.create_connection((ip, 9300), timeout=0.4)
        current.settimeout(0.4)
        current.sendall(json.dumps({"sequence": sequence}).encode() + b"\n")
        response = json.loads(current.recv(4096))
        record.update(delivered=response["sequence"] == sequence, protected_reached=response.get("protected_reached"),
                      freshness_s=max(0, time.time() - response["at"]))
    except (OSError, ValueError, KeyError):
        pass
    finally:
        record["latency_s"] = time.monotonic() - start
        results.append(record)
        if mode != "established" and current:
            current.close()
print(json.dumps({"records": results}), flush=True)
if connection:
    connection.close()
