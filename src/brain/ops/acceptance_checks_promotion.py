"""The install acceptance check for promoting a learned fast-lane rule (M39.4.2.3).

A tier-two learning in acceptance_a proposes two rules over a price list acceptance_a uploads: one
answering with the open sell price, one with the cost, which the list classifies as confidential.
Each question goes through `/answer`'s own route function, `brain.api_routes.answer`, so the
occurrence a held rule would have used is counted by the background task the route attaches, not
by the check. Each press goes through `brain.promotion_routes.promote_learned_rule` as its reader.

**What is proved, in order.** A held rule answers nothing. One conversation is counted and is not
enough, so a press is refused. Three separate conversations are enough; an administrator of
acceptance_b is refused as for a rule that does not exist, and the rule's proposer is refused. One
administrator of acceptance_a promotes the sell-price rule and the next question is answered on the
fast lane with no model call, on the ledger under them. The cost rule takes two: the first press
holds it, the same person cannot press again, and a second administrator's press applies it in
their name.

**The rules answer from a list acceptance_a uploads**, through the Classification routes' own
sequence, reused from `brain.ops.acceptance_checks_tables` as the department rule check reuses it.

Task ids: M39.4.2.3
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Final, cast

from sqlalchemy import insert, text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_checks_dept_rules import _reading
from brain.ops.acceptance_checks_memory import KeptPrompts, memory_app
from brain.ops.acceptance_checks_speed import RULE_TEMPLATE, row_of, trace_of
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    _administrator,
    _apply,
    _price_list,
    _upload,
)
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page.
CHECK_ORDER: Final = 448

#: The column the list classifies as confidential, which makes a rule over it take two people.
COST: Final = "cost"

HELD_RULE_ANSWERED: Final = "a learned rule held for review answered a question"
NOT_COUNTED: Final = (
    "a question a held rule would have answered was not counted once for its conversation"
)
PROMOTED_UNREADY: Final = (
    "a learned rule was promoted before enough conversations would have used it"
)
PRESSED_ELSEWHERE: Final = (
    "an administrator of another department, or the rule's proposer, could press to promote it"
)
NOT_APPLIED: Final = (
    "a promoted rule did not answer the next question on the fast lane with no model call, on "
    "the ledger under its promoter"
)
ONE_PERSON_FOR_MONEY: Final = (
    "a rule answering with a confidential column was promoted by one person, or not by two"
)


async def _asked(h: Harness, principal_id: str, *, reach: Any) -> Any:
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    # A cast at the routes' boundary, as `acceptance_checks_review._reader` makes it.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person),
            reach=reach,
            now=h.now,
            channel=Channel.CONSOLE,
        ),
    )


async def _asked_on_answer(h: Harness, app: Any, principal_id: str, question: str, n: int) -> str:
    """One question through `/answer`'s own function in a new conversation, with the background
    task the route attaches run as the server runs it. The answer's text."""
    from starlette.requests import Request

    from brain.api_routes import Question, answer
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel, open_trace

    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    asked = await _asked(h, principal_id, reach=reach)
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    response = await answer(
        request,
        open_trace(trace_of(h, n), h.now, Channel.CONSOLE),
        asked,
        Question(question=question),
    )
    said: list[str] = []
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        said.append(chunk if isinstance(chunk, str) else bytes(chunk).decode("utf-8"))
    if response.background is not None:
        await response.background()
    return "".join(said)


async def _press(h: Harness, app: Any, principal_id: str, memory_id: str) -> Any:
    """One press as `principal_id` at their console reach: the view, the refusal, or `Absent`."""
    from starlette.requests import Request

    from brain.core.errors import Absent
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.promotion_routes import promote_learned_rule

    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    asked = await _asked(h, principal_id, reach=reach)
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    try:
        return await promote_learned_rule(request, asked, memory_id)
    except Absent:
        return None


def _state(pressed: Any) -> str:
    return str(getattr(pressed, "state", ""))


