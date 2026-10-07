"""Install checks for the elevation chain: an elevation is its own chain, and it is told in the main.

Approving an installing partner's elevation writes a break-glass entry, and since `0209` it writes
two: one in the main audit ledger, where every other act is, and one in `obs.elevation_entry`, a
chain of elevations alone whose head moves only when somebody is elevated
(`brain.console.elevation.A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER`). The unit
tests run the two chains' rules over lists. What they cannot show is that, on an install, an
approval made through the Elevation route lands once in each chain, that the elevation chain holds
nothing but elevations, and that it still walks as one unbroken chain with the check the worker
runs on a schedule.

**The elevation chain is walked in full and the main ledger is not.** The elevation chain holds
one entry per elevation and a check can walk it in a moment, in SQL. The main ledger holds every audited act
the install has ever made, and walking it is the worker's own scheduled control
(`brain.audit.chain_check`), which has no business inside a check with a two-minute bound. What the
check asks of the main ledger is the twin of the entry: that the approval is in it.

**The partner is a reserved principal and the elevation is the check's own**, in the
check's rolled-back transaction, through the routes of `brain.ops.acceptance_checks_governance_2`:
the partner files, the authoriser approves, and the chain is read afterwards.

Task ids: M33.7.1.3
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_governance_2 import _approved, _elevation_desk, _filed
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 855

NOT_IN_THE_ELEVATION_CHAIN: Final = (
    "an approved elevation was not written once to the elevation chain"
)
NOT_IN_THE_MAIN_LEDGER: Final = (
    "an approved elevation was not written once to the main ledger as well"
)
SOMETHING_ELSE_IN_IT: Final = "the elevation chain held an entry that is not an elevation"
THE_CHAIN_BROKE: Final = "the elevation chain did not walk as one unbroken chain"
THE_TWINS_DIFFER: Final = "an elevation's two entries did not say the same thing"


#: The walk, in SQL: every entry's digest is the database's own digest of what it holds, its
#: parent is the entry before it, and the first has the genesis parent. Written out and not left to
#: `brain.audit.chain_check.check_ledger`, because that walk rebuilds each entry through the
#: ledger's own type, which refuses a name carrying a dot, and every reserved principal's id has
#: three. The digest function is `0003`'s, the one the chain's trigger writes the digest with.
WALK_THE_ELEVATION_CHAIN: Final = """
SELECT count(*) FROM obs.elevation_entry e
LEFT JOIN obs.elevation_entry p ON p.seq = e.seq - 1
WHERE e.entry_hash <> obs.audit_entry_hash(
        e.seq, e.at, e.actor_id, e.action, e.subject, e.ent_hash, e.trace_id, e.details,
        e.prev_hash)
   OR (e.seq = 0 AND e.prev_hash <> repeat('0', 64))
   OR (e.seq > 0 AND (p.seq IS NULL OR p.entry_hash <> e.prev_hash))
"""


async def _entries(h: Harness, table: str, subject: str) -> list[tuple[str, str, str]]:
    """Every entry about this session in one chain: its action, its actor and its details."""
    # The table is one of this module's two literals, never input.
    found = await h.execute(
        text(
            f"SELECT action, actor_id, details::text FROM {table} WHERE subject = :subject"  # noqa: S608
        ).bindparams(subject=subject)
    )
    return [(str(a), str(b), str(c)) for a, b, c in found.all()]


@check(
    leaves=("M33.7.1.3",),
    sentence=(
        "An installing partner's elevation, approved through the Elevation route, is written once "
        "to the elevation chain and once to the main ledger, each as the authoriser's act with "
        "the same details; the elevation chain holds nothing but break-glass entries and walks "
        "as one unbroken chain."
    ),
)
async def an_approved_elevation_is_in_its_own_chain_and_the_main_ledger(h: Harness) -> None:
    request, partner, authoriser, _ = await _elevation_desk(h)
    request_id = await _filed(h, request, partner)
    if await _approved(h, request, request_id, authoriser) is None:
        raise CheckFailedError("an authoriser could not approve an installing partner's request")
    subject = f"session:{request_id}"

    second = await _entries(h, "obs.elevation_entry", subject)
    main = await _entries(h, "obs.audit_entry", subject)
    if len(second) != 1 or second[0][:2] != ("break_glass", authoriser):
        raise CheckFailedError(NOT_IN_THE_ELEVATION_CHAIN)
    if len(main) != 1 or main[0][:2] != ("break_glass", authoriser):
        raise CheckFailedError(NOT_IN_THE_MAIN_LEDGER)
    if second[0][2] != main[0][2]:
        raise CheckFailedError(THE_TWINS_DIFFER)

    others = (
        await h.execute(
            text("SELECT count(*) FROM obs.elevation_entry WHERE action <> 'break_glass'")
        )
    ).scalar_one()
    if others:
        raise CheckFailedError(SOMETHING_ELSE_IN_IT)
    broken = (await h.execute(text(WALK_THE_ELEVATION_CHAIN))).scalar_one()
    walked = (await h.execute(text("SELECT count(*) FROM obs.elevation_entry"))).scalar_one()
    if broken or walked < 1:
        raise CheckFailedError(THE_CHAIN_BROKE)
