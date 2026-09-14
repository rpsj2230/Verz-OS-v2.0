"""A company arriving, and the dozen defaults that get decided while nobody is watching.

Onboarding is where a product finds out what it assumed. Every screen a new install shows in
its first week answers a question the client has not asked yet: which source to connect first,
what a good question looks like, how much coverage is enough, when a document counts as
trustworthy. Answer those in the module that draws the screen and the answers become facts
about the company that wrote it. `brain.ops.starter` already holds the four settings a new
install starts with and argues each one; this is the rest of the first week, and it has more
of them.

**The value here is not the sequence, it is the refusal to describe adoption as a percentage.**
The obvious onboarding module has a checklist and a progress bar, and both are wrong for the
same reason: they measure how much of this product has been switched on rather than how much
of the client's work it can answer for. A company with one connector covering the department
that asks the most questions is further along than one with five connectors and nobody asking.
So the outputs here are a coverage statement per scope and a shopping list of next actions,
and there is no ratio anywhere. See `A_PROGRESS_BAR_MEASURES_THE_PRODUCT_AND_NOT_THE_COMPANY`.

**A count is a disclosure, and this module produces counts for a living.** The platform's rule
is that DENIED and ABSENT are indistinguishable, and "coverage: 3 of 12 departments" tells a
reader there are nine departments they were not shown. So every function here takes the
reader's reach as a parameter, reports on what is inside it, and emits no total, no remainder
and no ratio. `coverage_gaps` refuses a statement that carries one.

**The reach arrives as a parameter and is never computed here.** `EntitlementSet.intersect` is
the one implementation of this platform's central rule and it has a pinned set of call sites.
An onboarding module narrowing a department list by hand would be a second, worse copy of that
narrowing, written by somebody thinking about a welcome screen. So the caller does the
intersection where it is already done and hands the result in, exactly as
`brain.ops.connections.undeclared_clients` takes connection strings somebody else parsed.

**Nothing here is a canned list.** The starter questions are built from the entities that
actually have records, the verification targets from the documents answers actually cite, and
the connector roadmap from what people actually asked and did not get. A canned first question
is a demonstration: it works on the day it is written, on the data it was written against, and
the first client whose data is shaped differently gets a question their system cannot answer,
in week one, which is the week that decides whether anybody comes back.

**Rejected: storing the unanswered questions.** A log of what people asked and did not get is
the most useful artefact in this module and it is a search history: it holds what somebody
wanted to know, in their words, under permissions belonging to whoever reads the roadmap.
`Unanswered` therefore holds a department and a source and no text at all, which is
`brain.ops.feedback`'s closed vocabulary argument arriving one surface earlier. See
`AN_UNANSWERED_QUESTION_LOG_THAT_KEEPS_THE_QUESTION_IS_A_SEARCH_HISTORY`.

**Adoption is measured in questions people asked, and the machine filter is not written here.**
Rollout wants a figure per department, and the cheap figure is runs: every row a ledger holds.
A nightly report, a webhook, an API key and an automation with nobody present all produce rows
and none of them is somebody in that department deciding the system is worth asking, so a
department whose champion installed three schedules would read as the keenest in the company.
Whether a row is a machine's is already one lookup, `brain.ops.limits.is_automated`, reading
the principal's kind and the traffic class its channel declared through
`brain.gate.context.traffic_class_for`. `Asked.machine` calls those two and decides nothing.
A second list of "machine channels" here would be right on the day it was written and wrong on
the day somebody added a channel, and it would be wrong in the direction of counting a robot.
See `A_ROW_IS_NOT_A_QUESTION_AND_A_SCHEDULE_IS_NOT_A_PERSON`.

**A question is a trace, not a row, which is how an agent handing work to another agent is
kept out.** `brain.orchestration.delegation.fan_out_request` admits every child of a run under
the root run's trace id, so a question that fanned out to four agents is five records and one
trace. Counting records would make the departments whose questions need delegation look five
times as engaged. A trace whose records disagree about who asked, from where or for which
department is refused rather than split, and it is refused before anything is narrowed to the
reader, so the refusal is the same for everybody and says nothing about what they may see. See
`A_HOP_IS_PART_OF_THE_QUESTION_THAT_STARTED_IT`.

**Two figures per department and no third.** Questions, and the number of distinct people who
asked them, because one enthusiast asking two hundred questions is not a department adopting
anything and the question count alone cannot tell the two apart. There is no headcount beside
them, no share and no total: a headcount is the denominator
`A_PROGRESS_BAR_MEASURES_THE_PRODUCT_AND_NOT_THE_COMPANY` refuses, and a count of machine rows
or of departments outside the reach is the hidden count with a label on it. Every reachable
department gets a line, zero included, so whether a line appears is a fact about the reader's
reach and never about what the excluded rows held. See
`AN_ADOPTION_LINE_IS_BUILT_FROM_PEOPLE_AND_THE_READERS_OWN_REACH_ONLY`.

**Nothing records an `Asked` yet, and M37.3.2.4 is not claimable for that reason.** The gate
is not assembled end to end (`brain.ops.lane_share` records the same absence), and neither
ledger that exists carries what a question count needs. `brain.ops.spend.Actual` has the
principal's kind, the traffic class and the department and no trace id, so a delegated question
counts once per hop; `brain.ops.telemetry.RequestTelemetry` has the trace id and no department
and no principal kind. Building the measure over `Actual` was rejected for exactly that: it
would ship a figure that treats agent hops as people. Evaluation traffic is the other open half.
Nothing in `src` asks a golden question yet (`brain.ops.evaluation` says why), so nothing marks
one either, and when a harness does it is excluded here only by recording its persona as a
`PrincipalKind.SERVICE`. See `AN_EVALUATION_RUN_IS_EXCLUDED_ONLY_BY_ASKING_AS_A_SERVICE`.

Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3, M34.2.1.1
Task ids: M34.2.2.3, M34.3.1.1, M34.3.1.2, M37.3.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, assert_never

from brain.core.principal import PrincipalKind
from brain.gate.context import Channel, traffic_class_for
from brain.install import value_of
from brain.locale import MESSAGES, PLACEHOLDER
from brain.ops.limits import is_automated
from brain.orchestration.unattended import TriggerKind

# ------------------------------------------------------------------ written-down reasons
#: Why there is no percentage anywhere in this module.
A_PROGRESS_BAR_MEASURES_THE_PRODUCT_AND_NOT_THE_COMPANY: Final = (
    "A completion figure counts how much of this product has been switched on, which is a "
    "fact about us. A company with one connector over the department that asks the most "
    "questions is further along than one with five and nobody asking, and the bar says the "
    "opposite. It also leaks: a denominator is a count of the things the reader was not "
    "shown. A shopping list has neither problem, because every line is an action somebody "
    "can take and there is no line for what is missing from their view."
)

#: Why the first connector cannot be one that needs an upload.
A_FIRST_CONNECTOR_THAT_NEEDS_AN_UPLOAD_HAS_NO_FIRST_ANSWER: Final = (
    "A document source answers nothing until somebody has chosen, uploaded, parsed and "
    "embedded a file, which is a week of work by the person who is least convinced. A "
    "record source answers on the day it is connected, from data that was already there, "
    "and the first answer is the whole argument for the second week."
)

#: Why a starter question has to be checkable.
AN_ANSWER_NOBODY_CAN_CHECK_IS_A_DEMONSTRATION: Final = (
    "The first answer a company sees is either evidence or theatre, and the difference is "
    "whether the person watching can open the system it came from and see the same figure. "
    "So a starter question names where to check it, and a source with nothing a person can "
    "open is not used for one, however good its data is."
)

#: Why a starter question is never invented.
A_STARTER_QUESTION_ABOUT_NOTHING_TEACHES_THAT_THE_SYSTEM_CANNOT_ANSWER: Final = (
    "A canned question works on the data it was written against. Asked against a client "
    "whose records are shaped differently it returns nothing, in week one, and what the "
    "room learns is that the system cannot answer questions. Fewer questions than asked for "
    "is the honest output; padding the list to three is how the failure gets built in."
)

#: Why a not-connected department is a state rather than a zero.
A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS: Final = (
    "Rendering both as 0 tells a department that the system looked and found nothing, when "
    "it never looked. The two need different actions from different people: one is a "
    "connector somebody has to authorise, the other is data somebody has to enter. A "
    "coverage view that cannot tell them apart sends every question to the wrong person."
)

#: Why the log holds no question text.
AN_UNANSWERED_QUESTION_LOG_THAT_KEEPS_THE_QUESTION_IS_A_SEARCH_HISTORY: Final = (
    "What somebody asked and did not get is the most sensitive line in this system: it is a "
    "statement of what they were trying to find out, held under whoever reads the roadmap "
    "rather than under the asker. The roadmap needs which source was missing and for which "
    "department, and it needs nothing else, so there is no field for the rest."
)

#: Why the five documents are the cited ones.
VERIFYING_WHAT_NOBODY_ASKS_ABOUT_BUYS_NOTHING: Final = (
    "The obvious five are the five most recently uploaded, which are the five the lead has "
    "already read. The five worth an hour are the ones answers are already built from, "
    "because those are the passages a wrong document is being quoted through, and every "
    "unverified citation is a wrong answer waiting for somebody to act on it."
)

#: Why the privacy posture is derived rather than written.
A_PRIVACY_STATEMENT_WRITTEN_BY_HAND_IS_TRUE_ON_THE_DAY_IT_IS_WRITTEN: Final = (
    "A page saying that questions never leave the client's network is a sentence somebody "
    "typed, and it stays on the screen after an administrator switches the model profile to "
    "a hosted provider. Read off the configuration it cannot say that: the same setting "
    "that sends the text away changes the sentence, and there is no version of the page "
    "that is confidently wrong."
)

#: Why nothing here lists what a reader cannot reach.
A_LIST_OF_WHAT_YOU_CANNOT_SEE_IS_THE_MAP_YOU_WERE_NOT_GIVEN: Final = (
    "The plain-language explanation people ask for is a list of what the system holds and "
    "what they may have of it, and the second half of that is the whole disclosure. What is "
    "safe is the first person's own reach and the rule that governs the rest, stated as a "
    "rule: nothing outside is listed, and finding nothing is never evidence of a refusal."
)


class AdoptionError(Exception):
    """Raised when a first week is described in a way that would be wrong or would disclose."""


# ------------------------------------------------------------------ choosing the first source
class SourceKind(enum.StrEnum):
    """What a connector brings, which decides how soon it can answer anything.

    Two members and no `MIXED`. A source that holds both is declared as `RECORDS` when its
    records are what a question would reach, because the choice this enum drives is "can
    this answer something on the day it is connected", and half a source that can is a
    source that can.
    """

    #: Rows that exist already: tickets, invoices, deals, projects.
    RECORDS = "records"
    #: Files that have to be chosen, uploaded, parsed and embedded before anything is asked.
    DOCUMENTS = "documents"


@dataclass(frozen=True)
class ConnectorOffer:
    """One source this install could connect, described by what it would buy in week one.

    No vendor is named anywhere in this module. The fields are the properties that decide
    the order, and a client running something nobody here has heard of gets the same
    decision from the same rule.
    """

    name: str
    kind: SourceKind
    #: The departments whose questions this source could answer.
    departments: tuple[str, ...]
    #: Whether a person can open this source and see the same figure the answer gave.
    checkable_in_its_own_interface: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a connector offer with no name cannot be chosen or refused"
            raise AdoptionError(msg)
        if not self.departments:
            msg = f"{self.name} reaches no department, so connecting it answers nobody"
            raise AdoptionError(msg)


def first_connector(offers: Sequence[ConnectorOffer]) -> ConnectorOffer:
    """Which source to connect first, so a real question is answerable before any upload.

    Three criteria in a stated order, and the order is the decision. Records before
    documents, because a document source answers nothing until somebody has uploaded
    something: see `A_FIRST_CONNECTOR_THAT_NEEDS_AN_UPLOAD_HAS_NO_FIRST_ANSWER`. Then
    checkable before not, because the first answer is either evidence or theatre. Then the
    widest reach, because the first connector should put the system in front of the most
    people who could ask it something. Ties break on the name so two runs agree.

    Raises when every offer is a document source. That is a refusal rather than a fallback
    because the fallback is a first week spent uploading files, which is the failure this
    function exists to prevent, and it should be a conversation rather than a default.
    """
    if not offers:
        msg = "there is nothing to connect, so there is no first connector to choose"
        raise AdoptionError(msg)
    answerable = [one for one in offers if one.kind is SourceKind.RECORDS]
    if not answerable:
        msg = (
            "every offered source holds documents rather than records, so nothing can be "
            "answered until somebody uploads a file. "
            f"{A_FIRST_CONNECTOR_THAT_NEEDS_AN_UPLOAD_HAS_NO_FIRST_ANSWER}"
        )
        raise AdoptionError(msg)
    return sorted(
        answerable,
        key=lambda one: (
            not one.checkable_in_its_own_interface,
            -len(one.departments),
            one.name,
        ),
    )[0]


# ------------------------------------------------------------------ what is actually there
class Coverage(enum.StrEnum):
    """What one department's source is doing, as a value and never as a colour.

    Three members because two would collapse the distinction that matters. See
    `A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS`, and
    `brain.locale.A_STATUS_THAT_IS_A_COLOUR_HAS_DECIDED_THE_READER_CAN_SEE_IT` for why this
    is a named state with a message key rather than a tone the console picks.
    """

    NOT_CONNECTED = "not_connected"
    CONNECTED_NO_RECORDS = "connected_no_records"
    CONNECTED = "connected"


#: What each state is called on a screen, in whichever language the reader has.
#:
#: Message keys rather than sentences: a state rendered from an English string in this
#: module is a state that is English for everybody, and the reader who needed the other
#: language is the one who cannot tell "not connected" from "connected, nothing found".
COVERAGE_MESSAGE: Final[Mapping[Coverage, str]] = {
    Coverage.NOT_CONNECTED: "coverage.not_connected",
    Coverage.CONNECTED_NO_RECORDS: "coverage.connected_no_records",
    Coverage.CONNECTED: "coverage.connected",
}


@dataclass(frozen=True)
class ScopeCoverage:
    """What one source holds for one department, as it stands.

    `records` and `last_sync` are both optional and they are optional together: a source
    that has never synced has no count and no time, and a count of zero from a sync that ran
    is a different fact from no sync at all.
    """

    department: str
    source: str
    connected: bool
    records: int | None = None
    last_sync: datetime | None = None
    #: The entities that came back with rows, most populated first. Drives the questions.
    entities: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.department.strip() or not self.source.strip():
            msg = "a coverage row needs a department and a source to be about"
            raise AdoptionError(msg)
        if not self.connected and (self.records is not None or self.last_sync is not None):
            msg = (
                f"{self.source} is not connected for {self.department} and carries a count or "
                "a sync time, which is a row describing two different states at once"
            )
            raise AdoptionError(msg)
        if self.records is not None and self.records < 0:
            msg = f"{self.source} reports {self.records} records for {self.department}"
            raise AdoptionError(msg)
        if (self.records is None) != (self.last_sync is None):
            msg = (
                f"{self.source} has a count without a sync time or the other way round, and "
                "a count nobody can date is a figure that ages without saying so"
            )
            raise AdoptionError(msg)
        if any(count <= 0 for _, count in self.entities):
            msg = f"{self.source} lists an entity with no rows, which is not something indexed"
            raise AdoptionError(msg)

    @property
    def state(self) -> Coverage:
        """The three-way state. See `A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS`."""
        if not self.connected:
            return Coverage.NOT_CONNECTED
        if not self.records:
            return Coverage.CONNECTED_NO_RECORDS
        return Coverage.CONNECTED


def coverage_report(
    rows: Sequence[ScopeCoverage], reachable: frozenset[str]
) -> tuple[ScopeCoverage, ...]:
    """Every coverage row inside the reader's own reach, and nothing about the rest.

    The reach arrives as a set of department names the caller has already narrowed with
    `EntitlementSet.intersect`, for the reason given in the header: there is one
    implementation of that narrowing and this is not it.

    **No total accompanies the result and no remainder is available from it.** A caller that
    wanted "showing 4 of 11" would have to count the rows it did not pass in, which is the
    disclosure stated in `CLAUDE.md` and the one that arrives by subtraction rather than by
    anybody printing it.
    """
    return tuple(
        sorted(
            (one for one in rows if one.department in reachable),
            key=lambda one: (one.department, one.source),
        )
    )


def coverage_gaps(rendered: Sequence[str]) -> tuple[str, ...]:
    """Every line of a rendered coverage view that says more than it may.

    A ratio, a fraction and the word "of" between two numbers, which are the three shapes a
    progress figure arrives in. Takes the rendered lines rather than the rows, because the
    disclosure is made by whatever writes the sentence and the rows themselves carry no
    total to leak. See `A_PROGRESS_BAR_MEASURES_THE_PRODUCT_AND_NOT_THE_COMPANY`.
    """
    findings: list[str] = []
    for line in rendered:
        words = line.replace("%", " % ").split()
        if "%" in words:
            findings.append(f"{line!r} states a percentage, which is a denominator by another name")
        for index, word in enumerate(words):
            if word != "of" or index == 0 or index + 1 >= len(words):
                continue
            if words[index - 1].isdigit() and words[index + 1].isdigit():
                findings.append(
                    f"{line!r} says how many of how many, and the difference is a count of "
                    "things this reader was not shown"
                )
    return tuple(findings)


# ------------------------------------------------------------------ the first questions
#: The question shapes a record source can answer on the day it is connected.
#:
#: Three, and each is answerable from a count or a date rather than from prose, so the first
#: answers do not depend on retrieval quality at all. That is the point: week one is testing
#: whether the connection is real, and a question needing good retrieval conflates two
#: failures the client cannot tell apart.
QUESTION_SHAPES: Final[tuple[str, ...]] = (
    "starter.how_many",
    "starter.most_recent",
    "starter.changed_this_week",
)

#: How many starter questions one department is offered.
#:
#: Three, matching the shapes above, because the list is one per shape rather than a number
#: somebody liked: a fourth would repeat a shape against a second entity and teach that the
#: system answers one kind of question well.
STARTER_QUESTIONS: Final = 3


@dataclass(frozen=True)
class StarterQuestion:
    """One question a department can ask on day one, and where to check the answer.

    `check_in` is required and non-blank, which is
    `AN_ANSWER_NOBODY_CAN_CHECK_IS_A_DEMONSTRATION` made structural: there is no way to
    build a starter question that cannot be verified, so a source with no interface a person
    can open cannot produce one however good its data is.
    """

    department: str
    entity: str
    shape: str
    #: The system a person opens to see the same figure. Never this one.
    check_in: str

    def __post_init__(self) -> None:
        if self.shape not in MESSAGES:
            msg = f"{self.shape!r} is not a message, so the question renders in no language"
            raise AdoptionError(msg)
        if not self.entity.strip():
            msg = "a starter question about no entity has nothing to ask about"
            raise AdoptionError(msg)
        if not self.check_in.strip():
            msg = (
                f"the question about {self.entity} names nowhere to check the answer. "
                f"{AN_ANSWER_NOBODY_CAN_CHECK_IS_A_DEMONSTRATION}"
            )
            raise AdoptionError(msg)


def starter_questions(
    rows: Sequence[ScopeCoverage],
    department: str,
    *,
    checkable: frozenset[str],
    wanted: int = STARTER_QUESTIONS,
) -> tuple[StarterQuestion, ...]:
    """The questions this department can ask, built from what actually indexed.

    Generated from the entities that came back with rows, most populated first, and never
    from a list written here. Fewer than `wanted` is a correct answer and is what a thin
    first sync should produce: see
    `A_STARTER_QUESTION_ABOUT_NOTHING_TEACHES_THAT_THE_SYSTEM_CANNOT_ANSWER`.

    `checkable` names the sources a person can open. A source not in it contributes no
    questions rather than contributing unverifiable ones, which is the same refusal
    `StarterQuestion` makes at construction, applied before anything is built.
    """
    if wanted < 1:
        msg = "a department offered no starter question has nothing to try on day one"
        raise AdoptionError(msg)
    candidates: list[tuple[int, str, str]] = []
    for row in rows:
        if row.department != department or row.source not in checkable:
            continue
        candidates.extend((count, entity, row.source) for entity, count in row.entities)
    candidates.sort(key=lambda one: (-one[0], one[1]))
    return tuple(
        StarterQuestion(department=department, entity=entity, shape=shape, check_in=source)
        for (_, entity, source), shape in zip(candidates[:wanted], QUESTION_SHAPES, strict=False)
    )


# ------------------------------------------------------------------ the shopping list
class Need(enum.StrEnum):
    """What one action would change, as a closed value rather than as a sentence.

    **The first version of this carried the sentence.** It was English prose built in the
    domain layer, on a screen this install offers in two languages, and it let a caller
    construct an action whose stated benefit was a space. Two members and a message key each
    is the same argument `Coverage` makes: a state a screen renders is a value with a word
    for it, and the word lives where every other word does.
    """

    #: Nobody has connected this source, so the department cannot ask about it at all.
    AUTHORISE_THE_SOURCE = "authorise_the_source"
    #: It is connected and returned nothing, so the scope is wrong or the records moved.
    FIND_OUT_WHY_IT_IS_EMPTY = "find_out_why_it_is_empty"


#: What each need is called on a screen, in whichever language the reader has.
NEED_MESSAGE: Final[Mapping[Need, str]] = {
    Need.AUTHORISE_THE_SOURCE: "action.authorise_the_source",
    Need.FIND_OUT_WHY_IT_IS_EMPTY: "action.find_out_why_it_is_empty",
}

#: Which need each unfinished coverage state produces.
#:
#: A table rather than a branch, and the difference is not style. As a branch, the two arms
#: differed only in the sentence they built, so a mutation collapsing them into one produced
#: two actions that still read differently because each interpolated its own department name.
#: A table cannot be collapsed that way: `shopping_list` looks the need up and has no
#: opinion, and the property that the two states need different people is asserted here,
#: once, where it can be read. See `A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS`.
NEED_FOR: Final[Mapping[Coverage, Need]] = {
    Coverage.NOT_CONNECTED: Need.AUTHORISE_THE_SOURCE,
    Coverage.CONNECTED_NO_RECORDS: Need.FIND_OUT_WHY_IT_IS_EMPTY,
}


@dataclass(frozen=True)
class Action:
    """One thing the champion could do next, and which of the two kinds of work it is."""

    department: str
    source: str
    need: Need

    def __post_init__(self) -> None:
        if not self.department.strip() or not self.source.strip():
            msg = "an action needs a department and a source to be about"
            raise AdoptionError(msg)


def shopping_list(
    rows: Sequence[ScopeCoverage],
    reachable: frozenset[str],
    demand: Mapping[tuple[str, str], int] | None = None,
) -> tuple[Action, ...]:
    """What is worth doing next, in the order it is worth doing it (M34.1.2.3).

    Ordered by how many unanswered questions the connection would have answered, which is
    the only ordering that is about the company rather than about the product. Rows with no
    recorded demand come after those with some, alphabetically, so the list is stable rather
    than arbitrary when nothing has been asked yet.

    A finished scope produces nothing and the two unfinished ones produce different needs,
    which `NEED_FOR` decides rather than this function.
    """
    wanted = demand or {}
    actions: list[tuple[int, str, str, Action]] = []
    for row in rows:
        if row.department not in reachable or row.state not in NEED_FOR:
            continue
        asked = wanted.get((row.department, row.source), 0)
        actions.append(
            (
                -asked,
                row.department,
                row.source,
                Action(row.department, row.source, NEED_FOR[row.state]),
            )
        )
    return tuple(one for *_, one in sorted(actions, key=lambda one: one[:3]))


# ------------------------------------------------------------------ the verification ritual
#: How many documents one department lead verifies in the first week.
#:
#: Five. Small enough that somebody with a job will actually finish it, which is the only
#: property that matters: a target of twenty is a target that is missed, and a ritual that
#: is missed in week one teaches that targets here are decoration. Five citations checked is
#: also enough to find a wrong document if there is one, because the five are the most cited
#: rather than five at random.
WEEK_ONE_TARGET: Final = 5


@dataclass(frozen=True)
class CitedItem:
    """One knowledge item and how much weight answers are already putting on it."""

    item_id: str
    department: str
    citations: int
    verified: bool

    def __post_init__(self) -> None:
        if self.citations < 0:
            msg = f"{self.item_id} is cited {self.citations} times"
            raise AdoptionError(msg)


def verification_targets(
    items: Sequence[CitedItem], department: str, *, target: int = WEEK_ONE_TARGET
) -> tuple[CitedItem, ...]:
    """The documents this lead should check first, most-cited first (M34.2.1.1).

    Unverified items only, inside one department, ordered by how often answers already quote
    them. See `VERIFYING_WHAT_NOBODY_ASKS_ABOUT_BUYS_NOTHING`. An item nothing cites is not
    offered at all, because verifying it changes no answer and the hour is better spent.

    Returns fewer than the target when there are fewer, and the shortfall is not padded with
    uncited documents: a lead who verifies two documents and is told they are done has done
    the whole of what was worth doing.
    """
    if target < 1:
        msg = "a week-one target of nothing is a ritual with no act in it"
        raise AdoptionError(msg)
    return tuple(
        sorted(
            (
                one
                for one in items
                if one.department == department and not one.verified and one.citations > 0
            ),
            key=lambda one: (-one.citations, one.item_id),
        )[:target]
    )


# ------------------------------------------------------------------ correcting an answer
@dataclass(frozen=True)
class ChannelSurface:
    """One place answers are delivered, and whether a wrong one can be corrected from it."""

    name: str
    corrects: bool


def correction_gaps(channels: Sequence[ChannelSurface]) -> tuple[str, ...]:
    """Every channel where a wrong answer cannot be reported from where it was read.

    **A correction path that exists only in the console is a correction path for the people
    who use the console**, which is not who reads most answers. Somebody who gets a wrong
    answer in a chat message and would have to open a different application to say so does
    not say so, and the wrong document stays cited. The check is per channel because that is
    where the omission happens: a channel is added, it delivers answers on the first day,
    and the feedback affordance is the second commit that nobody wrote.
    """
    return tuple(
        f"{one.name}: an answer read here cannot be corrected from here, so a wrong "
        "document stays cited for everybody who reads it in this channel"
        for one in sorted(channels, key=lambda one: one.name)
        if not one.corrects
    )


# ------------------------------------------------------------------ the connector roadmap
@dataclass(frozen=True)
class Unanswered:
    """One question that could not be answered, with the question left out.

    **Two fields and no text.** See
    `AN_UNANSWERED_QUESTION_LOG_THAT_KEEPS_THE_QUESTION_IS_A_SEARCH_HISTORY`. What the
    roadmap needs is which source would have answered and for whom; what a text field would
    add is a record of what somebody was trying to find out, kept under the permissions of
    whoever reads the roadmap rather than of whoever asked.
    """

    department: str
    #: The source that would have held the answer.
    missing_source: str

    def __post_init__(self) -> None:
        if not self.department.strip() or not self.missing_source.strip():
            msg = "an unanswered row needs a department and a source, and holds nothing else"
            raise AdoptionError(msg)


def connector_demand(
    rows: Sequence[Unanswered], reachable: frozenset[str]
) -> Mapping[tuple[str, str], int]:
    """How often each missing source was wanted, per department, inside the reader's reach.

    Keyed by the pair rather than by the source alone, because "sales wanted this eleven
    times" is an argument a champion can take to the person who owns that system, and
    "eleven times somewhere" is not.

    Rows outside the reach are not counted rather than counted anonymously. A total that
    included them would be a number the reader could compare against their own departments'
    figures and read the remainder off, which is the subtraction disclosure again.
    """
    counted: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.department not in reachable:
            continue
        key = (row.department, row.missing_source)
        counted[key] = counted.get(key, 0) + 1
    return counted


# ------------------------------------------------------------------ what to tell the staff
@dataclass(frozen=True)
class Sentence:
    """One line of a plain-language explanation: a catalogue key and what fills it.

    **Not a string, and the difference is the whole of "in plain language" here.** A
    sentence built in this module would be English on an install that offers two languages,
    on the page whose entire purpose is that everybody understands it. A key plus its fills
    is a sentence in whichever language the reader has, and `catalogue_gaps` has already
    proved the key exists in all of them.

    The fills have to match the message's placeholders exactly. Too few renders a sentence
    with a value silently missing or raises inside the renderer; too many is a value
    somebody meant to show and did not, which is the same defect facing the other way.
    """

    key: str
    fills: Mapping[str, str]

    def __post_init__(self) -> None:
        entries = MESSAGES.get(self.key)
        if entries is None:
            msg = f"{self.key!r} is not a message, so this sentence renders in no language"
            raise AdoptionError(msg)
        expected = {name for one in entries.values() for name in PLACEHOLDER.findall(one)}
        if expected != set(self.fills):
            msg = (
                f"{self.key} takes {sorted(expected)} and was given {sorted(self.fills)}, so "
                "the sentence renders with a value missing or with one nobody shows"
            )
            raise AdoptionError(msg)


def visibility_summary(reachable: Sequence[str]) -> tuple[Sentence, ...]:
    """What a person may ask about, in plain language, and nothing about the rest.

    Two sentences and no third. The first names the reader's own departments, which they
    already know. The second states the rule that governs everything else, as a rule:
    nothing outside is listed anywhere, and finding nothing is never evidence of a refusal.
    See `A_LIST_OF_WHAT_YOU_CANNOT_SEE_IS_THE_MAP_YOU_WERE_NOT_GIVEN`.

    **The only variable content is the reader's own reach**, which is what makes this safe
    to render to anybody. There is no parameter naming what exists elsewhere, so there is no
    version of this page that could be built with a wider list by a caller who had one.
    """
    if not reachable:
        msg = (
            "a person who can reach nothing has no summary to be shown, and rendering an "
            "empty one would tell them there is something to reach and that it is not theirs"
        )
        raise AdoptionError(msg)
    return (
        Sentence("visibility.can_reach", {"departments": ", ".join(sorted(reachable))}),
        Sentence("visibility.rule", {}),
    )


def privacy_posture(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """What this install actually does with what people type, read off its configuration.

    Three statements, each derived from a setting rather than written down. See
    `A_PRIVACY_STATEMENT_WRITTEN_BY_HAND_IS_TRUE_ON_THE_DAY_IT_IS_WRITTEN`: the value of
    this function is not the sentences, it is that switching `INSTALL_MODEL_PROFILE` to a
    hosted provider changes the page, so there is no configuration in which the page is
    confidently wrong.

    Every value is read through `brain.install.value_of`, which is the one reader of an
    installation value in this repository.
    """
    profile = value_of("INSTALL_MODEL_PROFILE", env).strip().lower()
    brokered = value_of("INSTALL_BROKERED_DIRECTORY", env).strip().lower()
    model = "posture.model_local" if profile == "local" else "posture.model_hosted"
    directory = "posture.directory_own" if brokered == "none" else "posture.directory_brokered"
    return (model, directory, "posture.entitled")


def posture_gaps(keys: Sequence[str]) -> tuple[str, ...]:
    """Every posture statement that is not in the catalogue, so none is English-only.

    Separate from `brain.locale.catalogue_gaps` because that one checks the catalogue is
    complete and this one checks that what is announced is in it. A key that exists in one
    language and is announced anyway would pass the first check by being absent from it.
    """
    return tuple(
        f"{one!r} is stated as a posture and is not in the catalogue"
        for one in keys
        if one not in MESSAGES
    )


# ------------------------------------------------------------------ adoption (M37.3.2.4)
#: Why rows are not counted and the machine test is imported rather than written.
A_ROW_IS_NOT_A_QUESTION_AND_A_SCHEDULE_IS_NOT_A_PERSON: Final = (
    "A scheduled report, a webhook, an API key and an automation with nobody present all "
    "produce the rows a ledger holds, and none of them is somebody in a department deciding "
    "the system is worth asking. Whether a row is a machine's is already one lookup over the "
    "principal's kind and the traffic class its channel declared, so this module calls that "
    "lookup. A second list of machine channels would be right until somebody added a channel, "
    "and then wrong in the direction of counting a robot as a person."
)

#: Why a question is a trace and a delegation is not another question.
A_HOP_IS_PART_OF_THE_QUESTION_THAT_STARTED_IT: Final = (
    "An agent handing work to another agent admits the child under the root run's trace id, "
    "so one question that fanned out is several records and one trace. Counting records makes "
    "the departments whose questions need delegation look several times as engaged. A trace "
    "whose records disagree about who asked, from where or for which department is refused "
    "rather than split, because either answer would be a guess about which record is the "
    "question."
)

#: Why every line is a function of people's questions and the reader's reach and nothing else.
AN_ADOPTION_LINE_IS_BUILT_FROM_PEOPLE_AND_THE_READERS_OWN_REACH_ONLY: Final = (
    "A line appearing only for departments that had some traffic would appear for one that "
    "had nothing but a schedule, which tells the reader a schedule exists. So every reachable "
    "department has a line, zero included, and no line exists for anything outside the reach. "
    "There is no total, no headcount and no share beside the figures: a headcount is a "
    "denominator, and a count of what was excluded is the hidden count with a label on it."
)

#: Why evaluation traffic has no field of its own.
AN_EVALUATION_RUN_IS_EXCLUDED_ONLY_BY_ASKING_AS_A_SERVICE: Final = (
    "Nothing asks a golden question yet, so nothing marks one. A flag on the record saying "
    "'this was a test' would be a boolean a caller sets and a second answer to whether "
    "anybody was asking. The answer that already exists is the principal's kind: a harness "
    "that records its personas as service principals is excluded by the same lookup as every "
    "other machine, and one that records them as people is counted, which is a defect in the "
    "harness and not something this module could detect."
)


def channel_for_trigger(trigger: TriggerKind) -> Channel:
    """The channel a run started with nobody present is recorded as arriving on.

    `assert_never` for the reason `brain.gate.context.traffic_class_for` gives: a fourth kind
    of trigger is a type error here until somebody says where its runs enter, and a mapping
    with a default would pick one silently.

    The split is who starts the run. A webhook is somebody outside calling an endpoint, which
    is `Channel.WEBHOOK`. A schedule and a connector event are both this install's own worker
    starting work, one on a clock and one on a change it noticed, which is
    `Channel.SCHEDULER`. Both channels are machine traffic whichever principal the automation
    runs as, and that, rather than the split, is the property the tests hold.

    This names where the run is *recorded* for counting. Which verbs a channel may use is
    `brain.gate.admission.CHANNEL_VERBS`'s decision and is not taken here.
    """
    match trigger:
        case TriggerKind.WEBHOOK:
            return Channel.WEBHOOK
        case TriggerKind.SCHEDULE | TriggerKind.CONNECTOR_EVENT:
            return Channel.SCHEDULER
        case _:
            assert_never(trigger)


@dataclass(frozen=True)
class Asked:
    """One record of a question reaching the gate, holding only what adoption counts by.

    No question text, on `AN_UNANSWERED_QUESTION_LOG_THAT_KEEPS_THE_QUESTION_IS_A_SEARCH_HISTORY`.
    A channel rather than a traffic class, because the channel is the origin and the class is
    `traffic_class_for`'s declaration about it: a record carrying the class could say a
    scheduler run was interactive. The department is supplied by whoever records the question,
    where it is known, and never looked up here.

    Whether it was a machine is derived and never stored, exactly as `brain.ops.spend.Actual`
    derives it. See `A_ROW_IS_NOT_A_QUESTION_AND_A_SCHEDULE_IS_NOT_A_PERSON`.
    """

    #: The request's trace id. Every record of a delegated question shares the root's.
    trace_id: str
    principal_id: str
    principal_kind: PrincipalKind
    channel: Channel
    department: str
    at: datetime

    def __post_init__(self) -> None:
        for label, value in (
            ("trace_id", self.trace_id),
            ("principal_id", self.principal_id),
            ("department", self.department),
        ):
            if not value.strip():
                msg = f"a question record with no {label} cannot be counted or attributed"
                raise AdoptionError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant lands a question in the wrong window at either end of a day"
            raise AdoptionError(msg)

    @property
    def machine(self) -> bool:
        """Whether nobody was asking. `limits.is_automated` over the declared class."""
        return is_automated(self.principal_kind, traffic_class_for(self.channel))


@dataclass(frozen=True)
class DepartmentAdoption:
    """How one department used the system over a window: questions, and who asked them.

    Three fields, and there is nowhere to put a fourth figure. See
    `AN_ADOPTION_LINE_IS_BUILT_FROM_PEOPLE_AND_THE_READERS_OWN_REACH_ONLY`.
    """

    department: str
    #: Distinct questions people asked, one per trace.
    questions: int
    #: Distinct people who asked them.
    people: int

    def __post_init__(self) -> None:
        # No separate check that questions is not negative: people is refused below zero and
        # above questions, so a negative question count is already refused by one of the two,
        # and a third check would be a branch no test could reach on its own.
        if self.people < 0:
            msg = f"{self.department} reports {self.people} people asking"
            raise AdoptionError(msg)
        if self.people > self.questions:
            msg = f"{self.department} has more people asking than questions asked"
            raise AdoptionError(msg)
        if self.questions and not self.people:
            msg = f"{self.department} has questions that nobody asked"
            raise AdoptionError(msg)


def adoption_by_department(
    asked: Sequence[Asked],
    reachable: frozenset[str],
    *,
    start: datetime,
    end: datetime,
) -> tuple[DepartmentAdoption, ...]:
    """Questions people asked, per department in the reader's reach, over `[start, end)`.

    In three steps and the order is the argument.

    First every trace is checked and dated, over every record handed in. One trace is one
    question, dated by its earliest record because a delegated child finishes after the run
    that started it. A trace whose records disagree about the asker, the principal's kind, the
    channel or the department is refused. See `A_HOP_IS_PART_OF_THE_QUESTION_THAT_STARTED_IT`.
    This happens before the reach is applied so that the refusal is the same for every
    reader, and a reader cannot learn anything by getting one.

    Then machine traces are removed, once, before either figure is counted, so questions and
    people are drawn from one population.

    Then each reachable department gets a line, sorted by name, zero included, and nothing
    outside the reach is counted or mentioned. The reach arrives already narrowed, as it does
    for `coverage_report`, and should be the same usage grant
    `brain.console.spend_view.may_read_spend` answers, so this screen and the usage screen
    cannot disagree about who may know how much a department asked.
    """
    if start.tzinfo is None or end.tzinfo is None:
        msg = "a window with a naive edge moves by the server's offset"
        raise AdoptionError(msg)
    if start >= end:
        msg = f"a window from {start} to {end} holds no instant, so it measures nothing"
        raise AdoptionError(msg)
    first: dict[str, Asked] = {}
    for one in asked:
        seen = first.get(one.trace_id)
        if seen is None:
            first[one.trace_id] = one
            continue
        if (seen.principal_id, seen.principal_kind, seen.channel, seen.department) != (
            one.principal_id,
            one.principal_kind,
            one.channel,
            one.department,
        ):
            msg = (
                f"trace {one.trace_id!r} has records that disagree about who asked, from "
                f"where or for which department. {A_HOP_IS_PART_OF_THE_QUESTION_THAT_STARTED_IT}"
            )
            raise AdoptionError(msg)
        if one.at < seen.at:
            first[one.trace_id] = one
    questions = dict.fromkeys(reachable, 0)
    people: dict[str, set[str]] = {department: set() for department in reachable}
    for question in first.values():
        if question.machine or question.department not in reachable:
            continue
        if not start <= question.at < end:
            continue
        questions[question.department] += 1
        people[question.department].add(question.principal_id)
    return tuple(
        DepartmentAdoption(department, questions[department], len(people[department]))
        for department in sorted(reachable)
    )
