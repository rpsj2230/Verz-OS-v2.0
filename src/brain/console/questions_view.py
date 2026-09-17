"""Questions and gaps, as one reader may be shown them: the gaps an install can name, and no other.

`docs/screens.html` draws this screen as a card headed "Questions nobody could answer", with the
shape of each question, how often it was asked, why it failed and the fix. Measured on
2026-09-16, nothing on any install recorded a question that went unanswered. `ops.question_asked`
holds who asked and from where, and its table says in its own docstring that it holds nothing
about the outcome. `obs.request_telemetry` holds a status, and `brain.ops.telemetry.
AN_ABSTENTION_IS_RECORDED_WITHOUT_ITS_REASON` makes every abstention one status whatever it was
for. Since 2026-09-17 one kind is recorded, in `ops.question_gap`, and this module decides who may
see it.

**Only one reason an answer is refused is a gap, and it is a fact about the install.**
`brain.console.operate.GAP_REASONS` is the decision and it is imported rather than restated:
`brain.gate.abstain.AbstentionReason` has five members and `NOTHING_CONNECTED` is the one whose
own comment says it is identical for everybody. "I could not find that" is said identically
when a record does not exist and when the person asking may not see it, which is the whole
point of `NOT_FOUND_TEXT` being one constant shared by two reasons, so a gap list counting it
would publish refusals as holes in the knowledge base. See
`ONE_REASON_IS_A_FACT_ABOUT_THE_INSTALL_AND_THE_REST_ARE_FACTS_ABOUT_A_READER`.

**A gap names the source that would have answered, and that is the narrowing the leaf took.** The
answer lane declines a question as nothing connected in two cases, both decided from the rules and
the readers before anything is read: nothing is connected at all, or the question's shape matches
a rule for a source nothing on the install reads. The second names a source, which is
`brain.adoption.Unanswered.missing_source`, and `brain.ops.question_gap_store` records it with the
asker's department and nothing else. So the screen lists, per department and source, how many
questions no connected source covered. It does not list questions answered "I could not find
that", or any question's words, and never will: see
`A_GAP_IS_A_QUESTION_NO_CONNECTED_SOURCE_COVERS_AND_NOTHING_ELSE_IS_ONE`. The leaf's sentence was
reworded to say so on 2026-09-17.

**A gap line is shown by the department it was asked in, and its source is named by the
Connectors screen's own decision.** `gap_lines` counts through `brain.adoption.connector_demand`,
which admits a line only for a department the reader's Questions grant matches and returns no
count of the rest. A source name is a fact about what the company runs, so it is shown only where
`brain.console.connector_trust.connectors_reachable` would show it; a line whose source this
reader may not be told is merged into one line for its department with no source named, which is a
count of questions in a department the reader reaches and names nothing it does not. See
`A_SOURCE_IS_NAMED_WHERE_THE_CONNECTORS_SCREEN_WOULD_NAME_IT`.

**That nothing is connected at all can be read now, without a record of it.** The answer lane
abstains with `NOTHING_CONNECTED` for every question when `brain.api_routes.row_readers` returns no
reader, which is a property of the tool registry the process holds and not of any question. The
route reads that same function over that same registry, so the screen says what every asker is
being told at the moment it is opened. Any holder of the screen's grant may be told it, whatever
the grant's scope, because it is the sentence every asker in the company receives while it is
true. See `THE_GAP_IS_READ_FROM_THE_REGISTRY_THE_ANSWER_LANE_READS` and
`NOTHING_CONNECTED_IS_TOLD_TO_ANY_HOLDER_OF_THE_SCREENS_GRANT`.

**The two sentences the screen quotes are the lane's own objects.** `PUBLIC_TEXT` is read here and
carried to the page, so the page quotes the words an asker actually receives rather than a copy
that drifts the afternoon somebody improves the wording of one of them.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything.

Task ids: M27.7.18
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.adoption import connector_demand
from brain.console.connector_trust import connectors_reachable
from brain.console.operate import GAP_REASONS
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.abstain import PUBLIC_TEXT, AbstentionReason
from brain.ops.question_gap_store import Gap
from brain.tables.adoption import QuestionAskedRow
from brain.tables.question_gap import QuestionGapRow
from brain.tables.telemetry import RequestTelemetryRow

# ------------------------------------------------------------------ written-down reasons
#: Why the screen names one kind of gap and counts no other.
ONE_REASON_IS_A_FACT_ABOUT_THE_INSTALL_AND_THE_REST_ARE_FACTS_ABOUT_A_READER: Final = (
    "Nothing connected is said to everybody alike, because it describes the install. Nothing "
    "found is said both when a record does not exist and when the asker may not see it, and "
    "the two are one sentence on purpose. A gaps screen that counted the second would tell an "
    "administrator how often somebody was refused, dressed as a hole in the knowledge base."
)

#: Why the recorded gaps are exactly the questions no connected source covers.
A_GAP_IS_A_QUESTION_NO_CONNECTED_SOURCE_COVERS_AND_NOTHING_ELSE_IS_ONE: Final = (
    "A gap is recorded when the question's shape matched a rule for a source nothing on the "
    "install reads, which is decided from the rules and the readers before anything is read. "
    "Every asker and every record gives that answer alike, so counting it counts wiring and not "
    "refusals. A question answered with nothing found is never recorded, and no question's "
    "words or asker are kept, so the screen lists departments, sources and counts."
)

#: Why a source is named only where the Connectors screen would name it.
A_SOURCE_IS_NAMED_WHERE_THE_CONNECTORS_SCREEN_WOULD_NAME_IT: Final = (
    "A source's name says what the company runs, and the Connectors screen already decides who "
    "may be told that. A gap line is shown for a department the reader's Questions grant "
    "reaches, and its source is named only when the Connectors grant reaches it too. Lines "
    "whose source may not be named are merged into one line for the department, which counts "
    "questions the reader may see and names nothing the reader may not."
)

#: Why the gap is read from the registry rather than from a record of questions.
THE_GAP_IS_READ_FROM_THE_REGISTRY_THE_ANSWER_LANE_READS: Final = (
    "The answer lane abstains with nothing connected exactly when the registry holds no row "
    "reader, and brain.api_routes.row_readers is the function that builds what the lane is "
    "given. Reading the same function over the same registry means the screen and the lane "
    "cannot disagree about whether an asker is being told nothing is connected."
)

#: Why the scope of the reader's grant does not narrow this answer.
NOTHING_CONNECTED_IS_TOLD_TO_ANY_HOLDER_OF_THE_SCREENS_GRANT: Final = (
    "Every asker in the company receives the nothing-connected sentence while it is true, so a "
    "reader whose grant names one department learns nothing here that one question would not "
    "tell them. Narrowing it would withhold from an administrator what their own staff are "
    "being told, and withholding it adds no protection to anybody."
)

#: The screen this module is the reader decision for.
SCREEN_KEY: Final = "questions"

#: The capability the screen is read behind, read off the registry rather than written here.
QUESTION_AUTHORITY: Final[Capability] = screen(SCREEN_KEY).read.requires

#: Whether an install records every question that went unanswered. It does not, and it records
#: exactly one kind: see `A_GAP_IS_A_QUESTION_NO_CONNECTED_SOURCE_COVERS_AND_NOTHING_ELSE_IS_ONE`.
#: `questions_gaps` reports a ledger column that would make this untrue while it still reads false.
UNANSWERED_QUESTIONS_ARE_RECORDED: Final = False

#: Column names through which a ledger would start recording how a question ended.
OUTCOME_COLUMNS: Final[frozenset[str]] = frozenset(
    {"abstention", "abstention_reason", "answered", "outcome", "reason", "unanswered"}
)

#: The whole of what a gap row holds. A principal or the question's words beside these is a list of
#: what each colleague tried to find out, and `questions_gaps` reports a column added to it.
GAP_COLUMNS: Final[frozenset[str]] = frozenset({"trace_id", "department", "source", "at"})


@dataclass(frozen=True)
class GapLine:
    """How many questions no connected source covered, in one department, for one source.

    `source` is None when this reader may not be told that source's name, and then the line is
    every such question in the department together. See
    `A_SOURCE_IS_NAMED_WHERE_THE_CONNECTORS_SCREEN_WOULD_NAME_IT`.
    """

    department: str
    source: str | None
    asked: int


@dataclass(frozen=True)
class QuestionsScreen:
    """What the questions screen may say to one reader.

    `nothing_connected` is true only when the reader may be told and it is so. The two
    sentences are always carried, because they are the product's words for every asker and say
    nothing about this install or this reader. `gaps` holds a line only for a department this
    reader's grant reaches, and no count of the rest.
    """

    nothing_connected: bool
    #: What every asker receives while nothing is connected.
    answered_when_nothing_connected: str
    #: What an asker receives when nothing was found or they may not see it: one sentence.
    answered_when_nothing_found: str
    #: Questions no connected source covered, most asked first.
    gaps: tuple[GapLine, ...]


def may_be_told_what_is_connected(entitlement: EntitlementSet, *, now: datetime) -> bool:
    """Whether this reader holds the screen's grant at all, in any scope.

    `scope_for` alone and no `Scope.matches`, which is
    `NOTHING_CONNECTED_IS_TOLD_TO_ANY_HOLDER_OF_THE_SCREENS_GRANT`: the fact has no department's
    version to match against, and it is the same for every department.
    """
    return entitlement.scope_for(QUESTION_AUTHORITY, now) is not None


def gap_lines(
    gaps: Sequence[Gap], entitlement: EntitlementSet, *, now: datetime
) -> tuple[GapLine, ...]:
    """The gap lines this reader may be shown (M27.7.18).

    Departments through the Questions grant's scope, counted by `connector_demand`, which admits
    only the departments handed to it; sources named through `connectors_reachable`, and the rest
    merged per department. Most asked first, then by department and source, so two reads of an
    unchanged ledger produce the same page.
    """
    where = entitlement.scope_for(QUESTION_AUTHORITY, now)
    if where is None:
        return ()
    reachable = frozenset(
        one.department for one in gaps if where.matches({"department": one.department})
    )
    demand = connector_demand([one.unanswered() for one in gaps], reachable)
    nameable = frozenset(
        connectors_reachable(sorted({source for _, source in demand}), entitlement, now)
    )
    merged: dict[tuple[str, str | None], int] = {}
    for (department, source), asked in demand.items():
        key = (department, source if source in nameable else None)
        merged[key] = merged.get(key, 0) + asked
    return tuple(
        GapLine(department=department, source=source, asked=asked)
        for (department, source), asked in sorted(
            merged.items(), key=lambda pair: (-pair[1], pair[0][0], pair[0][1] or "")
        )
    )


def questions_for_reader(
    *, connected: bool, gaps: Sequence[Gap], entitlement: EntitlementSet, now: datetime
) -> QuestionsScreen:
    """The questions screen for one reader (M27.7.18).

    `connected` is whether `brain.api_routes.row_readers` found a reader in the registry, and
    `gaps` is every gap in the window, read whoever is asking. A reader who may not be told is
    answered as a connected install with no gap recorded is, so the two are one object.
    """
    return QuestionsScreen(
        nothing_connected=not connected and may_be_told_what_is_connected(entitlement, now=now),
        answered_when_nothing_connected=PUBLIC_TEXT[AbstentionReason.NOTHING_CONNECTED],
        answered_when_nothing_found=PUBLIC_TEXT[AbstentionReason.NOTHING_RETRIEVED],
        gaps=gap_lines(gaps, entitlement, now=now),
    )


def questions_gaps(
    gap_reasons: Collection[AbstentionReason] = GAP_REASONS,
    ledger_columns: Iterable[Iterable[str]] | None = None,
    gap_columns: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Everything that would make this screen say something untrue about gaps.

    Three checks. The first is the console's gap decision moving without this screen: a reason
    added to `GAP_REASONS` is a gap this screen has nowhere to show, and a reason removed is a
    sentence this screen goes on saying. The second is a ledger starting to record how a question
    ended, which makes `UNANSWERED_QUESTIONS_ARE_RECORDED` untrue while it still reads false. The
    third is the gap ledger holding anything beyond a department, a source and an instant.
    """
    gaps: list[str] = []
    if set(gap_reasons) != {AbstentionReason.NOTHING_CONNECTED}:
        gaps.append(
            f"the console counts {sorted(one.value for one in gap_reasons)} as gaps and this "
            "screen shows only nothing connected, so one of the two is describing a screen "
            "that does not exist"
        )
    tables = (
        (
            tuple(QuestionAskedRow.__table__.columns.keys()),
            tuple(RequestTelemetryRow.__table__.columns.keys()),
        )
        if ledger_columns is None
        else tuple(tuple(one) for one in ledger_columns)
    )
    for columns in tables:
        for column in sorted(set(columns) & OUTCOME_COLUMNS):
            gaps.append(
                f"a question ledger now has a column named {column}, so something may record "
                "how a question ended and this screen still says nothing does"
            )
    held = set(QuestionGapRow.__table__.columns.keys() if gap_columns is None else gap_columns)
    for column in sorted(held - GAP_COLUMNS):
        gaps.append(
            f"the gap ledger now has a column named {column}, beyond a department, a source and "
            "an instant, so a gap may carry who asked or what they typed"
        )
    return tuple(gaps)
