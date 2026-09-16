"""An application test that means "no database" has to say so, because CI's environment has one.

`brain.settings.Settings` reads `DATABASE_URL`, and CI's unit job sets it for the suites that need
a server. A test that builds `create_app(Settings(env="development"))` and then relies on there
being no session factory is therefore testing a different process in CI from the one it tests on
a laptop, and it is green where it was written. On 2026-09-17 that was three files at once: the
sessions screen found a store and answered 200 where the test expected the no-store 500, the
Staff sources screen had its held settings replaced by the database's (none) at start-up, and the
credential store came back wrapped for recording rather than as the object handed in.

The pin is `Settings(..., database_url="")`, in the test, where a reader sees it. What this module
adds is the other half: `DATABASE_URL` set to an address nothing answers, and the premise asserted
once the application has started. Drop the pin and the premise fails here, on a machine with no
server, rather than only in CI.

**Rejected: an autouse fixture that removes `DATABASE_URL` for every test.** The suites that need
CI's server read the same variable, and a fixture that could take it away from them is one wrong
scope from skipping every database test with the run still green.

Task ids: none
"""

from __future__ import annotations

from typing import Final

import pytest

#: Where nothing listens, with a timeout short enough that an unpinned start-up fails in seconds.
#: Measured on a development machine on 2026-09-17: one connection to this port took 130 seconds
#: to time out without `connect_timeout`, and a whole unpinned start-up took 2.8 seconds with it.
UNREACHABLE_DATABASE_URL: Final = (
    "postgresql://nobody:nothing@127.0.0.1:9/no_database_here?connect_timeout=1"
)


def as_if_ci_had_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set `DATABASE_URL` the way CI does, to somewhere no test may reach.

    Both names, because `Settings` prefers `BRAIN_DATABASE_URL` and a host that set it would
    otherwise decide which of the two this test ignored.
    """
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("BRAIN_DATABASE_URL", UNREACHABLE_DATABASE_URL)
