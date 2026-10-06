"""The install acceptance check for a department's fast-lane rules (M6.5.1).

A department's administrator adds a rule from the console, and the next question one of that
department's people asks in its words is answered with no model call; nobody in another department
is answered by it, the other department's administrator can neither see, test nor retire it, and
once retired it answers nothing from the next question. Every step is the routes' own function in
the routes' order (`brain.rule_routes`), and every question goes through `/answer`'s own
`brain.api_routes.answered_for`, which reads the rule table as it is asked.

**What the rule answers from is a price list acceptance_a uploads** through the Classification
routes' own sequence, reused from `brain.ops.acceptance_checks_tables` as the speed check reuses it,
so the row a rule reads is a row a department uploaded. **The asker in acceptance_b holds the
list's table grant over acceptance_a's rows**, so the one thing standing between them and the
answer is that the rule is acceptance_a's, which is the property being proved; an asker who could
not read the row anyway would pass the check with the department ignored. **Both administrators
hold the same read over the list**, for the same reason: acceptance_b's administrator could read
the price, so their refused test is refused for the rule's department and not for the data.

**No model is asked for the answer, and the stand-in proves it.** The application's model is the
memory checks' `KeptPrompts`, which keeps every prompt it is sent, and the answered question's
request row is read back from the ledger as the fast lane's with no provider. A question no rule
answers is put to the stand-in, which is what makes a question the rule should not have answered
visible as an answer that does not carry the price.

Task ids: M6.5.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in

# The price list, the stand-in and the asking helpers, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of this one.
from brain.ops.acceptance_checks_memory import KeptPrompts, memory_app
from brain.ops.acceptance_checks_speed import RULE_TEMPLATE, asked_on, row_of
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    _Administrator,
    _administrator,
    _apply,
    _console,
    _price_list,
    _upload,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.classification_store import Writer

A, B = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 446

# ---------------------------------------------------------- what the check says on failure
#: The rule a department's administrator added did not answer that department's next question.
RULE_DID_NOT_ANSWER: Final = (
    "a rule a department's administrator added did not answer that department's next question "
    "on the fast lane with no model call"
)
#: A rule answered before anybody had added it, so the check proved nothing about adding one.
ANSWERED_BEFORE_IT_WAS_ADDED: Final = (
    "the question was answered before the rule was added, so adding it proved nothing"
)
#: The administrator's own test of the rule did not say what it would answer.
TEST_DID_NOT_ANSWER: Final = (
    "the administrator's test of their own rule did not say it would answer the price"
)
#: A person in another department was answered by a department's rule.
ANSWERED_ANOTHER_DEPARTMENT: Final = (
    "a person in another department was answered by a department's rule"
)
#: Another department's administrator saw the rule.
SEEN_BY_ANOTHER_DEPARTMENT: Final = (
    "another department's administrator was shown a department's rule"
)
#: Another department's administrator tested or retired the rule.
CHANGED_BY_ANOTHER_DEPARTMENT: Final = (
    "another department's administrator could test or retire a department's rule"
)
#: The rule still answered after it was retired.
STILL_ANSWERS_AFTER_RETIREMENT: Final = "a retired rule still answered the next question"


async def _reading(h: Harness, admin: _Administrator, table: str) -> _Administrator:
    """`admin` granted the list's table reads in acceptance_a, at their console reach anew."""
    for capability, scope in _in(A, table, *KNOWLEDGE_READS):
        await h.grant(admin.principal_id, capability, scope)
    return _Administrator(
        admin.principal_id, await _console(h, admin.principal_id, second_factor=True)
    )


def _writer(h: Harness, admin: _Administrator) -> Writer:
    from brain.ops.classification_store import Writer

    return Writer(actor_id=admin.principal_id, ent_hash=admin.reach.ent_hash(), trace_id=h.trace_id)


