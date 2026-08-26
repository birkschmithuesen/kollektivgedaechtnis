"""The only thing Tool 2 ever says to Tool 1, and it is a question.

Read-only by construction (spec §2): this module has no POST, no PUT, no PATCH
and no DELETE, and `tests/test_dream_contract.py` asserts on the source that it
never grows one. Tool 1 must keep working when Tool 2 is broken, and the
cheapest way to guarantee that is to have no way to write at all.

Polling a complete-state endpoint, not subscribing to `/events` (spec §4.1):
it survives a Tool 1 restart with no reconnect logic, it is the pattern CR-1
already chose, and at a 240 s floor a 5 s detection lag is invisible.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# The keys that make a payload Tool 1's state rather than an error page, a
# proxy's JSON or half a file. Checked before the payload is handed on, because
# a caller that gets `{"error": ...}` here would read `graph["nodes"]` and
# crash the watcher loop.
_REQUIRED_KEYS = frozenset({"version", "nodes", "edges"})


def _httpx_get(url: str, timeout: float) -> dict:
    import httpx

    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_graph(url: str, timeout: float = 10.0, get=_httpx_get) -> dict | None:
    """Tool 1's complete state, or None. NEVER raises.

    `get` is injectable so no test ever touches the network.

    Every failure — refused connection, DNS, timeout, 500, truncated body, an
    HTML error page — collapses to None, and the caller does nothing. That is
    spec §8's „poll keeps failing quietly": nothing new was said, so no new
    dream is correct behaviour, and the display is untouched either way.
    """
    try:
        payload = get(url, timeout)
    except Exception as exc:  # network, HTTP status, JSON — all the same to us
        log.debug("graph fetch failed: %s", exc)
        return None
    if not isinstance(payload, dict) or not _REQUIRED_KEYS <= set(payload):
        log.warning("graph fetch returned something that is not a graph: %r", type(payload))
        return None
    return payload
