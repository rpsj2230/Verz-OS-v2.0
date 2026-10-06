"""The Learning screen's two figures: their bounds, what they reach, and the routes that set them.

The domain half holds each figure against something outside `brain.ops.tuning`: the half-life's
lower bound against the digest week and the weight an inference forms at, the agreement's upper
bound against the evidence an agent's rise in trust needs, and the tier map against every figure
either could hold. The holding half shows a held figure reaching the recall every surface asks and
the tier-two verdict the Learning screen draws, and a lent reading reaching its own task only. The
route half drives the real application with `ops.setting` held in memory: who may read and change,
a refusal that writes nothing, and a save that is in force at once.

Dates are pinned in 2019 for `tests/unit/test_scope_and_capability.py`'s reason: nothing here is
about the present, so no fixture here may expire.

Task ids: M16.6.8
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.console.reach_view import MINIMUM_CLEAN_RUNS, tier_two_rows
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory import tiers
from brain.memory.digest import DIGEST_PERIOD, Learning
from brain.memory.formation import (
    HALF_LIFE_DAYS,
    RECALL_FLOOR,
    Formation,
    MemoryKind,
    confidence_now,
    may_recall,
)
from brain.memory.tiers import (
    BLAST_RADIUS,
    PROMOTION_AGREEMENT,
    Change,
    Occurrence,
    Tier,
    blast_radius,
    may_promote,
    propose,
)
from brain.memory.turn import EXTRACTED_CONFIDENCE
from brain.ops import tuning
from brain.ops.tuning import (
    INFERRED_HALF_LIFE,
    KNOB_BY_NAME,
    NOT_A_KNOB,
    PROMOTION_AGREEMENT_KNOB,
    KnobKind,
)
from brain.settings_routes import INSTALL_SETTING_AUTHORITY
from brain.tables.config import SettingType
from brain.tuning_routes import LEARNING_SETTINGS_PATH, TUNING_PATH
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.setting_rows import SettingRows

NOW = datetime(2019, 6, 3, 9, 0, tzinfo=UTC)
CAP = "read:client_record"
WRITER = "u_writer"
SCREEN = f"{API_PREFIX}{LEARNING_SETTINGS_PATH}"
LIMITS = f"{API_PREFIX}{TUNING_PATH}"
HALF_LIFE = KNOB_BY_NAME[INFERRED_HALF_LIFE]
AGREEMENT = KNOB_BY_NAME[PROMOTION_AGREEMENT_KNOB]

GRANTS = {
    "u_admin": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.unrestricted()),),
    # A reader of the Learning screen: its capability, and the console plane admitting it.
    "u_wide": (
        Grant(capability=screen("learning").read.requires, scope=Scope.unrestricted()),
        Grant(capability=plane_capability(Plane.CONTENT), scope=Scope.unrestricted()),
    ),
    "u_narrow": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


@pytest.fixture(autouse=True)
def nothing_held() -> Iterator[None]:
    """Every test starts with nothing held and leaves what was held before it."""
    before = tuning.hold({})
    yield
    tuning.hold(before)


def reader() -> EntitlementSet:
    return EntitlementSet(
        principal_id=WRITER,
        grants=(Grant(capability=Capability(value=CAP), scope=Scope.unrestricted()),),
    )


def inference(at: datetime = NOW) -> Formation:
    return Formation(
        principal_id=WRITER,
        capabilities=(Capability(value=CAP),),
        scope=Scope.unrestricted(),
        ent_hash="0" * 32,
        formed_at=at,
        kind=MemoryKind.ADAPTIVE,
    )


def recalled(formation: Formation, days: float) -> bool:
    """Whether the writer would recall their own inference this many days after it formed."""
    return (
        may_recall(
            formation,
            reader(),
            now=formation.formed_at + timedelta(days=days),
            formed_confidence=EXTRACTED_CONFIDENCE,
        )
        is not None
    )


def conversations(*ids: str) -> tuple[Occurrence, ...]:
    return tuple(Occurrence(conversation_id=one, on=NOW - timedelta(days=1)) for one in ids)


def rule(memory_id: str = "m_rule") -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.FAST_PATH_RULE, subject=f"subject:{memory_id}"),
        formation=inference(NOW - timedelta(days=1)),
        agent_id="a_desk",
    )


# ------------------------------------------------------------------------ the knobs
def test_the_learning_figures_default_to_the_memory_package_s_own_and_are_the_only_two() -> None:
    """Held against `brain.memory`, which owns both figures. Delete this and a default can drift
    from the constant every test of decay and promotion reads, so an install that saved nothing
    decays at a rate no test ever looked at, or a third figure can be added to learning's list
    without anybody asking what tier it could reach."""
    assert HALF_LIFE.default == HALF_LIFE_DAYS
    assert AGREEMENT.default == PROMOTION_AGREEMENT
    assert [one.name for one in tuning.knobs_of(KnobKind.LEARNING)] == [
        INFERRED_HALF_LIFE,
        PROMOTION_AGREEMENT_KNOB,
    ]
    assert tuning.inferred_half_life_days() == HALF_LIFE_DAYS
    assert tuning.promotion_agreement() == PROMOTION_AGREEMENT


def test_the_shortest_half_life_is_the_shortest_that_keeps_a_week_s_inference_recalled() -> None:
    """**The lower bound is derived, and this proves it is the tightest one.** An inference forms
    at `EXTRACTED_CONFIDENCE` and the weekly digest offers to undo it up to `DIGEST_PERIOD` later;
    at the lowest half-life it is still above `RECALL_FLOOR` then, and one day shorter it is not.
    Delete this and the bound can be lowered until the digest lists inferences nobody is shown
    any more, whose undo button changes nothing."""

    def after_a_week(half_life: float) -> float:
        return confidence_now(
            EXTRACTED_CONFIDENCE,
            formed_at=NOW,
            now=NOW + DIGEST_PERIOD,
            half_life_days=half_life,
        )

    assert after_a_week(float(HALF_LIFE.lowest)) >= RECALL_FLOOR
    assert after_a_week(float(HALF_LIFE.lowest - 1)) < RECALL_FLOOR


def test_no_agreement_asks_more_of_a_rule_than_of_an_agent_s_rise_in_trust() -> None:
    """Held against `brain.console.reach_view.MINIMUM_CLEAN_RUNS`, the evidence a tier-three rung
    rise needs. Delete this and the upper bound can be raised past it, so a tier-two rule would
    need more agreement than a change that widens what an agent may do alone, which is the tier
    order upside down; or lowered to one, where one person's phrasing is a pattern."""
    assert AGREEMENT.highest <= MINIMUM_CLEAN_RUNS
    assert AGREEMENT.lowest >= 2


