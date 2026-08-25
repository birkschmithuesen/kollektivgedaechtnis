"""The LAN bind (spec §3.1) — the ONE thing Tool 1 changes for Tool 2.

Spec §3.1 originally claimed `server_host` had to *become* bindable. It was
already bindable; this file pins the two things that were actually missing —
that the value round-trips through `load_config`, and that what gets PRINTED
is an address the other machine can open.
"""

from __future__ import annotations

import ipaddress
import socket
import subprocess

from kg.__main__ import resolved_host
from kg.config import load_config


def _probe_default_route_ipv4():
    """Mirror `resolved_host`'s own route probe, so a test can know ahead of
    time whether this machine even has a default route to find. On a
    routeless CI box the probe raises here too, and the caller skips instead
    of asserting something the network cannot provide."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


class _RoutelessSocket:
    """Stand-in for `socket.socket` that fails exactly like a machine with no
    default route: `connect()` raises OSError. Used to force `resolved_host`
    past its first probe without depending on the test host's own routing
    table."""

    def __init__(self, *args, **kwargs):
        pass

    def connect(self, *args, **kwargs):
        raise OSError("no route to host (simulated)")

    def close(self):
        pass


def test_server_host_round_trips_through_load_config(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\nserver_host = "0.0.0.0"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.server_host == "0.0.0.0"


def test_the_documented_default_is_still_localhost(tmp_path):
    """Spec §3.1: the documented default stays 127.0.0.1; the exhibition value
    goes into config.toml on site, so a developer machine is never exposed by
    merely checking the repo out."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    assert load_config(cfg_file).server_host == "127.0.0.1"


def test_resolved_host_leaves_a_literal_host_alone():
    assert resolved_host("127.0.0.1") == "127.0.0.1"
    assert resolved_host("192.168.1.23") == "192.168.1.23"
    assert resolved_host("dream.local") == "dream.local"


def test_resolved_host_replaces_the_wildcard_with_a_routable_address():
    """`http://0.0.0.0:8800/graph.json` is not openable from the dream machine.
    Whatever comes back must be a real IPv4 address, never the wildcard."""
    shown = resolved_host("0.0.0.0")

    assert shown != "0.0.0.0"
    ipaddress.IPv4Address(shown)  # raises if it is not an address at all

    # A "not 0.0.0.0, parses as IPv4" assertion alone would also pass for a
    # regression that unconditionally returns 127.0.0.1 without consulting
    # the routing table at all. On a machine that actually has a default
    # route (true on any normal dev box and most CI runners), demand more:
    # the result must be a real LAN address, not loopback in disguise.
    if _probe_default_route_ipv4() is not None:
        assert not ipaddress.IPv4Address(shown).is_loopback


def test_resolved_host_handles_the_ipv6_wildcard_too():
    shown = resolved_host("::")

    assert shown != "::"
    ipaddress.IPv4Address(shown)

    if _probe_default_route_ipv4() is not None:
        assert not ipaddress.IPv4Address(shown).is_loopback


def _fake_run_ip_command_unavailable(cmd, **kwargs):
    """Stand-in for `subprocess.run` that fails exactly like a machine with
    no `ip` binary on PATH, so tests can force `resolved_host` past its
    `ip`-enumeration step without depending on the test host's own
    interfaces."""
    raise FileNotFoundError("no such file or directory: 'ip' (simulated)")


