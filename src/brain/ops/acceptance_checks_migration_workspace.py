"""Install checks for running a migration from another system: the register is kept and what is
outstanding in it is said, the comparison period's criteria are held to being agreed first, and a
cutover cannot be reported complete while an act with a security consequence is unrecorded.

Every check calls the route the console calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`): an
application holding the check's sessions, and the asking the gate would hand the route for a
reserved administrator on the console, with a second factor.

**The old system is made up for the check, and nothing is reached.** The register describes two
things "a made-up system" holds, the period asks two made-up questions and the cutover names a
made-up connector, so no value of anybody's is read and nothing is sent. What is proved is the
install's half: the table `0241` built accepts the documents, the package's refusals are said in the
route's words, the gaps are computed from what was saved, and the completion gate holds with a real
database under it. Nothing here proves a person did what a record says they did, and
`brain.migration.decommission` is explicit that nothing can.

**The switch is set in both directions and never assumed.** An install that already has
`migration_workspace` on is not the empty state, so the check turns it off through the Features
route, shows a save refused, and turns it on.

**Not claimed:** the exporter, the re-parse and the old system's side of the comparison (M37.1.2,
M37.1.3.1), the skill and memory conversions (M37.2), and the rehearsal of the whole migration
(M37.7.6).

Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3, M37.1.3.2, M37.1.3.3, M37.1.4.1, M37.1.4.2, M37.1.4.3,
M37.1.4.4, M37.7.5
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from sqlalchemy import text

from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2250

A, _B = RESERVED_DEPARTMENTS

#: The authorities the check's administrator holds. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
RUNS_A_MIGRATION: Final = "admin:install_setting"
SWITCHES_FEATURES: Final = "admin:feature"

#: The five acts with a security consequence, by leaf. Restated so a change to the gate fails here.
THE_GATED_ACTS: Final = (
    "M37.2.5.4",
    "M37.2.6.1",
    "M37.2.6.2",
    "M37.2.6.5",
    "M37.4.1.3",
    "M37.6.1.1",
    "M37.6.1.2",
)

SHOWN_TO_ANYBODY: Final = "a person without the authority to run a migration was shown it"
SAVED_WITH_THE_SWITCH_OFF: Final = "a migration document was saved while keeping one was off"
A_HALF_REGISTER_WAS_AGREED: Final = "a register with an item nothing decided was called agreed"
THE_UNDECIDED_ITEM_WAS_NOT_NAMED: Final = "an item nothing decided was not named as outstanding"
THE_UNMAPPED_PERMISSION_WAS_NOT_NAMED: Final = "an unmapped permission was not named as outstanding"
A_PROMPT_WAS_CARRIED_ACROSS: Final = "a prompt decided to migrate was not named as uncarriable"
A_FINISHED_REGISTER_WAS_NOT_AGREED: Final = "a register that was finished was not called agreed"
A_VERSION_WAS_LOST: Final = "an earlier version of a document was not kept when a later was saved"
A_LATE_CRITERION_WAS_SAVED: Final = "a threshold agreed after the period began was saved"
A_DISAGREEMENT_WAS_NOT_SURFACED: Final = "a question the two systems differed on was not surfaced"
A_CUTOVER_WAS_ALLOWED_TO_UNREAD: Final = (
    "a period with a disagreement nobody read allowed a cutover"
)
A_READ_PERIOD_WAS_NOT_ALLOWED: Final = "a period that met every criterion did not allow a cutover"
AN_ARCHIVE_PRECEDED_READ_ONLY: Final = "an archive taken before the system was read-only was saved"
READ_ONLY_PRECEDED_CUTOVER: Final = "the system was made read-only before the cutover and saved"
A_GAP_WAS_NOT_NAMED: Final = "a cutover record lacking a revocation, a job or a backup was silent"
A_COMPLETION_WAS_ALLOWED: Final = "a cutover was reported complete with a gated act unrecorded"
THE_REFUSAL_DID_NOT_NAME_AN_ACT: Final = (
    "the refusal of a completion did not name each unrecorded act"
)
A_COMPLETION_WAS_REFUSED: Final = "a cutover with every gated act recorded was refused"
A_COMPLETION_WAS_NOT_KEPT: Final = "a reported completion was not read back with who reported it"
A_COMPLETION_SURVIVED_AN_EDIT: Final = "a cutover edited after it was reported still read complete"


async def _administrator(h: Harness) -> str:
    made = h.principal(A, "migration")
    await h.person(
        made,
        department=A,
        grants=(
            (RUNS_A_MIGRATION, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
        ),
    )
    return made


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    """The workspace switch, through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features import MIGRATION_WORKSPACE

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            MIGRATION_WORKSPACE.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


