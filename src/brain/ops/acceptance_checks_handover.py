"""Install acceptance checks for the handover pack: the service level statement made only on
evidence, the subprocessors a question may reach, the named owners, the booked review, and the
sentence about what the new system does not carry across.

Every check calls the route the handover is read and written through, as an administrator holding
the install authority, in the shape `brain.ops.acceptance_operations_console` sets out
(`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`), and asks the refusal beside the answer.

**The statement is proved over a listing the check holds.** The install's own copies and rehearsals
decide whether the install can yet be handed over, and a check that failed until a week of
rehearsals existed would say nothing about the product. So the check hands the route a listing it
made: copies of every coverage inside the profile's recovery point and no rehearsal, which must be
refused in words, then the same with a rehearsal that verified, which must be made. What the
install can say today is read on the Handover route itself.

**The owners and the review are written inside the check's transaction and rolled back**, with the
switch turned on through the Features route and never assumed (the plugin check's reason).

Task ids: M30.5.4, M30.6.6, M37.4.2.4, M37.4.3.3, M37.4.3.5, M37.2.4.4
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2323

A, _B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to a route's authority fails its check.
INSTALL_AUTHORITY: Final = "admin:install_setting"
SWITCHES_FEATURES: Final = "admin:feature"

THE_STATEMENT_WAS_MADE_WITH_NO_REHEARSAL: Final = (
    "a service level statement was made with no rehearsal having verified a copy"
)
THE_REFUSAL_DID_NOT_SAY_WHY: Final = "the statement was refused without saying which promise failed"
THE_STATEMENT_WAS_NOT_MADE: Final = (
    "no statement was made with every copy inside the recovery point and a rehearsal verified"
)
THE_STATEMENT_DROPPED_THE_PROFILES_FIGURES: Final = (
    "the statement did not carry the profile's recovery point and time"
)
A_PROVIDER_WAS_LEFT_OFF_THE_LIST: Final = (
    "a provider whose key this process holds was not named among the subprocessors"
)
A_PROVIDER_WAS_INVENTED: Final = "a provider was named that no key was held for"
A_CONTACTLESS_OWNER_WAS_KEPT: Final = "an owner with no way to be reached was recorded"
A_MISSING_OWNER_WAS_NOT_SAID: Final = "a responsibility with no owner was not reported as missing"
OWNERS_WERE_NOT_KEPT: Final = "three named owners were not read back as the owners"
THE_SWITCH_WAS_IGNORED: Final = "owners were recorded while recording the handover was switched off"
A_LATE_REVIEW_WAS_BOOKED: Final = "a review past thirty days, or on launch day, was booked"
A_REVIEW_WAS_NOT_KEPT: Final = "a review inside thirty days was not read back as booked"
THE_LEARNING_SENTENCE_IS_MISSING: Final = (
    "the pack did not state that the new system starts without the old one's learning"
)
THE_PACK_WAS_ANSWERED_TO_A_STRANGER: Final = (
    "a person without the install authority was shown the handover"
)


def _manifest(coverage: str, method: str, at: datetime) -> tuple[str, str]:
    name = f"{coverage}-acceptance"
    return (
        f"{name}.manifest.json",
        json.dumps(
            {
                "backup_id": name,
                "coverage": coverage,
                "method": method,
                "destination": "s3://acceptance",
                "started_at": (at - timedelta(minutes=1)).isoformat(),
                "finished_at": at.isoformat(),
                "recoverable_to": at.isoformat(),
                "size_bytes": 100,
            }
        ),
    )


def _drill(started: datetime, seconds: int) -> tuple[str, str]:
    return (
        "database-acceptance-drill-1.drill.json",
        json.dumps(
            {
                "backup_id": "database-acceptance",
                "started_at": started.isoformat(),
                "finished_at": (started + timedelta(seconds=seconds)).isoformat(),
                "into_scratch": True,
                "checks": [
                    {"check": "schema_complete", "passed": True, "detail": "all present"},
                    {"check": "smoke_query", "passed": True, "detail": "counts came back"},
                    {"check": "permission_canary", "passed": True, "detail": "stranger refused"},
                ],
            }
        ),
    )


async def _administrator(h: Harness) -> str:
    made = h.principal(A, "handover")
    await h.person(
        made,
        department=A,
        grants=(
            *screen_grants("recovery"),
            (INSTALL_AUTHORITY, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
        ),
    )
    return made


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features_declared.handover_pack import HANDOVER_PACK

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            HANDOVER_PACK.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


async def _page(h: Harness, who: str, listing: tuple[tuple[str, str], ...] | None) -> Any:
    from brain.handover_routes import handover

    console = console_for(h)
    if listing is not None:
        console.app.state.backup_objects = lambda: listing
    return await handover(console.request(), await asking_as(h, who, strong=True))


# -------------------------------- 1. the statement, only on evidence (M30.5.4, M30.6.6)
@check(
    leaves=("M30.5.4", "M30.6.6"),
    sentence=(
        "The handover's service level statement is refused in words while no rehearsal has "
        "verified a copy, and is made, with the profile's recovery point and time and the time "
        "measured, once every copy is inside the recovery point and one has."
    ),
)
async def the_statement_is_made_only_after_a_rehearsal_verified(h: Harness) -> None:
    from brain.ops.reliability import recovery_objective

    await h.found_departments()
    administrator = await _administrator(h)
    objective = recovery_objective(h.settings.profile)
    fresh = h.now - timedelta(minutes=2)
    copies = (
        _manifest("database", "full", fresh),
        _manifest("object_store", "snapshot", fresh),
        _manifest("configuration", "snapshot", fresh),
    )
    without = await _page(h, administrator, copies)
    if without.service_level is not None:
        raise CheckFailedError(THE_STATEMENT_WAS_MADE_WITH_NO_REHEARSAL)
    if "no restore has ever verified" not in without.service_level_refused:
        raise CheckFailedError(THE_REFUSAL_DID_NOT_SAY_WHY)
    drill = _drill(h.now - timedelta(hours=1), min(60, objective.rto_seconds))
    with_one = await _page(h, administrator, (*copies, drill))
    if with_one.service_level is None:
        raise CheckFailedError(THE_STATEMENT_WAS_NOT_MADE)
    made = with_one.service_level
    if (made.rpo_seconds, made.rto_seconds) != (objective.rpo_seconds, objective.rto_seconds):
        raise CheckFailedError(THE_STATEMENT_DROPPED_THE_PROFILES_FIGURES)


# -------------------------------------------------------- 2. subprocessors (M37.4.2.4)
@check(
    leaves=("M37.4.2.4",),
    sentence=(
        "The handover names as subprocessors exactly the model providers whose key this install "
        "holds, each with what it is for, and says in words when it holds none."
    ),
)
async def the_subprocessors_are_the_providers_whose_key_is_held(h: Harness) -> None:
    from brain.ops.model_service import held_providers

    await h.found_departments()
    administrator = await _administrator(h)
    page = await _page(h, administrator, None)
    held = held_providers()
    named = {one.provider for one in (page.subprocessors or [])}
    if not held <= named:
        raise CheckFailedError(A_PROVIDER_WAS_LEFT_OFF_THE_LIST)
    if named - held:
        raise CheckFailedError(A_PROVIDER_WAS_INVENTED)
    if not held and not page.subprocessors_refused:
        raise CheckFailedError(THE_REFUSAL_DID_NOT_SAY_WHY)


# ----------------- 3. owners, review and the learning sentence (M37.4.3.3, 4.3.5, 2.4.4)
@check(
    leaves=("M37.4.3.3", "M37.4.3.5", "M37.2.4.4"),
    sentence=(
        "An administrator names who owns knowledge, grants and connectors and books the review "
        "inside thirty days; a missing owner is reported, a contactless one and a late review "
        "are refused, nothing is recorded while the switch is off, and the pack states that the "
        "new system starts without the old one's learning."
    ),
)
async def owners_and_the_review_are_recorded_and_checked(h: Harness) -> None:
    from datetime import date

    from brain.handover_routes import (
        HandoverOwnerAsked,
        HandoverOwnersAsked,
        HandoverReviewAsked,
        book_review,
        save_owners,
    )
    from brain.launch import Responsibility

    await h.found_departments()
    administrator = await _administrator(h)
    stranger = h.principal(A, "stranger")
    await h.person(stranger, department=A, grants=screen_grants("recovery"))
    console = console_for(h)

    def owner(which: Responsibility, name: str, contact: str = "owner@example.invalid") -> Any:
        return HandoverOwnerAsked(responsibility=which, name=name, contact=contact)

    async def write(who: str, owners: list[Any]) -> Any:
        return await save_owners(
            console.request("PUT"),
            HandoverOwnersAsked(owners=owners),
            await asking_as(h, who, strong=True),
        )

    if not await refused(_page(h, stranger, None)):
        raise CheckFailedError(THE_PACK_WAS_ANSWERED_TO_A_STRANGER)
    await _switched(h, administrator, on=False, n=1)
    if not await refused(write(administrator, [owner(Responsibility.KNOWLEDGE, "A Person")])):
        raise CheckFailedError(THE_SWITCH_WAS_IGNORED)
    await _switched(h, administrator, on=True, n=2)
    if not await refused(write(administrator, [owner(Responsibility.KNOWLEDGE, "A", "  ")])):
        raise CheckFailedError(A_CONTACTLESS_OWNER_WAS_KEPT)
    two = await write(
        administrator,
        [owner(Responsibility.KNOWLEDGE, "A Person"), owner(Responsibility.GRANTS, "B Person")],
    )
    if not any(row.startswith("connectors:") for row in two.owner_gaps):
        raise CheckFailedError(A_MISSING_OWNER_WAS_NOT_SAID)
    three = await write(
        administrator,
        [
            owner(Responsibility.KNOWLEDGE, "A Person"),
            owner(Responsibility.GRANTS, "B Person"),
            owner(Responsibility.CONNECTORS, "C Person"),
        ],
    )
    if three.owner_gaps or len(three.owners) != 3:
        raise CheckFailedError(OWNERS_WERE_NOT_KEPT)

    launched = date(2999, 1, 1)
    for later in (launched, launched + timedelta(days=31)):
        if not await refused(
            book_review(
                console.request("PUT"),
                HandoverReviewAsked(launched_on=launched, review_booked_for=later),
                await asking_as(h, administrator, strong=True),
            )
        ):
            raise CheckFailedError(A_LATE_REVIEW_WAS_BOOKED)
    booked = await book_review(
        console.request("PUT"),
        HandoverReviewAsked(launched_on=launched, review_booked_for=launched + timedelta(days=30)),
        await asking_as(h, administrator, strong=True),
    )
    if booked.review is None or booked.review_gaps:
        raise CheckFailedError(A_REVIEW_WAS_NOT_KEPT)
    if "without" not in booked.learning.sentence:
        raise CheckFailedError(THE_LEARNING_SENTENCE_IS_MISSING)
