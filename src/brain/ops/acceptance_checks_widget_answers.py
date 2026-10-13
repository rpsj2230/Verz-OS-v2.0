"""The install acceptance check for the website widget's model-written answers and their daily cap.

The owner decided on needs item 139 (2026-10-13, option B) that the widget's answers are written by
the model from the public passages only, under a daily spending cap set in the console, falling
back to the passages once the cap is reached. This runs `brain.widget_answers.written_answer` as
the widget route calls it, over the check's own application, with the product's own executor, price
book, spend ledger and tuning knob, and the model a stand-in that answers in the process.

**Four things are read.** With the switch off, as an install ships it, no model is asked and the
visitor gets the passages. With it on and a cap of one hundred minor units, the stand-in's answer is
written for the visitor and what it cost is on the spend ledger under the widget's own name and
department, three answers fit under the cap and the fourth is not asked; and what the model was
sent is the visitor's question and the public passages, with no tool among the request's fields.

**The model is a stand-in, and the proof is held for it.** What a stand-in cannot show is that a
real provider's reply stays within the passages, which is a property of a prompt and a model
together; what the check shows is what the model is sent and that the cap is counted and held. The
cap, the price and the switch are rolled back with the check's transaction, and the install's own
are never touched.

Task ids: M10.7.6, M10.7.7, M10.7.8
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

import httpx

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_routing import ANSWERS, STAND_IN_REPLY, StandIns, stand_in_drivers, step
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1510

# What the check says, one sentence for each way the property can fail.
ASKED_WITH_THE_SWITCH_OFF: Final = "the model was asked for a visitor with the switch off"
NO_MODEL_ANSWER: Final = "a visitor was not given the model's answer with the switch on"
NOT_WRITTEN_FROM_THE_PASSAGES: Final = (
    "the model was not sent the visitor's question and the public passage"
)
SENT_MORE_THAN_THE_PASSAGES: Final = "the model was sent a tool or something beside the passages"
COST_NOT_ON_THE_LEDGER: Final = "what a visitor's answer cost was not on the spend ledger"
CAP_NOT_HELD: Final = "the model was asked again once the day's cap was used up"
CAP_NOT_USED: Final = "the cap stopped the model before it was used up"

#: The cap the check sets, in minor units, and what the stand-in's three answers cost together.
CAP: Final = 100
ANSWER_COST: Final = 48
QUESTION: Final = "Acceptance question about opening hours"
PASSAGE_TEXT: Final = "Acceptance passage: the office opens at nine."


class _Recording(StandIns):
    """The stand-in model, keeping every request body it was sent."""

    def __init__(self) -> None:
        super().__init__()
        self.bodies: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content.decode("utf-8", "replace"))
        return super().__call__(request)


async def _priced(h: Harness) -> str:
    """The stand-in's model priced at one minor unit a token in the install's currency, in this
    transaction. Not run where the install's currency does not resolve."""
    from decimal import Decimal

    from brain.core.errors import Failed
    from brain.locale import NO_CURRENCY_CODE, LocaleError
    from brain.locale import currency as install_currency
    from brain.models.pricing import Price
    from brain.ops.acceptance_models import STAND_IN
    from brain.ops.price_store import set_price_statement

    try:
        code = install_currency()
    except (LocaleError, Failed):
        raise CheckNotRunError(
            "this install's currency does not resolve, so no cost can be counted against a cap"
        ) from None
    if code == NO_CURRENCY_CODE:
        raise CheckNotRunError(
            "this install has no currency set, so no cost can be counted against a cap"
        )
    price = Price(input_minor=Decimal(1_000_000), output_minor=Decimal(1_000_000), currency=code)
    await h.execute(*h.attributed(), set_price_statement(STAND_IN, ANSWERS, price, by=h.actor))
    return code


def _passages() -> tuple[Any, ...]:
    from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage

    return (
        KnowledgePassage(
            entity=KNOWLEDGE_ENTITY,
            id="acceptance.widget.0",
            document_id=f"acceptance-widget-{ANSWERS}",
            title="Opening hours",
            section="Hours",
            document=PASSAGE_TEXT,
        ),
    )


async def _app(h: Harness, responder: _Recording) -> FastAPI:
    from fastapi import FastAPI

    from brain.models.routing import Tier
    from brain.ops.acceptance_models import STAND_IN, askable, models_for, pinned
    from brain.ops.acceptance_routing import constrained

    await h.found_departments()
    await constrained(h, ())
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS, tier=Tier.SMALL),))
    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.models = models
    return app


@check(
    leaves=("M10.7.6", "M10.7.7", "M10.7.8"),
    sentence=(
        "With the switch off the website widget asks no model; with it on and a cap of one "
        "hundred, a visitor's question is answered by the model from the public passage alone, "
        "each answer's cost is on the spend ledger under the widget's own name, the third fits "
        "and the fourth is not asked."
    ),
)
async def the_widget_writes_from_public_passages_under_a_daily_cap(
    h: Harness,
) -> None:
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await _held(h)


async def _held(h: Harness) -> None:
    from sqlalchemy import select

    from brain.ops.acceptance_switch import switched
    from brain.ops.features import WIDGET_MODEL_ANSWERS
    from brain.ops.tuning import WIDGET_DAILY_SPEND
    from brain.tables.spend import SpendActualRow
    from brain.widget_answers import WIDGET_DEPARTMENT, WIDGET_SPENDER, written_answer

    await _priced(h)
    responder = _Recording()
    app = await _app(h, responder)
    from starlette.requests import Request

    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    saved = {WIDGET_DAILY_SPEND: CAP}
    passages = _passages()

    async def ask() -> str | None:
        return await written_answer(request, QUESTION, passages, saved=saved)

    await switched(h, WIDGET_MODEL_ANSWERS, on=False)
    if await ask() is not None or responder.bodies:
        raise CheckFailedError(ASKED_WITH_THE_SWITCH_OFF)

    await switched(h, WIDGET_MODEL_ANSWERS, on=True)
    first = await ask()
    if first != STAND_IN_REPLY:
        raise CheckFailedError(NO_MODEL_ANSWER)
    sent = json.loads(responder.bodies[-1])
    seen = json.dumps(sent.get("messages", []))
    if QUESTION not in seen or PASSAGE_TEXT not in seen:
        raise CheckFailedError(NOT_WRITTEN_FROM_THE_PASSAGES)
    if any(sent.get(field) for field in ("tools", "functions", "tool_choice")):
        raise CheckFailedError(SENT_MORE_THAN_THE_PASSAGES)

    again: list[Callable[[], Any]] = [ask, ask]
    for one in again:
        if await one() != STAND_IN_REPLY:
            raise CheckFailedError(CAP_NOT_USED)
    spent = (
        await h.execute(
            select(SpendActualRow.cost_minor, SpendActualRow.department).where(
                SpendActualRow.principal_id == WIDGET_SPENDER
            )
        )
    ).all()
    if len(spent) != 3 or {one.department for one in spent} != {WIDGET_DEPARTMENT}:
        raise CheckFailedError(COST_NOT_ON_THE_LEDGER)
    if sum(one.cost_minor for one in spent) != 3 * ANSWER_COST:
        raise CheckFailedError(COST_NOT_ON_THE_LEDGER)

    asked = len(responder.bodies)
    if await ask() is not None or len(responder.bodies) != asked:
        raise CheckFailedError(CAP_NOT_HELD)