def test_resolved_host_uses_ip_command_when_route_probe_fails(monkeypatch):
    """The middle attempt (spec: `ip -4 -o addr show scope global`) is what
    actually covers a gateway-less exhibition LAN on Linux. Inject at the
    subprocess seam `_first_global_ipv4_via_ip_command` calls — not by
    mocking the function under test — so this exercises the real parsing of
    `ip`'s output."""
    monkeypatch.setattr(socket, "socket", _RoutelessSocket)
    # If the ip step is skipped or broken, the hostname fallback would need
    # to supply the answer instead; make it fail so only the ip step can
    # produce a result, proving this test actually exercises that step.
    monkeypatch.setattr(
        socket,
        "gethostbyname_ex",
        lambda name: (_ for _ in ()).throw(OSError("unknown host (simulated)")),
    )

    fake_stdout = (
        "2: eth0    inet 192.168.7.50/24 brd 192.168.7.255 scope global "
        "eth0\\       valid_lft forever preferred_lft forever\n"
    )

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["ip", "-4"]
        return subprocess.CompletedProcess(cmd, 0, stdout=fake_stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert resolved_host("0.0.0.0") == "192.168.7.50"


def test_resolved_host_falls_back_to_the_hostname_address_when_ip_command_is_unavailable(
    monkeypatch,
):
    """An isolated exhibition LAN (spec §3.1) can be a direct cable or a
    switch with static IPs and no configured gateway: a real, reachable
    machine that nonetheless has no default route to probe. Even if the `ip`
    binary itself is missing, `resolved_host` must not collapse straight to
    localhost there — it has a third chance via the machine's own
    hostname."""
    monkeypatch.setattr(socket, "socket", _RoutelessSocket)
    monkeypatch.setattr(subprocess, "run", _fake_run_ip_command_unavailable)
    monkeypatch.setattr(
        socket, "gethostbyname_ex", lambda name: (name, [], ["203.0.113.9"])
    )

    assert resolved_host("0.0.0.0") == "203.0.113.9"


def test_resolved_host_gives_up_to_localhost_only_when_all_three_attempts_fail(monkeypatch):
    """Only when the route probe fails AND the `ip` command finds nothing
    usable AND the hostname resolves to nothing usable (or nothing at all)
    is 127.0.0.1 the honest answer."""
    monkeypatch.setattr(socket, "socket", _RoutelessSocket)
    monkeypatch.setattr(subprocess, "run", _fake_run_ip_command_unavailable)
    monkeypatch.setattr(
        socket,
        "gethostbyname_ex",
        lambda name: (_ for _ in ()).throw(OSError("unknown host (simulated)")),
    )

    assert resolved_host("0.0.0.0") == "127.0.0.1"


def test_resolved_host_gives_up_to_localhost_on_the_real_debian_127_0_1_1_case(monkeypatch):
    """Pins the real failure this fix was written for, reproduced empirically
    on a Debian-family exhibition-adjacent host: no default route, no usable
    `ip` output, and `/etc/hosts`'s stock `127.0.1.1 <hostname>` line means
    `gethostbyname_ex` resolves to loopback only — even though the machine
    may well have a perfectly good static LAN address configured on eth0.
    That gap is exactly why the `ip`-enumeration step has to exist; this
    test documents the case where it, too, comes up empty and 127.0.0.1 is
    the honest — not silently wrong — answer."""
    monkeypatch.setattr(socket, "socket", _RoutelessSocket)
    monkeypatch.setattr(subprocess, "run", _fake_run_ip_command_unavailable)
    monkeypatch.setattr(
        socket,
        "gethostbyname_ex",
        lambda name: ("ubuntu-2gb-nbg1-1", ["ubuntu-2gb-nbg1-1"], ["127.0.1.1"]),
    )

    assert resolved_host("0.0.0.0") == "127.0.0.1"


def test_resolved_host_survives_a_hanging_or_failing_ip_command(monkeypatch):
    """A wedged `ip` binary must not be able to stall or crash the
    unattended startup path. Simulates the timeout `subprocess.run(...,
    timeout=2)` raises when the child does not return in time."""
    monkeypatch.setattr(socket, "socket", _RoutelessSocket)

    def fake_run_that_hangs(cmd, **kwargs):
        assert kwargs.get("timeout"), "the ip subprocess call must set a timeout"
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run_that_hangs)
    monkeypatch.setattr(
        socket,
        "gethostbyname_ex",
        lambda name: (_ for _ in ()).throw(OSError("unknown host (simulated)")),
    )

    assert resolved_host("0.0.0.0") == "127.0.0.1"
