"""Install checks for two role-surface leaves no install check named: the elevation chain and a
connector's permission-sync claim.

**An elevation is written twice, and the check reads both copies as the database wrote them.**
`brain.console.elevation` argues that the separate chain is worth only its own head, and that the
head moves only when somebody is elevated. Its unit tests run over fabricated entries and
`tests/unit/test_elevation_chain.py` runs the migration's triggers over rows it inserts itself.
What neither shows is that the Elevation route, called as the product calls it, writes the
approval to `obs.elevation_entry` as well as to the main ledger, in the authoriser's name and not
the partner's, and that **a request that is only filed writes nothing to the second chain**. The
check files and approves an installing partner's request through `brain.govern_people_routes`,
inside the check's rolled-back transaction, and reads both tables for the one session it made.

**What it does not compare is the install's whole chain.** An install holds real elevations. The
check asserts about the session it made (found by its subject, which is the request's own id) and
about one property of the whole table that is the product's and not the install's: nothing but a
break-glass entry is in it. A count of the chain's length would be a count of what the install
holds.

**A permission-sync claim is the manifest's, checked against what the manifest declares.**
`brain.connectors.manifest.PermissionSync` is declared per connector and refused at review when
the declarations cannot support it, so a console never reports a source as permission-aware on
somebody's say-so. The check builds the manifest of every source the console connects from its
own example form, as `brain.ops.acceptance_checks_console_connect` does, and asks that each
claim is one `implementable_permission_sync` allows for that manifest's tools and projections, and
that the words the Connectors screen would show for it are the screen's own for that claim.

Task ids: M33.7.1.3, M33.5.1.3
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.connectors.manifest import implementable_permission_sync
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_governance_2 import _approved, _elevation_desk, _filed
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 890

A_FILED_REQUEST_MOVED_THE_SECOND_CHAIN: Final = (
    "an elevation request that was only filed was written to the elevation chain"
)
AN_APPROVAL_WAS_NOT_IN_THE_SECOND_CHAIN: Final = (
    "an approved elevation was not written to the elevation chain once, as break_glass"
)
THE_CHAIN_COULD_BE_EDITED: Final = (
    "an entry in the elevation chain could be changed or removed by the application's own role"
)
THE_ENTRY_NAMED_THE_WRONG_PEOPLE: Final = (
    "the elevation chain's entry did not name the authoriser as its actor, and the partner, the "
    "authoriser and the reason in its details"
)
AN_APPROVAL_HAD_NO_TWIN_IN_THE_MAIN_LEDGER: Final = (
    "the main ledger did not hold the same elevation as the elevation chain does"
)
AN_ORDINARY_ENTRY_WAS_IN_THE_SECOND_CHAIN: Final = (
    "the elevation chain held an entry that is not an elevation"
)

A_CLAIM_THE_DECLARATIONS_CANNOT_SUPPORT: Final = (
    "a source declared a permission-sync claim its own tools and projections cannot support"
)
A_CLAIM_WITHOUT_ITS_WORDS: Final = (
    "a source's permission-sync claim was shown in words other than the screen's own for it"
)
NO_SOURCE_WAS_ASKED: Final = "no source the console connects was asked about its permission sync"


async def _chain_rows(h: Harness, table: str, subject: str) -> list[Any]:
    """`(action, actor, details)` of this table's entries about one session."""
    found = await h.execute(
        text(
            f"SELECT action, actor_id, details FROM obs.{table} WHERE subject = :subject"  # noqa: S608
        ).bindparams(subject=subject)
    )
    return list(found.all())


async def _refused_by_the_database(h: Harness, statement: str, subject: str) -> bool:
    """Whether the database refused this statement about one session, as the application role.

    Run in the savepoint every `Harness.execute` is, so a refusal ends that statement and leaves
    the check's transaction usable. Nothing is written when it is refused, and a statement that
    was not refused is undone with the transaction.
    """
    try:
        await h.execute(text(statement).bindparams(subject=subject))
    except DBAPIError:
        return True
    return False


