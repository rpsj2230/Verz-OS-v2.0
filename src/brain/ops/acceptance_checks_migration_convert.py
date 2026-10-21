"""Install acceptance checks for what a person pastes from the old system: skills, exported items,
memory files and agents' availability, each checked by the migration package and kept nowhere.

Every check calls the route the migration is run through, as an administrator holding the install
authority, in the shape `brain.ops.acceptance_operations_console` sets out
(`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`). The switch is turned on through the Features route inside
the check's transaction and rolled back with it, and **nothing the routes answer is kept**, so there
is nothing for a check to leave behind but the register the carry check saves to compare with.

**What is proved is the checking and not the old system.** Nothing here reaches it, exports from it
or imports from it. The skills, items, memory files and agents are made up and say so, and a real
migration's are pasted by the person doing it. Proving that a real export arrives is the
rehearsal on a throwaway install (M37.7.6), which is a person's act.

Task ids: M37.1.2.1, M37.1.2.2, M37.1.2.3, M37.1.2.4, M37.2.2.2, M37.2.2.4, M37.2.2.5, M37.2.3.4
Task ids: M37.2.4.2, M37.2.4.3
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_migration_workspace import _administrator, _switched
from brain.ops.acceptance_operations_console import asking_as, console_for, refused
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2251

A, _B = RESERVED_DEPARTMENTS

A_ROUTER_PREAMBLE_WAS_KEPT: Final = "a description written at a router was not converted to a draft"
A_PLAIN_DESCRIPTION_WAS_REWRITTEN: Final = "a description already about the skill was rewritten"
A_STALE_SKILL_WAS_NOT_LISTED: Final = (
    "a skill nobody invoked in ninety days, or ever, was not listed to leave behind"
)
A_FRESH_SKILL_WAS_LISTED: Final = "a skill invoked last month was listed to leave behind"
AN_UNPROVEN_SKILL_WAS_CLEAN: Final = (
    "a skill no real task was run through, or one whose answer changed, was not named"
)
THE_ROUTES_WERE_OPEN_TO_ANYBODY: Final = "a person without the authority ran a conversion"
THE_ROUTES_IGNORED_THE_SWITCH: Final = "a conversion ran while the migration was switched off"
EVERY_EXPORT_WAS_NOT_REPARSED: Final = "an export was left out of the plan to read it again"
A_VECTOR_WAS_KEPT: Final = "an export's vectors were not named as discarded"
A_COLLISION_WAS_MERGED: Final = "two seeds that collapse to one name were not reported"
AN_EXPORT_GAP_WAS_MISSED: Final = (
    "an item decided migrate and not exported, or exported and decided retire, was not reported"
)
A_CONVERSATION_WAS_SEARCHABLE: Final = "an archived conversation was left searchable"
A_WIDENING_WAS_DERIVED: Final = "a conclusion that widens who may see what was derived"
A_PREFERENCE_WAS_REFUSED: Final = "a preference drawn from a memory file was refused"
ONE_REFUSAL_STOPPED_THE_REST: Final = "one refused conclusion stopped the others being derived"
AN_UNMAPPED_LEVEL_WAS_DEFAULTED: Final = "an availability nobody mapped was given an audience"
A_MAPPED_LEVEL_WAS_LOST: Final = "an availability that was mapped was not given its audience"

_SKILLS: Final = {
    "skills": [
        {"name": "quote", "description": "Use the quote skill to price a made-up job"},
        {"name": "plain", "description": "Prices a made-up job from a made-up list"},
        {
            "name": "stale",
            "description": "Does a made-up old thing",
            "last_invoked_at": "2019-01-01T00:00:00+00:00",
        },
        {
            "name": "fresh",
            "description": "Does a made-up recent thing",
            "last_invoked_at": "2999-01-01T00:00:00+00:00",
        },
    ],
    "checks": [
        {
            "skill_name": "plain",
            "task": "price a made-up job",
            "same_answer": False,
            "checked_by": "a made-up reviewer",
        }
    ],
    "now": "2999-01-10T00:00:00+00:00",
}


async def _begin(h: Harness) -> tuple[str, str, Any]:
    """An administrator with the switch on, a stranger, and the console they are asked through."""
    await h.found_departments()
    administrator = await _administrator(h)
    stranger = h.principal(A, "stranger")
    await h.person(stranger, department=A)
    await _switched(h, administrator, on=True, n=1)
    return administrator, stranger, console_for(h)


@check(
    leaves=("M37.2.2.2", "M37.2.2.4", "M37.2.2.5"),
    sentence=(
        "A pasted list of skills comes back with a draft description for each, the ones still "
        "written at a router, the ones to leave behind after ninety days unused, and the ones no "
        "real task has been run through; a person without the authority is refused and "
        "nothing is imported."
    ),
)
async def pasted_skills_are_converted_and_nothing_is_imported(h: Harness) -> None:
    from brain.migration_convert_routes import PastedSkillsAsked, convert_skills

    administrator, stranger, console = await _begin(h)

    async def ask(who: str) -> Any:
        return await convert_skills(
            console.request("POST"),
            PastedSkillsAsked.model_validate(_SKILLS),
            await asking_as(h, who, strong=True),
        )

    if not await refused(ask(stranger)):
        raise CheckFailedError(THE_ROUTES_WERE_OPEN_TO_ANYBODY)
    await _switched(h, administrator, on=False, n=2)
    if not await refused(ask(administrator)):
        raise CheckFailedError(THE_ROUTES_IGNORED_THE_SWITCH)
    await _switched(h, administrator, on=True, n=3)
    answer = await ask(administrator)
    drafts = {one.name: one.proposed_description for one in answer.descriptions}
    if drafts["quote"] != "price a made-up job":
        raise CheckFailedError(A_ROUTER_PREAMBLE_WAS_KEPT)
    if drafts["plain"] != "Prices a made-up job from a made-up list":
        raise CheckFailedError(A_PLAIN_DESCRIPTION_WAS_REWRITTEN)
    retired = [one.split(":")[0] for one in answer.to_retire]
    if "stale" not in retired:
        raise CheckFailedError(A_STALE_SKILL_WAS_NOT_LISTED)
    if "fresh" in retired:
        raise CheckFailedError(A_FRESH_SKILL_WAS_LISTED)
    if len(answer.unproven) < 2:
        raise CheckFailedError(AN_UNPROVEN_SKILL_WAS_CLEAN)


@check(
    leaves=("M37.1.2.1", "M37.1.2.2", "M37.1.2.3", "M37.1.2.4"),
    sentence=(
        "A pasted export is planned to be read again from its original bytes with every vector "
        "named as discarded, seeds that collapse to one name are reported and not merged, the "
        "export is compared with the agreed register in both directions, and every conversation "
        "is archived and none is searchable."
    ),
)
async def a_pasted_export_is_planned_compared_and_archived(h: Harness) -> None:
    from brain.migration_convert_routes import PastedCarryAsked, check_carry
    from brain.migration_routes import RegisterAsked, save_register

    administrator, _, console = await _begin(h)
    await save_register(
        console.request("PUT"),
        RegisterAsked.model_validate(
            {
                "surveyed": ["knowledge", "prompt", "tool", "conversation"],
                "items": [
                    {"item_id": "doc_1", "holding": "knowledge", "name": "A made-up list"},
                    {"item_id": "chat_1", "holding": "conversation", "name": "A made-up chat"},
                ],
                "decisions": [
                    {"item_id": "doc_1", "disposition": "migrate", "because": "It is theirs"},
                    {"item_id": "chat_1", "disposition": "retire", "because": "It is archived"},
                ],
                "mappings": [],
            }
        ),
        await asking_as(h, administrator, strong=True),
    )

    async def ask(document: dict[str, Any]) -> Any:
        return await check_carry(
            console.request("POST"),
            PastedCarryAsked.model_validate(document),
            await asking_as(h, administrator, strong=True),
        )

    answer = await ask(
        {
            "exports": [
                {
                    "item_id": "doc_1",
                    "content_digest": "d1",
                    "vector_count": 2,
                    "vector_width": 8,
                    "embedded_by": "a made-up model",
                }
            ],
            "seeds": [
                {"external_id": "e1", "name": "Made Up Ltd", "source_record": "r1"},
                {"external_id": "e2", "name": "MADE UP  Ltd.", "source_record": "r2"},
            ],
        }
    )
    if [one.item_id for one in answer.reparse] != ["doc_1"]:
        raise CheckFailedError(EVERY_EXPORT_WAS_NOT_REPARSED)
    if len(answer.vectors_discarded) != 1:
        raise CheckFailedError(A_VECTOR_WAS_KEPT)
    if len(answer.seed_findings) != 1:
        raise CheckFailedError(A_COLLISION_WAS_MERGED)
    if answer.export_gaps:
        raise CheckFailedError(AN_EXPORT_GAP_WAS_MISSED)
    if answer.archive is None or answer.archive.archived != ["chat_1"] or answer.archive.searchable:
        raise CheckFailedError(A_CONVERSATION_WAS_SEARCHABLE)
    wrong = await ask({"exports": [{"item_id": "chat_1", "content_digest": "d2"}]})
    if len(wrong.export_gaps) < 2:
        raise CheckFailedError(AN_EXPORT_GAP_WAS_MISSED)


@check(
    leaves=("M37.2.4.2", "M37.2.4.3"),
    sentence=(
        "A conclusion drawn from an old memory file is re-derived the ordinary way, one that would "
        "widen who may see what is refused by name without stopping the others, and the handover "
        "note counts only what was derived."
    ),
)
async def a_conclusion_is_re_derived_and_a_widening_is_refused(h: Harness) -> None:
    from brain.migration_convert_routes import PastedLearningAsked, check_learning

    administrator, _, console = await _begin(h)

    def one(change: str) -> dict[str, str]:
        return {
            "source_file": "memory/made-up.md",
            "change": change,
            "subject": "short answers",
            "derived_by": "a made-up reader",
            "because": "the made-up file says so",
        }

    answer = await check_learning(
        console.request("POST"),
        PastedLearningAsked.model_validate(
            {
                "memories": [{"source_file": "memory/made-up.md", "text": "Likes short answers"}],
                "derivations": [one("scope_widening"), one("preference")],
            }
        ),
        await asking_as(h, administrator, strong=True),
    )
    if any(row.change == "scope_widening" for row in answer.derived):
        raise CheckFailedError(A_WIDENING_WAS_DERIVED)
    if [row.change for row in answer.derived] != ["preference"]:
        raise CheckFailedError(A_PREFERENCE_WAS_REFUSED)
    if len(answer.refused) != 1:
        raise CheckFailedError(ONE_REFUSAL_STOPPED_THE_REST)


@check(
    leaves=("M37.2.3.4",),
    sentence=(
        "An old agent's availability is mapped to who may see it here by the mapping given, an "
        "availability nobody mapped is named and never given a default, and what the agent may "
        "reach is left to its authority."
    ),
)
async def availability_is_mapped_and_never_defaulted(h: Harness) -> None:
    from brain.migration_convert_routes import PastedAvailabilityAsked, map_availability

    administrator, _, console = await _begin(h)
    answer = await map_availability(
        console.request("POST"),
        PastedAvailabilityAsked.model_validate(
            {
                "agents": [
                    {"name": "made-up helper", "availability": "everyone"},
                    {"name": "made-up secret", "availability": "private-ish"},
                ],
                "mapping": {"everyone": "company"},
                "owner_id": administrator,
            }
        ),
        await asking_as(h, administrator, strong=True),
    )
    if [row.subject for row in answer.unmapped] != ["made-up secret"]:
        raise CheckFailedError(AN_UNMAPPED_LEVEL_WAS_DEFAULTED)
    if [(row.name, row.level) for row in answer.audiences] != [("made-up helper", "company")]:
        raise CheckFailedError(A_MAPPED_LEVEL_WAS_LOST)
