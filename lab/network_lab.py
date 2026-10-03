"""Packet qualification inside a disposable, network-none container only.

No host interfaces, host namespace, host firewall, volumes or external addresses.
This is a separate lab adapter, not a claim that the console currently enforces nftables.
"""
import json
import os
import platform
import subprocess
import sys
import time

NODES = {"g": 0, "p": 1, "x": 2, "m": 3, "a": 4}
processes = []


def command(*args, **options):
    result = subprocess.run(args, capture_output=True, text=True, **options)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def namespace(node):
    return "withaq-" + node


def probe(node, mode="new"):
    return json.loads(command("ip", "netns", "exec", namespace("g"), sys.executable, "/lab/probe.py", "10.77." + str(NODES[node]) + ".2", mode))


def enforce(actions):
    pairs = []
    if "a" in actions:
        pairs.append(("g", "p"))
    if "b" in actions:
        pairs.append(("g", "x"))
    if "c" in actions:
        pairs.extend(("g", target) for target in ("p", "x", "m", "a"))
    if "d" in actions:
        pairs.append(("x", "p"))
    addresses = lambda node: "10.77." + str(NODES[node]) + ".2"
    rules = []
    for source, target in pairs:
        for a, b in ((source, target), (target, source)):
            rules.append(f"ip saddr {addresses(a)} ip daddr {addresses(b)} counter drop")
    # Denies precede established acceptance, so existing TCP sessions cannot bypass containment.
    rules.extend(["ct state established,related accept",
        "ip saddr 10.77.0.2 ip daddr { 10.77.1.2, 10.77.2.2, 10.77.3.2, 10.77.4.2 } tcp dport 9300 accept",
        "ip saddr 10.77.2.2 ip daddr 10.77.1.2 tcp dport 9300 accept"])
    script = "flush ruleset\ntable inet withaq_lab {\n chain forward {\n type filter hook forward priority 0; policy drop;\n" + ";\n".join(rules) + ";\n }\n}\n"
    command("nft", "-f", "-", input=script)


def main():
    report = {"mode": "isolated-container-packets", "synthetic_devices": True, "host_firewall_modified": False,
              "topology": "G/X/P/M/A through one PEP; X is an application relay", "cases": {}}
    report["runtime"] = {"python": sys.version, "kernel": platform.release(), "nftables": command("nft", "--version").strip(),
                         "iproute2": command("ip", "-V").strip()}
    # Container network-none must have loopback only before lab veth creation.
    interfaces = json.loads(command("ip", "-j", "link"))
    if any(item["ifname"] != "lo" for item in interfaces):
        raise SystemExit("Refusing to run outside a network-none disposable lab container")
    for node, index in NODES.items():
        ns = namespace(node)
        command("ip", "netns", "add", ns)
        command("ip", "link", "add", "pep" + node, "type", "veth", "peer", "name", "node" + node)
        command("ip", "link", "set", "node" + node, "netns", ns)
        command("ip", "addr", "add", f"10.77.{index}.1/24", "dev", "pep" + node)
        command("ip", "link", "set", "pep" + node, "up")
        command("ip", "-n", ns, "addr", "add", f"10.77.{index}.2/24", "dev", "node" + node)
        command("ip", "-n", ns, "link", "set", "node" + node, "up")
        command("ip", "-n", ns, "link", "set", "lo", "up")
        command("ip", "-n", ns, "route", "add", "default", "via", f"10.77.{index}.1")
    for node in ("p", "x", "m", "a"):
        processes.append(subprocess.Popen(["ip", "netns", "exec", namespace(node), sys.executable, "/lab/endpoint.py", node], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(0.3)
    enforce(())
    report["cases"]["before"] = {node: probe(node) for node in ("p", "x", "m", "a")}
    existing = subprocess.Popen(["ip", "netns", "exec", namespace("g"), sys.executable, "/lab/probe.py", "10.77.1.2", "established"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    processes.append(existing)
    if json.loads(existing.stdout.readline()) != {"ready": True}:
        raise RuntimeError("Established-session prerequisite failed")
    selected = json.loads(os.environ.get("WITHAQ_PLAN_ACTIONS", '["a","b"]'))
    if not isinstance(selected, list) or not set(selected) <= {"a", "b", "c", "d"}:
        raise RuntimeError("Unsupported deny action")
    report["applied_actions"] = selected
    enforce(selected)
    existing.stdin.write("apply\n")
    existing.stdin.flush()
    report["cases"]["established_after"] = json.loads(existing.stdout.readline())
    existing.wait(timeout=10)
    report["cases"]["mfsc_after"] = {node: probe(node) for node in ("p", "x", "m", "a")}
    report["rules"] = json.loads(command("nft", "-j", "list", "ruleset"))
    # Controller disappears: installed denies persist; no blind reopening.
    report["cases"]["controller_absent"] = {"p": probe("p"), "m": probe("m"), "a": probe("a")}
    # G has exactly one veth and no alternate route to the protected network.
    report["g_interfaces"] = json.loads(command("ip", "-n", namespace("g"), "-j", "link"))
    report["g_routes"] = json.loads(command("ip", "-n", namespace("g"), "-j", "route"))
    enforce(("c",))
    report["cases"]["full_quarantine"] = {node: probe(node) for node in ("m", "a")}
    after = report["cases"]["mfsc_after"]
    records = lambda result: result["records"]
    blocked = lambda result: all(not r["delivered"] for r in records(result))
    passes = lambda result: all(r["delivered"] and r["latency_s"] <= 2 and r["freshness_s"] <= 2 for r in records(result))
    report["checks"] = {
        "attack_paths_exist_before": all(passes(report["cases"]["before"][node]) for node in ("p", "x")),
        "relay_reaches_protected_before": all(r["protected_reached"] for r in records(report["cases"]["before"]["x"])),
        "direct_and_relay_blocked_after": blocked(after["p"]) and all(not r.get("protected_reached") for r in records(after["x"])),
        "existing_session_blocked": blocked(report["cases"]["established_after"]),
        "each_monitor_and_alert_event_under_2s": passes(after["m"]) and passes(after["a"]),
        "controller_absence_keeps_denies": blocked(report["cases"]["controller_absent"]["p"]),
        "quarantine_breaks_functions": blocked(report["cases"]["full_quarantine"]["m"]) and blocked(report["cases"]["full_quarantine"]["a"]),
        "no_alternate_client_interface": len([link for link in report["g_interfaces"] if link["ifname"] != "lo"]) == 1,
    }
    print(json.dumps(report, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
