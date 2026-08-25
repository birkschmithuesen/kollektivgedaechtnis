"""The LAN bind (spec §3.1) — the ONE thing Tool 1 changes for Tool 2.

Spec §3.1 originally claimed `server_host` had to *become* bindable. It was
already bindable; this file pins the two things that were actually missing —
that the value round-trips through `load_config`, and that what gets PRINTED
is an address the other machine can open.
"""

from __future__ import annotations

import ipaddress

from kg.__main__ import resolved_host
from kg.config import load_config


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


def test_resolved_host_handles_the_ipv6_wildcard_too():
    shown = resolved_host("::")

    assert shown != "::"
    ipaddress.IPv4Address(shown)