class _Routes:
    """The migration routes, each asked as one reserved person on the console."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.console = console_for(h)

    async def page(self, who: str) -> Any:
        from brain.migration_routes import workspace

        return await workspace(self.console.request(), await asking_as(self.h, who, strong=True))

    async def register(self, who: str, document: dict[str, Any]) -> Any:
        from brain.migration_routes import RegisterAsked, save_register

        return await save_register(
            self.console.request("PUT"),
            RegisterAsked.model_validate(document),
            await asking_as(self.h, who, strong=True),
        )

    async def period(self, who: str, document: dict[str, Any]) -> Any:
        from brain.migration_routes import ParallelAsked, save_parallel

        return await save_parallel(
            self.console.request("PUT"),
            ParallelAsked.model_validate(document),
            await asking_as(self.h, who, strong=True),
        )

    async def cutover(self, who: str, document: dict[str, Any]) -> Any:
        from brain.migration_routes import CutoverAsked, save_cutover

        return await save_cutover(
            self.console.request("PUT"),
            CutoverAsked.model_validate(document),
            await asking_as(self.h, who, strong=True),
        )

    async def report_complete(self, who: str) -> Any:
        from brain.migration_routes import report_cutover_complete

        return await report_cutover_complete(
            self.console.request("POST"), await asking_as(self.h, who, strong=True)
        )


async def _versions(h: Harness, kind: str) -> int:
    return int(
        (
            await h.execute(
                text("SELECT count(*) FROM ops.migration_record WHERE kind = :kind").bindparams(
                    kind=kind
                )
            )
        ).scalar_one()
    )


async def _refusal_words(call: Any) -> str | None:
    """What a route refused with, in its own words, or None when it answered."""
    try:
        await call
    except Absent as refusal:
        return str(refusal.public_message)
    return None


# ---------------------------------------- 1. the register (M37.1.1.1, M37.1.1.2, M37.1.1.3)
def _register(**more: Any) -> dict[str, Any]:
    """What a made-up old system holds: a document and a prompt, and one permission."""
    return {
        "surveyed": ["knowledge", "prompt", "tool", "conversation"],
        "items": [
            {
                "item_id": "doc_1",
                "holding": "knowledge",
                "name": "A made-up price list",
                "permissions": ["view_prices"],
            },
            {"item_id": "prompt_1", "holding": "prompt", "name": "A made-up quote prompt"},
        ],
        "decisions": [
            {
                "item_id": "doc_1",
                "disposition": "migrate",
                "because": "It is the company's own data and reads the same here",
            }
        ],
        "mappings": [],
        **more,
    }


@check(
    leaves=("M37.1.1.1", "M37.1.1.2", "M37.1.1.3"),
    sentence=(
        "An administrator saves the register of a made-up old system with the switch off and on: "
        "an item nothing decided and a permission nothing maps are named as outstanding and the "
        "register is not agreed, a prompt decided to migrate is named as uncarriable, and a "
        "finished register is agreed, with every earlier version kept."
    ),
)
async def a_register_is_kept_and_what_is_outstanding_in_it_is_said(h: Harness) -> None:
    await h.found_departments()
    admin, other = await _administrator(h), h.principal(A, "other")
    await h.person(other, department=A)
    routes = _Routes(h)
    if not await refused(routes.page(other)):
        raise CheckFailedError(SHOWN_TO_ANYBODY)

    await _switched(h, admin, on=False, n=1)
    if not await refused(routes.register(admin, _register())):
        raise CheckFailedError(SAVED_WITH_THE_SWITCH_OFF)
    await _switched(h, admin, on=True, n=2)
    before = await _versions(h, "register")

    half = await routes.register(admin, _register())
    if half.agreed:
        raise CheckFailedError(A_HALF_REGISTER_WAS_AGREED)
    said = "\n".join(half.gaps)
    if "prompt_1" not in said:
        raise CheckFailedError(THE_UNDECIDED_ITEM_WAS_NOT_NAMED)
    if "view_prices" not in said:
        raise CheckFailedError(THE_UNMAPPED_PERMISSION_WAS_NOT_NAMED)

    carried = _register()
    carried["decisions"].append(
        {"item_id": "prompt_1", "disposition": "migrate", "because": "It worked there"}
    )
    carried["mappings"] = [
        {
            "old": "view_prices",
            "capabilities": ["read:price.list"],
            "because": "Reading a list there is reading it here",
        }
    ]
    if "prompt_1" not in "\n".join((await routes.register(admin, carried)).gaps):
        raise CheckFailedError(A_PROMPT_WAS_CARRIED_ACROSS)

    done = _register()
    done["decisions"].append(
        {
            "item_id": "prompt_1",
            "disposition": "rebuild",
            "because": "It was written for a system that narrowed nothing",
        }
    )
    done["mappings"] = carried["mappings"]
    finished = await routes.register(admin, done)
    if not finished.agreed or finished.gaps:
        raise CheckFailedError(A_FINISHED_REGISTER_WAS_NOT_AGREED)
    if await _versions(h, "register") != before + 3:
        raise CheckFailedError(A_VERSION_WAS_LOST)


# ---- 2. the comparison period (M37.1.3.2, M37.1.3.3)
@check(
    leaves=("M37.1.3.2", "M37.1.3.3"),
    sentence=(
        "A comparison period whose threshold was agreed after it began is refused; one agreed "
        "before is saved, the question the two systems differed on is surfaced as unreviewed and a "
        "cutover is not allowed, and once somebody has read it and every measure has a threshold "
        "that is met the cutover is allowed."
    ),
)
async def a_period_keeps_criteria_agreed_first_and_surfaces_disagreements(
    h: Harness,
) -> None:
    await h.found_departments()
    admin = await _administrator(h)
    routes = _Routes(h)
    await _switched(h, admin, on=True, n=3)
    began = h.now - timedelta(days=10)
    ends = h.now + timedelta(days=20)
    agreed = h.now - timedelta(days=40)

    def criteria(when: Any) -> list[dict[str, Any]]:
        return [
            {
                "measure": "questions asked",
                "direction": "at least",
                "threshold": 2,
                "agreed_at": when.isoformat(),
                "because": "Enough to be a sample of what people ask",
            },
            {
                "measure": "days running",
                "direction": "at least",
                "threshold": 5,
                "agreed_at": when.isoformat(),
                "because": "Long enough to see a weekday and a weekend",
            },
            {
                "measure": "unreviewed disagreements",
                "direction": "at most",
                "threshold": 0,
                "agreed_at": when.isoformat(),
                "because": "Every disagreement is read before the switch",
            },
        ]

    def period(when: Any, *, reviewed: str = "") -> dict[str, Any]:
        return {
            "started_at": began.isoformat(),
            "ends_at": ends.isoformat(),
            "criteria": criteria(when),
            "comparisons": [
                {"question": "q_agree", "asked_at": began.isoformat(), "verdict": "agreed"},
                {
                    "question": "q_differ",
                    "asked_at": began.isoformat(),
                    "verdict": "differed",
                    "reviewed_by": reviewed,
                },
            ],
        }

    if not await refused(routes.period(admin, period(began + timedelta(days=1)))):
        raise CheckFailedError(A_LATE_CRITERION_WAS_SAVED)
    open_period = await routes.period(admin, period(agreed))
    if open_period.disagreements != ["q_differ"] or open_period.unreviewed != ["q_differ"]:
        raise CheckFailedError(A_DISAGREEMENT_WAS_NOT_SURFACED)
    if open_period.may_cut_over:
        raise CheckFailedError(A_CUTOVER_WAS_ALLOWED_TO_UNREAD)
    read = await routes.period(admin, period(agreed, reviewed=admin))
    if read.unreviewed or not read.may_cut_over or read.gaps:
        raise CheckFailedError(A_READ_PERIOD_WAS_NOT_ALLOWED)


# ------------------------------------------ 3. the cutover (M37.1.4.1 to M37.1.4.4, M37.7.5)
@check(
    leaves=("M37.1.4.1", "M37.1.4.2", "M37.1.4.3", "M37.1.4.4", "M37.7.5"),
    sentence=(
        "A cutover made read-only before it happened, or archived before it was read-only, is "
        "refused; a record with an unconfirmed revocation, an unwatched job and an unverified "
        "backup names each; reporting it complete is refused naming every unrecorded gated act, "
        "allowed once each is recorded, and an edit afterwards is no longer reported complete."
    ),
)
async def a_cutover_is_not_complete_while_a_gated_act_is_unrecorded(h: Harness) -> None:
    await h.found_departments()
    admin = await _administrator(h)
    routes = _Routes(h)
    await _switched(h, admin, on=True, n=4)
    cut = h.now - timedelta(days=3)
    after = h.now - timedelta(days=2)
    later = h.now - timedelta(days=1)

    def at(when: Any) -> str:
        return str(when.isoformat())

    if not await refused(
        routes.cutover(admin, {"cut_over_at": at(cut), "read_only_at": at(cut - timedelta(days=1))})
    ):
        raise CheckFailedError(READ_ONLY_PRECEDED_CUTOVER)
    if not await refused(routes.cutover(admin, {"cut_over_at": at(cut), "archived_at": at(after)})):
        raise CheckFailedError(AN_ARCHIVE_PRECEDED_READ_ONLY)

    open_record = {
        "cut_over_at": at(cut),
        "read_only_at": at(after),
        "archived_at": at(later),
        "revocations": [{"connector": "a_made_up_connector", "requested_at": at(after)}],
        "jobs": [{"name": "a_made_up_nightly_job", "disabled_at": at(after)}],
        "final_backup": {"backup_id": "made_up_backup", "taken_at": at(after)},
    }
    view = await routes.cutover(admin, open_record)
    said = "\n".join(view.gaps)
    if not all(
        word in said for word in ("a_made_up_connector", "a_made_up_nightly_job", "made_up_backup")
    ):
        raise CheckFailedError(A_GAP_WAS_NOT_NAMED)
    if view.may_report_complete or len(view.acts_outstanding) != len(THE_GATED_ACTS):
        raise CheckFailedError(A_COMPLETION_WAS_ALLOWED)

    words = await _refusal_words(routes.report_complete(admin))
    if words is None:
        raise CheckFailedError(A_COMPLETION_WAS_ALLOWED)
    if not all(leaf in words for leaf in THE_GATED_ACTS):
        raise CheckFailedError(THE_REFUSAL_DID_NOT_NAME_AN_ACT)

    recorded = {
        **open_record,
        "acts": [
            {"leaf": leaf, "performed_at": at(later), "recorded_by": "a made-up colleague"}
            for leaf in THE_GATED_ACTS
        ],
    }
    await routes.cutover(admin, recorded)
    if await _refusal_words(routes.report_complete(admin)) is not None:
        raise CheckFailedError(A_COMPLETION_WAS_REFUSED)
    reported = (await routes.page(admin)).cutover
    if reported.reported_complete is None or reported.reported_complete.by != admin:
        raise CheckFailedError(A_COMPLETION_WAS_NOT_KEPT)
    edited = await routes.cutover(admin, recorded)
    if edited.reported_complete is not None:
        raise CheckFailedError(A_COMPLETION_SURVIVED_AN_EDIT)