async def _outside(h: Harness, table: str) -> int:
    """How many entries of this table are not an elevation: the product's rule, install-wide."""
    found = await h.execute(
        text(f"SELECT count(*) FROM obs.{table} WHERE action <> 'break_glass'")  # noqa: S608
    )
    return int(found.scalar_one())


@check(
    leaves=("M33.7.1.3",),
    sentence=(
        "A filed elevation request writes nothing to the elevation chain; once approved, the chain "
        "holds one break_glass entry for it in the authoriser's name, the main ledger holds its "
        "twin, only elevations are in the chain, and the application's role cannot change or "
        "remove an entry."
    ),
)
async def an_elevation_is_written_to_its_own_chain_beside_the_main_ledger(h: Harness) -> None:
    from brain.identity.roles import BreakGlassReason

    request, partner, authoriser, _ = await _elevation_desk(h)
    request_id = await _filed(h, request, partner)
    subject = f"session:{request_id}"

    if await _chain_rows(h, "elevation_entry", subject):
        raise CheckFailedError(A_FILED_REQUEST_MOVED_THE_SECOND_CHAIN)

    decided = await _approved(h, request, request_id, authoriser)
    if decided is None:
        raise CheckFailedError("an authoriser could not approve an installing partner's request")

    elevated = await _chain_rows(h, "elevation_entry", subject)
    if len(elevated) != 1 or elevated[0][0] != "break_glass":
        raise CheckFailedError(AN_APPROVAL_WAS_NOT_IN_THE_SECOND_CHAIN)
    _, actor, details = elevated[0]
    if (
        actor != authoriser
        or details.get("principal") != partner
        or details.get("authorised_by") != authoriser
        or details.get("reason") != BreakGlassReason.INSTALL.value
    ):
        raise CheckFailedError(THE_ENTRY_NAMED_THE_WRONG_PEOPLE)

    twin = [one for one in await _chain_rows(h, "audit_entry", subject) if one[0] == "break_glass"]
    if [(one[1], dict(one[2])) for one in twin] != [(actor, dict(details))]:
        raise CheckFailedError(AN_APPROVAL_HAD_NO_TWIN_IN_THE_MAIN_LEDGER)
    if await _outside(h, "elevation_entry"):
        raise CheckFailedError(AN_ORDINARY_ENTRY_WAS_IN_THE_SECOND_CHAIN)
    for statement in (
        "UPDATE obs.elevation_entry SET actor_id = actor_id WHERE subject = :subject",
        "DELETE FROM obs.elevation_entry WHERE subject = :subject",
    ):
        if await _refused_by_the_database(h, statement, subject):
            continue
        raise CheckFailedError(THE_CHAIN_COULD_BE_EDITED)


@check(
    leaves=("M33.5.1.3",),
    sentence=(
        "Every source the Connectors screen connects declares, in its manifest built from its own "
        "form, a permission-sync claim that its tools and projections support, and the screen "
        "says the claim in its own words for it."
    ),
)
async def every_connectors_permission_sync_claim_is_one_it_can_support(h: Harness) -> None:
    from brain.console.connector_trust import PERMISSION_SYNC_SAYS
    from brain.ops.acceptance_checks_connector_framework import _form
    from brain.ops.connectable import CONNECTABLE, given, key_reference

    asked = 0
    for name, kind in CONNECTABLE.items():
        # A setting naming a person is built with any name: building a manifest asks nothing of
        # the directory, which the connect route does separately.
        people = {one.name: "acceptance" for one in kind.settings if one.names_a_person}
        manifest = kind.build(given(kind, {**_form(name), **people}), key_reference(name))
        if manifest.permission_sync not in implementable_permission_sync(
            manifest.tools, manifest.projections
        ):
            raise CheckFailedError(A_CLAIM_THE_DECLARATIONS_CANNOT_SUPPORT)
        if not PERMISSION_SYNC_SAYS[manifest.permission_sync].strip():
            raise CheckFailedError(A_CLAIM_WITHOUT_ITS_WORDS)
        asked += 1
    if not asked:
        raise CheckFailedError(NO_SOURCE_WAS_ASKED)