def test_no_learning_figure_on_any_install_can_lower_a_change_s_tier() -> None:
    """**The leaf's last clause, proved over every figure either knob admits.** The tier map is
    `blast_radius(change)`, a function of one parameter in a module that imports nothing from the
    settings, and at every admissible agreement only a tier-two change is ever promoted by
    agreement, however many conversations agree. Delete this and a setting could be threaded into
    the tier decision, or `may_promote` could start promoting a gated change once the agreement
    was lowered far enough, and no other test reads the two together."""
    assert list(inspect.signature(blast_radius).parameters) == ["change"]
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(Path(inspect.getfile(tiers)).read_text()))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(Path(inspect.getfile(tiers)).read_text()))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not [one for one in imported if one.startswith("brain.ops")], imported
    assert not [one.name for one in tuning.KNOBS if "tier" in one.name]

    plenty = conversations(*(f"c{n}" for n in range(MINIMUM_CLEAN_RUNS * 2)))
    before = dict(BLAST_RADIUS)
    for agreement in range(AGREEMENT.lowest, AGREEMENT.highest + 1):
        tuning.hold({PROMOTION_AGREEMENT_KNOB: agreement, INFERRED_HALF_LIFE: HALF_LIFE.lowest})
        for change in Change:
            promoted = may_promote(
                propose(change, subject="s"),
                plenty,
                now=NOW,
                agreement=tuning.promotion_agreement(),
            )
            assert promoted is (blast_radius(change) is Tier.PROMOTED), (agreement, change)
        assert dict(BLAST_RADIUS) == before