@check(
    leaves=("M6.5.1",),
    sentence=(
        "acceptance_a's administrator adds a rule from the console for acceptance_a, tests it and "
        "the next question in its words from acceptance_a is answered with no model call; an "
        "acceptance_b asker who reads the row is not answered by it, acceptance_b's administrator "
        "can neither see, test nor retire it, and once retired it answers nothing."
    ),
)
async def a_departments_rule_answers_its_own_from_the_next_question(h: Harness) -> None:
    from brain.core.errors import Absent, Denied
    from brain.gate.context import Channel
    from brain.gate.rule_store import StoredRules
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.rule_routes import FastRuleAsked, FastRuleTried, added, readable, retired, tried

    await h.found_departments()
    admin_a, admin_b = await _administrator(h, A), await _administrator(h, B)
    prices = _price_list(h, "rules", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin_a, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin_a, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    table = table_capability(prices.entity).value
    # Both administrators read the list in acceptance_a, as a department's administrator reads
    # the tables they write rules over: what stands between acceptance_b's administrator and
    # acceptance_a's rule is then the rule's department alone. See the module docstring.
    admin_a, admin_b = await _reading(h, admin_a, table), await _reading(h, admin_b, table)
    asker_a, asker_b = h.principal(A, "asker"), h.principal(B, "asker")
    await h.person(asker_a, department=A, grants=_in(A, table, *KNOWLEDGE_READS))
    # acceptance_b's asker reads acceptance_a's rows: only the rule's department stands between
    # them and the answer. See the module docstring.
    await h.person(asker_b, department=B, grants=_in(A, table, *KNOWLEDGE_READS))

    template = RULE_TEMPLATE.format(word=h.word().lower())
    rule = FastRuleAsked(
        name=f"rate_{h.run}",
        department=A,
        template=template,
        slot="name",
        source=TABLES_SOURCE,
        entity=prices.entity,
        match_field="name",
        answer_field=SELL_PRICE,
    )
    price = prices.rows[0][SELL_PRICE]
    question = template.replace("{name}", prices.rows[0]["name"])
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in, recorded=True)
    store = StoredRules(h.sessions)

    before = await asked_on(h, app, asker_a, question, 1, Channel.CONSOLE)
    if before.text is not None and price in before.text:
        raise CheckFailedError(ANSWERED_BEFORE_IT_WAS_ADDED)

    trial = FastRuleTried(**rule.model_dump(), question=question)
    tested = await tried(app.state, trial, reach=admin_a.reach, now=h.now)
    if not tested.matches or tested.answer is None or price not in tested.answer:
        raise CheckFailedError(TEST_DID_NOT_ANSWER)
    try:
        await tried(app.state, trial, reach=admin_b.reach, now=h.now)
    except Denied:
        pass
    else:
        raise CheckFailedError(CHANGED_BY_ANOTHER_DEPARTMENT)

    made = await added(store, rule, reach=admin_a.reach, writer=_writer(h, admin_a), now=h.now)
    if not made.done or made.rule_id is None:
        raise CheckFailedError("a department's administrator could not add a rule for it")

    sent_before = len(stand_in.sent)
    answered = await asked_on(h, app, asker_a, question, 2, Channel.CONSOLE)
    if (
        answered.text is None
        or price not in answered.text
        or len(stand_in.sent) != sent_before
        or await row_of(h, 2) != ("fast", None, None, "human_interactive")
    ):
        raise CheckFailedError(RULE_DID_NOT_ANSWER)

    elsewhere = await asked_on(h, app, asker_b, question, 3, Channel.CONSOLE)
    if elsewhere.text is not None and price in elsewhere.text:
        raise CheckFailedError(ANSWERED_ANOTHER_DEPARTMENT)

    live = await store.live()
    if made.rule_id in {one.rule_id for one in readable(live, admin_b.reach, h.now)}:
        raise CheckFailedError(SEEN_BY_ANOTHER_DEPARTMENT)
    if made.rule_id not in {one.rule_id for one in readable(live, admin_a.reach, h.now)}:
        raise CheckFailedError("a department's administrator was not shown their own rule")
    try:
        await retired(
            store, made.rule_id, reach=admin_b.reach, writer=_writer(h, admin_b), now=h.now
        )
    except Absent:
        pass
    else:
        raise CheckFailedError(CHANGED_BY_ANOTHER_DEPARTMENT)

    await retired(store, made.rule_id, reach=admin_a.reach, writer=_writer(h, admin_a), now=h.now)
    after = await asked_on(h, app, asker_a, question, 4, Channel.CONSOLE)
    if after.text is not None and price in after.text:
        raise CheckFailedError(STILL_ANSWERS_AFTER_RETIREMENT)
