"""The install acceptance checks for learning: who oversees a change, and what a person can undo.

Each check starts from a memory a reserved person formed on Ask through
`brain.api_routes.answered_for`, as `brain.ops.acceptance_checks_memory` does, and then acts on it
through the install's own functions and store: `brain.mine_routes.edited` and `forgotten`, the
bodies of a person's own Edit and Forget; `brain.estate_routes.learnings_stored` and
`brain.console.govern_estate.learning_estate`, what the Learning screen reads and decides; and
`brain.ops.memory_store.StoredMemoryRecords`, the store every revision is written through. Every
write is in the check's rolled-back transaction.

**The tier a change needs is the database's to refuse, not only the domain's.** `mem.learning`
carries a check constraint generated from `brain.memory.tiers.BLAST_RADIUS`, so a learning recorded
at a tier lower than its reach needs is refused by the install's own table whoever writes it. The
check tries every change at every tier inside a savepoint of its own and reads the refusal.

**The Learning screen's two figures are proved without changing what the install holds.** They are
saved in the check's transaction as the route saves them and read back by the reload every process
runs, and the product's own readers are then asked under them through
`brain.ops.tuning.reading`, which lends the rows to the check's task alone, so no other request the
process serves decays a memory at a figure that is about to be rolled back.

Task ids: M16.3.5, M16.3.6, M16.4.2, M16.6.8, M27.7.21, M33.3.1.4
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in

# The memory checks' people, application and readers, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks_memory import (
    ask,
    memories_of,
    memory_app,
    people,
    recalled_for,
    shown_about,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from sqlalchemy.sql import Executable

A, B = RESERVED_DEPARTMENTS

#: The capability a Learning screen reader holds to open it, and the one that undoes.
LEARNING_READ: Final = "read:learning"


async def refused_by_the_database(h: Harness, statement: Executable) -> bool:
    """Whether the install's database refuses a write, asked in a savepoint of its own.

    The session's savepoint is rolled back whatever happened, so a refusal leaves the check's
    transaction usable and an acceptance leaves nothing behind.
    """
    from sqlalchemy.exc import DBAPIError

    async with h.sessions() as session:
        try:
            await session.execute(statement)
            await session.flush()
        except DBAPIError:
            await session.rollback()
            return True
        await session.rollback()
    return False


async def stated_memory(h: Harness, principal_id: str, words: str, n: int) -> str:
    """A stated memory formed on Ask by `principal_id`, and its id."""
    app = await memory_app(h)
    await ask(h, app, principal_id, f"Remember that {words}.", n)
    found = [one for one in await memories_of(h, principal_id) if one.statement == words]
    if len(found) != 1:
        raise CheckFailedError("saying remember that on Ask did not keep a stated memory")
    return found[0].memory_id


async def corrections_of(h: Harness, memory_ids: list[str]) -> list[tuple[str, str, str | None]]:
    """Each correction naming these memories, in order: the memory, the kind, the replacement."""
    rows = (
        await h.execute(
            text(
                "SELECT memory_id, correction, by_id FROM mem.correction"
                " WHERE memory_id = ANY(:ids) OR by_id = ANY(:ids) ORDER BY at, id"
            ).bindparams(ids=memory_ids)
        )
    ).all()
    return [(str(one[0]), str(one[1]), one[2]) for one in rows]


# --------------------------------------------- M16.4.2, M33.3.1.4 edited, forgotten, kept
@check(
    leaves=("M16.4.2", "M33.3.1.4"),
    sentence=(
        "A person edits a memory they formed on Ask and then forgets it, through their own Edit "
        "and Forget: each change is marked and nothing is deleted, the old words stay in the "
        "history, answers use what they wrote and then nothing, and a colleague can do neither."
    ),
)
async def a_person_edits_and_forgets_their_own_memory(h: Harness) -> None:
    from brain.mine_routes import edited, forgotten
    from brain.ops.memory_store import StoredMemoryRecords

    placed = await people(h)
    word, later = h.word(), h.word()
    first = await stated_memory(h, placed.member, f"I work from {word} on Fridays", 1)
    records = StoredMemoryRecords(h.sessions)
    member = await h.reach(placed.member)

    def by(principal_id: str, reach_hash: str) -> dict[str, Any]:
        return {
            "principal_id": principal_id,
            "ent_hash": reach_hash,
            "trace_id": h.trace_id,
            "now": h.now,
        }

    colleague = await h.reach(placed.colleague)
    if await edited(
        h.sessions,
        records,
        memory_id=first,
        statement="Somebody else's words",
        **by(placed.colleague, colleague.ent_hash()),
    ) is not None or await forgotten(
        h.sessions, records, memory_id=first, **by(placed.colleague, colleague.ent_hash())
    ):
        raise CheckFailedError("a colleague could edit or forget somebody else's memory")

    changed = await edited(
        h.sessions,
        records,
        memory_id=first,
        statement=f"I work from {later} on Fridays",
        **by(placed.member, member.ent_hash()),
    )
    if changed is None or not changed.took_effect or changed.replacement_id is None:
        raise CheckFailedError("a person could not edit a memory formed from their own words")
    second = changed.replacement_id
    edited_to = f"I work from {later} on Fridays"
    if await shown_about(h, placed.member, member, h.now) != {edited_to: 1.0}:
        raise CheckFailedError("an edited memory was not what the person was shown afterwards")
    if await recalled_for(h, member, A, h.now) != (edited_to,):
        raise CheckFailedError("an answer would still use the words an edit replaced")
    if await corrections_of(h, [first, second]) != [(first, "superseded", second)]:
        raise CheckFailedError("an edit was not recorded as the old memory marked as replaced")

    gone = await forgotten(
        h.sessions, records, memory_id=second, **by(placed.member, member.ent_hash())
    )
    back = await shown_about(h, placed.member, member, h.now)
    gone_again = await forgotten(
        h.sessions, records, memory_id=first, **by(placed.member, member.ent_hash())
    )
    if gone is None or not gone.took_effect or back != {f"I work from {word} on Fridays": 1.0}:
        raise CheckFailedError("forgetting an edit did not put back the words it replaced")
    if gone_again is None or not gone_again.took_effect:
        raise CheckFailedError("a person could not forget a memory formed from their own words")
    if await shown_about(h, placed.member, member, h.now) or await recalled_for(
        h, member, A, h.now
    ):
        raise CheckFailedError("a forgotten memory was still shown or would still be used")
    if len(await memories_of(h, placed.member)) != 2:
        raise CheckFailedError("an edit or a forget deleted a memory rather than marking it")


# -------------------------------------------------- M16.3.5, M16.3.6 the tier is decided
@check(
    leaves=("M16.3.5", "M16.3.6"),
    sentence=(
        "Every kind of change the system could learn is proposed at the tier its reach needs, "
        "every change that widens who sees what is gated for a person, and the install's learning "
        "table refuses each kind recorded at any other tier, whoever writes it."
    ),
)
async def every_learned_change_is_held_at_the_tier_its_reach_needs(h: Harness) -> None:
    from brain.memory.tiers import BLAST_RADIUS, CHANGES_WHAT_ANYBODY_MAY_SEE, Tier, propose
    from brain.tables.learning import LearningRow

    for change in CHANGES_WHAT_ANYBODY_MAY_SEE:
        if BLAST_RADIUS[change] is not Tier.GATED:
            raise CheckFailedError("a change that widens who sees what is not gated for a person")
    for number, (change, needs) in enumerate(BLAST_RADIUS.items()):
        if propose(change, subject="acceptance").tier is not needs:
            raise CheckFailedError("a learned change was not proposed at the tier its reach needs")
        for tier in Tier:
            row = insert(LearningRow).values(
                memory_id=f"acceptance_{h.run}_{number}_{int(tier)}",
                change=change.value,
                tier=int(tier),
                subject="acceptance",
                agent_id=None,
            )
            if await refused_by_the_database(h, row) is (tier is needs):
                raise CheckFailedError(
                    "the install's learning table held a change at a tier its reach does not "
                    "need, or refused it at the tier it does"
                )


# ------------------------------------------------ M27.7.21 a conversation's learning, undone
@check(
    leaves=("M27.7.21",),
    sentence=(
        "What a person in acceptance_a asked to be remembered on Ask is on the Learning screen of "
        "an administrator of acceptance_a, in effect and undoable, and not on acceptance_b's; "
        "undone, it is still listed and no longer in effect, and the person's answers stop "
        "using it."
    ),
)
async def a_conversation_learning_is_reviewed_and_undone(h: Harness) -> None:
    from brain.console.govern_estate import UNDO_AUTHORITY, learning_estate, may_undo
    from brain.console.workspace import Basis
    from brain.estate_routes import MAX_LEARNINGS_CONSIDERED, learnings_stored
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.memory_store import StoredMemoryRecords

    placed = await people(h)
    memory_id = await stated_memory(h, placed.member, f"I sign as {h.word()}", 1)
    admins: dict[str, Any] = {}
    for department in (A, B):
        made = h.principal(department, "learning")
        await h.person(
            made,
            department=department,
            grants=_in(department, LEARNING_READ, UNDO_AUTHORITY.value, *KNOWLEDGE_READS),
        )
        admins[department] = await h.reach(made)

    async def reviewed(reader: Any) -> dict[str, tuple[bool, bool]]:
        async with h.sessions() as session:
            stored = await learnings_stored(session, (), MAX_LEARNINGS_CONSIDERED)
        review = learning_estate(
            basis=Basis.OWN,
            records=stored.records,
            learnings=stored.learnings,
            caller=reader,
            now=h.now,
            supersessions=stored.corrections.supersessions,
            demotions=stored.corrections.demotions,
        )
        by_id = {one.memory_id: one for one in stored.learnings}
        return {
            one.memory_id: (one.in_effect, may_undo(reader, by_id[one.memory_id], h.now))
            for one in review.tier_one
        }

    if (await reviewed(admins[A])).get(memory_id) != (True, True):
        raise CheckFailedError(
            "a learning a person's conversation formed was not on their department's Learning "
            "screen, in effect and undoable"
        )
    if memory_id in await reviewed(admins[B]):
        raise CheckFailedError("another department's Learning screen listed a person's learning")

    async with h.sessions() as session:
        from brain.estate_routes import learning_of

        learning = await learning_of(session, memory_id)
    if learning is None:
        raise CheckFailedError("a learning a conversation formed could not be read back")
    decided = await StoredMemoryRecords(h.sessions).undo(
        learning,
        actor=admins[A].principal_id,
        trace_id=h.trace_id,
        ent_hash=admins[A].ent_hash(),
    )
    if not decided.took_effect or (await reviewed(admins[A])).get(memory_id) != (False, True):
        raise CheckFailedError("an undone learning was not listed as no longer in effect")
    member = await h.reach(placed.member)
    if await recalled_for(h, member, A, h.now):
        raise CheckFailedError("a person's answers still used a learning an administrator undid")


# ------------------------------------------------ M16.6.8 the Learning screen's two figures
@check(
    leaves=("M16.6.8",),
    sentence=(
        "An administrator saves how long an inferred memory lasts and how many conversations "
        "must agree before a rule is offered for review: figures out of bounds or naming a tier "
        "are refused, saves are audited and reloaded, an inference formed on Ask lapses at the "
        "saved lifetime and not the product's, two agreeing conversations ready a rule, and no "
        "figure promotes a gated change."
    ),
)
async def learning_figures_are_set_in_bounds_and_move_no_tier(h: Harness) -> None:
    from datetime import timedelta

    from brain.console.reach_view import tier_two_rows
    from brain.core.entitlement import Capability
    from brain.core.scope import Scope
    from brain.memory.digest import Learning
    from brain.memory.formation import Formation, MemoryKind
    from brain.memory.tiers import Change, Occurrence, Tier, blast_radius, may_promote, propose
    from brain.ops.acceptance_checks_capacity import CHANGES_LIMITS, _setting_entries
    from brain.ops.acceptance_checks_memory import (
        PREFERENCE_QUESTION,
        KeptPrompts,
        a_document,
        unending,
    )
    from brain.ops.install_settings import read_tuned
    from brain.ops.tuning import (
        INFERRED_HALF_LIFE,
        KNOB_BY_NAME,
        LEARNING_KINDS,
        NOT_A_KNOB,
        PROMOTION_AGREEMENT_KNOB,
        TuningRefusedError,
        held,
        inferred_lifetime_days,
        promotion_agreement,
        reading,
        save,
        value,
    )
    from brain.settings_routes import may_configure
    from brain.tables.audit import attributed_to
    from brain.tuning_routes import problem_on

    before = dict(held())
    placed = await people(h)
    admin = h.principal(A, "learning_figures")
    await h.person(admin, department=A, grants=((CHANGES_LIMITS, Scope.unrestricted()),))
    if not may_configure(await h.reach(admin), h.now):
        raise CheckFailedError("the route's own question refused the Settings authority")

    half, agree = KNOB_BY_NAME[INFERRED_HALF_LIFE], KNOB_BY_NAME[PROMOTION_AGREEMENT_KNOB]
    # Outside the bounds: refused by the route's judgement and by the write beneath it.
    for name, refused in (
        (half.name, half.lowest - 1),
        (half.name, half.highest + 1),
        (agree.name, agree.lowest - 1),
        (agree.name, agree.highest + 1),
    ):
        if not problem_on(name, refused, LEARNING_KINDS):
            raise CheckFailedError("a learning figure outside the product's bounds was not refused")
        try:
            async with h.sessions() as session:
                await save(session, name, refused, updated_by=admin)
                await session.commit()
        except TuningRefusedError:
            continue
        raise CheckFailedError("a learning figure outside the product's bounds was written")
    # A figure naming a tier, or another screen's limit, is not a figure this screen sets.
    for name in (*(f"tier_{one.value}" for one in Change), "person_per_minute"):
        if problem_on(name, 1, LEARNING_KINDS) != NOT_A_KNOB:
            raise CheckFailedError("the Learning screen would set a figure that is not learning's")

    wanted = {half.name: half.lowest, agree.name: agree.lowest}
    async with h.sessions() as session:
        reach = await h.reach(admin)
        for statement in attributed_to(
            actor_id=admin, ent_hash=reach.ent_hash(), trace_id=h.trace_id
        ):
            await session.execute(statement)
        for name, amount in wanted.items():
            await save(session, name, amount, updated_by=admin)
        await session.commit()
    async with h.sessions() as session:
        saved = await read_tuned(session)
        await session.commit()
    if any(saved.get(name) != amount for name, amount in wanted.items()):
        raise CheckFailedError("the reload every process runs did not read back what was saved")
    for key in (half.key, agree.key):
        entries = await _setting_entries(h, key)
        if not entries or entries[-1][0] != admin:
            raise CheckFailedError("a saved learning figure is not in the ledger under its saver")

    # An inference formed on Ask, read by the recall a model's hints use, under each figure.
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in)
    answered = await ask(
        h, app, placed.member, PREFERENCE_QUESTION.format(pref=words.pref, key=words.key), 1
    )
    if answered.composed is None or not stand_in.sent:
        raise CheckFailedError("a question the check's document answers was not answered")
    inferred = f"I prefer {words.pref} answers"
    member = unending(await h.reach(placed.member))
    shortest = inferred_lifetime_days(float(value(half.name, saved)))
    if shortest >= inferred_lifetime_days(float(half.default)):
        raise CheckFailedError("the shortest lifetime is not shorter than the product's")
    later = h.now + timedelta(days=shortest + 1)
    with reading({}):
        at_default = await recalled_for(h, member, A, later)
    with reading(saved):
        at_saved = await recalled_for(h, member, A, later)
        on_screen = await shown_about(h, placed.member, member, later)
    if inferred not in at_default:
        raise CheckFailedError("an inference was not recalled inside the product's lifetime")
    if inferred in at_saved or inferred in on_screen:
        raise CheckFailedError("an inference was still recalled past the saved lifetime")

    # A tier-two rule two conversations agree on: ready at the saved figure, not the product's.
    rule = Learning(
        memory_id=f"acceptance_rule_{h.run}",
        proposal=propose(Change.FAST_PATH_RULE, subject=f"acceptance_subject_{h.run}"),
        formation=Formation(
            principal_id=placed.member,
            capabilities=(Capability(value=LEARNING_READ),),
            scope=Scope.unrestricted(),
            ent_hash=member.ent_hash(),
            formed_at=h.now,
            kind=MemoryKind.ADAPTIVE,
        ),
        agent_id=f"acceptance_agent_{h.run}",
    )
    two = {
        rule.memory_id: tuple(
            Occurrence(conversation_id=f"{h.run}_{n}", on=h.now) for n in range(2)
        )
    }

    def ready() -> bool:
        rows = tier_two_rows((rule,), agent_id=rule.agent_id or "", occurrences=two, now=h.now)
        return bool(rows) and rows[0].promote_ready

    with reading({}):
        ready_at_default = ready()
    with reading(saved):
        ready_at_saved = ready()
        plenty = [Occurrence(conversation_id=f"{h.run}_{n}", on=h.now) for n in range(20)]
        promoted_wrongly = [
            one.value
            for one in Change
            if may_promote(
                propose(one, subject=one.value), plenty, now=h.now, agreement=promotion_agreement()
            )
            is not (blast_radius(one) is Tier.PROMOTED)
        ]
    if ready_at_default or not ready_at_saved:
        raise CheckFailedError("a rule's readiness for review did not follow the saved agreement")
    if promoted_wrongly:
        raise CheckFailedError("a saved figure let a change be promoted its tier does not allow")

    if dict(held()) != before:
        raise CheckFailedError("the check changed what the process running it holds")