# ------------------------------------------------------------------------ what a figure reaches
def test_a_held_half_life_is_the_rate_every_recall_decays_an_inference_at() -> None:
    """**The figure reaches `may_recall`, which every surface asks.** At the product's figure an
    inference is recalled fifteen days on; at the shortest an administrator may save it is not,
    and a statement is recalled either way. Delete this and a saved figure can land in the table
    and the Memory screen, the digest and a model's hints all go on decaying at thirty days."""
    formed = inference()
    stated = Formation(
        principal_id=WRITER,
        capabilities=(Capability(value=CAP),),
        scope=Scope.unrestricted(),
        ent_hash="0" * 32,
        formed_at=NOW,
        kind=MemoryKind.PERSISTENT,
    )
    assert recalled(formed, 15)

    tuning.hold({INFERRED_HALF_LIFE: HALF_LIFE.lowest})

    assert not recalled(formed, 15)
    assert recalled(formed, tuning.inferred_lifetime_days(HALF_LIFE.lowest))
    assert may_recall(stated, reader(), now=NOW + timedelta(days=15)) is not None


def test_the_lifetime_the_screen_states_is_the_last_day_recall_admits_an_inference() -> None:
    """The sentence the Learning screen shows is `may_recall`'s answer, not a second formula.
    Delete this and the screen can say an inference lasts a week longer than recall keeps it."""
    for half_life in (HALF_LIFE.lowest, HALF_LIFE.default, HALF_LIFE.highest):
        tuning.hold({INFERRED_HALF_LIFE: half_life})
        days = tuning.inferred_lifetime_days(float(half_life))
        assert days == math.floor(half_life * math.log2(EXTRACTED_CONFIDENCE / RECALL_FLOOR))
        assert recalled(inference(), days)
        assert not recalled(inference(), days + 1)
        assert f"about {days} days" in tuning.lifetime_sentence()


def test_a_held_agreement_is_what_the_learning_screen_s_tier_two_verdict_counts_against() -> None:
    """Two conversations agreeing do not make a rule ready at the product's three, and do at a
    saved two. Delete this and the figure saved on the Learning screen reaches nothing the screen
    draws, because `tier_two_rows` went on counting against the constant."""
    seen = {"m_rule": conversations("c1", "c2")}

    def ready(agreement: int | None = None) -> bool:
        found = tier_two_rows(
            (rule(),), agent_id="a_desk", occurrences=seen, now=NOW, agreement=agreement
        )
        return found[0].promote_ready

    assert not ready()

    tuning.hold({PROMOTION_AGREEMENT_KNOB: 2})

    assert ready()
    assert not ready(3)


def test_a_reading_is_lent_to_the_task_that_asked_and_to_no_other() -> None:
    """**What makes an install check safe to run on a live install.** A task reading its own rows
    decides with them, a task running beside it at the same moment reads what is held, and the
    reading ends when its block does. Delete this and `reading` can be rewritten as a hold, and an
    install check's figure, saved in a transaction that is rolled back, would decide every request
    the process serves until the next reload."""
    tuning.hold({INFERRED_HALF_LIFE: 90})
    seen: dict[str, float] = {}
    lent = asyncio.Event()
    looked = asyncio.Event()

    async def lending() -> None:
        with tuning.reading({INFERRED_HALF_LIFE: HALF_LIFE.lowest}):
            lent.set()
            await looked.wait()
            seen["lending"] = tuning.inferred_half_life_days()
        seen["after"] = tuning.inferred_half_life_days()

    async def beside() -> None:
        await lent.wait()
        seen["beside"] = tuning.inferred_half_life_days()
        looked.set()

    async def both() -> None:
        await asyncio.gather(lending(), beside())

    asyncio.run(both())

    assert seen == {"lending": HALF_LIFE.lowest, "beside": 90.0, "after": 90.0}


# ------------------------------------------------------------------------ the routes
@pytest.fixture
def rows() -> SettingRows:
    return SettingRows()


