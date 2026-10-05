"""What a cassette file needs to drive a recording through its connector's read-back reading.

Each source's file carries how every recording its read-back names is answered, and the driver
that answers it in the connector's own reply value (`CassetteFile.read_back`). Until 2026-10-05
both were one table and one `match` in `tests/unit/test_write_verification.py`, which every
connector PR appended to. Underscored, so `tests.fixtures.cassettes` does not read it as a source.

Task ids: M11.1.6
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from brain.connectors.declaration import read_backs
from brain.connectors.write_verification import verdict
from brain.ops.idempotency import Verification

#: A read time pinned far outside any plausible wall clock: nothing here is about the present.
READ_AT: Final = "2019-01-01T00:00:00+00:00"


class PublicResolver:
    """Every name answers with one public address. Nothing is fetched by anything here."""

    def resolve(self, host: str) -> list[str]:
        del host
        return ["93.184.216.34"]


def reading_of(source: str) -> Callable[..., Any]:
    """The read-back reading a connector's own declaration names, refusing one that has none."""
    found = read_backs()[source].reading
    assert found is not None, f"{source} has no read-back reading to drive"
    return found


def answered(source: str, *reply: Any, **named: Any) -> Verification:
    """The verdict `source`'s read-back reading gives on this reply."""
    return verdict(reading_of(source)(*reply, **named))
