"""Spec §3's import boundary: Tool 2 must never import `kg.store`, `kg.core`
or `kg.server` (Finding 4).

`kg2/__main__.py` used to do `from kg.__main__ import resolved_host`, which
transitively imports all three of those modules (plus PIL, for portraits) even
though no DB is opened and no server started on that path. No live fault
followed from it today, but it made the spec's guarantee read stronger than it
actually was enforced in code — this is the test that guarantee never had.

Must run in a subprocess: several other modules in this test suite (e.g.
test_dream_contract.py) import `kg.store` directly, and pytest imports every
test module during collection regardless of run order. By the time any test
BODY runs, `sys.modules` may already contain `kg.store` for reasons that have
nothing to do with `kg2.__main__` — so an in-process check here would prove
nothing either way. A fresh subprocess is the only way to observe what
`import kg2.__main__` alone pulls in.
"""

from __future__ import annotations

import subprocess
import sys


def test_importing_kg2_main_does_not_pull_in_kg_store_core_or_server():
    probe = (
        "import kg2.__main__\n"
        "import sys\n"
        "forbidden = [m for m in ('kg.store', 'kg.core', 'kg.server') if m in sys.modules]\n"
        "assert not forbidden, forbidden\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
