"""Install check for a registration number as a join key: one spelling joins, a mistyped one not.

`brain.resolution.cascade.usable_identifiers` is the one place an identifier value becomes a
digest, and a UEN is the key stage one of the cascade merges on alone.
`brain.resolution.normalise.check_uen` says what a UEN is and how it is spelled, and until it was
called from that place a registration number mistyped on one record joined the record that carried
the same mistake, and one written in lower case never joined the same number in capitals. The unit
tests run over a pepper and a string. What they cannot show is the registry's own run over records
written the way a sync leaves them, through the install's real tables.

**The source is the check's own, said so.** No shipped connector keeps a registration number in its
projection (`brain.ops.acceptance_checks_matching` says why), so the check declares a company
source that does, for the check only, as that module does; the registry and the matching it runs
are the product's. The pass is therefore about the install's code reading a number, and not about
any company's records.

**Unattended merging stays off, and the check reads what that holds.** Two records sharing a valid
registration number are put to a person at stage one (`HELD_UNATTENDED`), which is what the cascade
does with a hard match while the owner has not switched unattended merging on (item 155). That is
the observable that two spellings were one key; the digests themselves are never read, because
each is made with a pepper the check mints.

Task ids: M14.2.6
"""

from __future__ import annotations

import secrets
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_matching import REGISTERED, _items, _matched
from brain.ops.acceptance_run import Harness
from brain.resolution.matching_store import HELD_UNATTENDED

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 815

TWO_SPELLINGS_DID_NOT_JOIN: Final = (
    "one registration number written in capitals and in lower case did not join at stage one"
)
THE_SPELLINGS_WERE_TWO_KEYS: Final = (
    "one registration number written two ways was kept as more than one join key"
)
A_MISTYPED_NUMBER_WAS_KEPT: Final = (
    "a value that is not a registration number was kept as a join key"
)
A_MISTYPED_NUMBER_JOINED: Final = "two records carrying one mistyped number were joined by it"


@check(
    leaves=("M14.2.6",),
    sentence=(
        "With a company source declared for the check, two records whose registration number is "
        "one number in capitals and in lower case are one join key and are put to a person at "
        "stage one; two records carrying one number that is not a registration number are given "
        "no join key and are not joined."
    ),
)
async def a_uen_joins_in_one_spelling_and_a_mistyped_one_does_not(
    h: Harness,
) -> None:
    pepper = secrets.token_hex(32)
    word = h.word()

    valid = await _matched(
        h,
        (REGISTERED, {"name": f"{word} Alpha Labs", "uen": "201900001K"}),
        (REGISTERED, {"name": f"Wholly Different {word} Freight", "uen": " 201900001k "}),
        extra=True,
        pepper=pepper,
    )
    found = await _items(h, valid)
    if [(row[3], row[4]) for row in found] != [(1, HELD_UNATTENDED)]:
        raise CheckFailedError(TWO_SPELLINGS_DID_NOT_JOIN)
    keys = await _identifiers(h, valid)
    if len(keys) != 2 or len(set(keys)) != 1:
        raise CheckFailedError(THE_SPELLINGS_WERE_TWO_KEYS)

    mistyped = await _matched(
        h,
        (REGISTERED, {"name": f"{word} Beta Studio", "uen": "2019-00002K"}),
        (REGISTERED, {"name": f"Entirely Other {word} Logistics", "uen": "2019-00002K"}),
        extra=True,
        pepper=pepper,
    )
    if await _identifiers(h, mistyped):
        raise CheckFailedError(A_MISTYPED_NUMBER_WAS_KEPT)
    if await _items(h, mistyped):
        raise CheckFailedError(A_MISTYPED_NUMBER_JOINED)


async def _identifiers(h: Harness, refs: tuple[object, ...]) -> list[str]:
    """The digests the registry kept as a registration number's key for these records."""
    ids = [getattr(one, "source_id", "") for one in refs]
    found = await h.execute(
        text(
            "SELECT key_hash FROM er.identifier WHERE kind = 'uen' AND source_id = ANY(:ids)"
        ).bindparams(ids=ids)
    )
    return [str(one) for one in found.scalars()]