@pytest.fixture
def served(rows: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(rows.answer)
        yield client, stub


def put(client: TestClient, pid: str, path: str, name: str, value: Any) -> Any:
    return client.put(f"{path}/{name}", json={"value": value}, headers=headers(pid))


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_who_may_neither_read_learning_nor_change_settings_is_refused_before_a_read(
    pid: str,
) -> None:
    """One refusal for the read and the write, with and without a database, and nothing sent to
    the database. Delete this and a department's administrator sets how long every department's
    inferences last."""
    for database in (True, False):
        with console_client(GRANTS, database=database) as (client, stub):
            assert get(client, pid, SCREEN).status_code == 404
            assert put(client, pid, SCREEN, INFERRED_HALF_LIFE, 20).status_code == 404
            assert stub.statements == []


def test_a_reader_of_learning_sees_its_two_figures_and_what_they_mean_and_may_not_change_one(
    served: tuple[TestClient, Stub],
) -> None:
    """The read is the Learning screen's and the write the Settings authority's; the figures are
    learning's alone and the answer says how long an inference lasts. Delete this and the console
    draws a control for somebody the write refuses, or lists the rate limits on the wrong screen."""
    client, stub = served
    body = get(client, "u_wide", SCREEN).json()
    assert body["may_change"] is False
    assert [one["name"] for one in body["knobs"]] == [INFERRED_HALF_LIFE, PROMOTION_AGREEMENT_KNOB]
    days = tuning.inferred_lifetime_days(HALF_LIFE_DAYS)
    assert f"about {days} days" in body["in_force"]
    assert put(client, "u_wide", SCREEN, INFERRED_HALF_LIFE, 20).status_code == 404
    assert stub.statements == []


def test_saving_a_half_life_writes_its_row_as_the_person_and_the_next_recall_decays_at_it(
    served: tuple[TestClient, Stub], rows: SettingRows
) -> None:
    """The whole path: the row under the namespace, typed as a whole number and written by the
    person, held by this process, and in force on the next recall and in the screen's sentence.
    Delete this and a save can land in the table and change nothing until a restart."""
    client, _ = served
    answer = put(client, "u_admin", SCREEN, INFERRED_HALF_LIFE, HALF_LIFE.lowest)
    assert answer.status_code == 200
    assert rows.writes == [
        {
            "key": f"tuning.{INFERRED_HALF_LIFE}",
            "value_type": SettingType.INTEGER.value,
            "value": HALF_LIFE.lowest,
            "updated_by": "u_admin",
        }
    ]
    knob = next(one for one in answer.json()["knobs"] if one["name"] == INFERRED_HALF_LIFE)
    assert (knob["value"], knob["saved"], knob["default"]) == (HALF_LIFE.lowest, True, 30)
    lasts = tuning.inferred_lifetime_days(float(HALF_LIFE.lowest))
    assert f"about {lasts} days" in answer.json()["in_force"]
    assert not recalled(inference(), 15)


def test_each_screen_refuses_the_other_s_figures_and_a_figure_outside_its_bounds(
    served: tuple[TestClient, Stub], rows: SettingRows
) -> None:
    """A rate limit is not set from Learning, a learning figure is not set from Rate limits, and
    neither is set outside its bounds or as anything but a whole number, each in words and with
    nothing written. Delete this and a half-life of one day can be saved, or a figure set from a
    screen that does not explain it."""
    client, stub = served
    refused = put(client, "u_admin", SCREEN, INFERRED_HALF_LIFE, HALF_LIFE.lowest - 1)
    assert refused.status_code == 422
    assert f"between {HALF_LIFE.lowest} and {HALF_LIFE.highest}" in refused.json()["message"]
    assert put(client, "u_admin", SCREEN, PROMOTION_AGREEMENT_KNOB, 1).status_code == 422
    assert put(client, "u_admin", SCREEN, PROMOTION_AGREEMENT_KNOB, "3").status_code == 422
    other = put(client, "u_admin", SCREEN, "person_per_minute", 12)
    assert (other.status_code, other.json()["message"]) == (422, NOT_A_KNOB)
    crossed = put(client, "u_admin", LIMITS, INFERRED_HALF_LIFE, 20)
    assert (crossed.status_code, crossed.json()["message"]) == (422, NOT_A_KNOB)
    assert rows.writes == []
    assert not [one for one in stub.statements if "INSERT" in str(one).upper()]


def test_the_rate_limits_screen_lists_no_learning_figure(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the Rate limits screen lists how long memories last among the request
    windows, set by the same control and explained by nothing."""
    client, _ = served
    body = get(client, "u_admin", LIMITS).json()
    names = {one["name"] for one in body["knobs"]}
    assert names == {one.name for one in tuning.KNOBS if one.kind in tuning.LIMIT_KINDS}
    assert not names & {INFERRED_HALF_LIFE, PROMOTION_AGREEMENT_KNOB}