@check(
    leaves=("M39.4.2.3",),
    sentence=(
        "A learned acceptance_a rule held for review answers nothing, and is pressed in vain "
        "until three conversations would have used it; acceptance_b's administrator and its "
        "proposer are refused, one acceptance_a administrator promotes it and the next question "
        "is answered with no model call, and a rule over the confidential cost takes two people."
    ),
)
async def a_learned_rule_is_promoted_once_conversations_agree(h: Harness) -> None:
    from brain.console.govern_estate import UNDO_AUTHORITY
    from brain.gate.fast_lane import FastPathRule
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.memory.promotion_store import StoredLearnedRules
    from brain.memory.tiers import Change, Tier
    from brain.rule_routes import stored_id
    from brain.tables.learning import LearningRow

    await h.found_departments()
    admin_a = await _administrator(h, A)
    prices = _price_list(h, "learned", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin_a, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin_a, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    table = table_capability(prices.entity).value
    asker = h.principal(A, "asker")
    await h.person(asker, department=A, grants=_in(A, table, *KNOWLEDGE_READS))
    first, second, proposer = (
        h.principal(A, "promoter"),
        h.principal(A, "second"),
        h.principal(A, "proposer"),
    )
    elsewhere = h.principal(B, "promoter")
    for person, department in ((first, A), (second, A), (proposer, A), (elsewhere, B)):
        await h.person(person, department=department, grants=_in(department, UNDO_AUTHORITY.value))
    admin_a = await _reading(h, admin_a, table)

    store = StoredLearnedRules(h.sessions)
    held: dict[str, tuple[str, str]] = {}
    for column in (SELL_PRICE, COST):
        word = h.word().lower()
        template = RULE_TEMPLATE.format(word=word)
        memory_id = f"lr_{column[:4]}_{h.run}"[:26]
        await h.execute(
            insert(LearningRow).values(
                memory_id=memory_id,
                change=Change.FAST_PATH_RULE.value,
                tier=int(Tier.PROMOTED),
                subject=memory_id,
                agent_id=None,
            )
        )
        rule_id = stored_id(A, f"lr_{word}") or ""
        await store.hold(
            memory_id,
            FastPathRule(
                rule_id=rule_id,
                template=template,
                slot="name",
                source=TABLES_SOURCE,
                entity=prices.entity,
                match_field="name",
                answer_field=column,
            ),
            department=A,
            proposed_by=proposer,
        )
        held[column] = (memory_id, template.replace("{name}", prices.rows[0]["name"]))

    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in, recorded=True)
    price = prices.rows[0][SELL_PRICE]
    sell, sell_question = held[SELL_PRICE]
    cost, cost_question = held[COST]

    said = await _asked_on_answer(h, app, asker, sell_question, 1)
    if price in said:
        raise CheckFailedError(HELD_RULE_ANSWERED)
    counted = (await store.occurrences((sell,))).get(sell, ())
    if len(counted) != 1:
        raise CheckFailedError(NOT_COUNTED)
    if _state(await _press(h, app, first, sell)) == "promoted":
        raise CheckFailedError(PROMOTED_UNREADY)

    for n in (2, 3):
        await _asked_on_answer(h, app, asker, sell_question, n)
    for n in (4, 5, 6):
        await _asked_on_answer(h, app, asker, cost_question, n)

    if await _press(h, app, elsewhere, sell) is not None:
        raise CheckFailedError(PRESSED_ELSEWHERE)
    if _state(await _press(h, app, proposer, sell)):
        raise CheckFailedError(PRESSED_ELSEWHERE)

    promoted = await _press(h, app, first, sell)
    sent_before = len(stand_in.sent)
    answered = await _asked_on_answer(h, app, asker, sell_question, 7)
    ledger = await h.execute(
        text("SELECT actor_id FROM obs.audit_entry WHERE subject = :subject").bindparams(
            subject=f"setting:learned_rule.{sell}"
        )
    )
    if (
        _state(promoted) != "promoted"
        or price not in answered
        or len(stand_in.sent) != sent_before
        or await row_of(h, 7) != ("fast", None, None, "human_interactive")
        or [str(one) for (one,) in ledger.all()] != [first]
    ):
        raise CheckFailedError(NOT_APPLIED)

    held_first = await _press(h, app, first, cost)
    again = await _press(h, app, first, cost)
    applied = await _press(h, app, second, cost)
    written = (
        await h.execute(
            text(
                "SELECT created_by, learned_from FROM gate.fast_path_rule"
                " WHERE learned_from = :memory AND deleted_at IS NULL"
            ).bindparams(memory=cost)
        )
    ).all()
    if (
        _state(held_first) != "awaiting_second"
        or _state(again)
        or _state(applied) != "promoted"
        or [tuple(one) for one in written] != [(second, cost)]
    ):
        raise CheckFailedError(ONE_PERSON_FOR_MONEY)
