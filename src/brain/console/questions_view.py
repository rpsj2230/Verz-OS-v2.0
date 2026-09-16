"""Questions and gaps, as one reader may be shown them: the one gap an install can name.

`docs/screens.html` draws this screen as a card headed "Questions nobody could answer", with the
shape of each question, how often it was asked, why it failed and the fix. Measured on
2026-09-16, nothing on any install records a question that went unanswered. `ops.question_asked`
holds who asked and from where, and its table says in its own docstring that it holds nothing
about the outcome. `obs.request_telemetry` holds a status, and `brain.ops.telemetry.
AN_ABSTENTION_IS_RECORDED_WITHOUT_ITS_REASON` makes every abstention one status whatever it was
for. The reason itself reaches a log line and nothing else. So the design's table has no source,
and what this module decides is the part of the screen that does.

**Only one reason an answer is refused is a gap, and it is a fact about the install.**
`brain.console.operate.GAP_REASONS` is the decision and it is imported rather than restated:
`brain.gate.abstain.AbstentionReason` has five members and `NOTHING_CONNECTED` is the one whose
own comment says it is identical for everybody. "I could not find that" is said identically
when a record does not exist and when the person asking may not see it, which is the whole
point of `NOT_FOUND_TEXT` being one constant shared by two reasons, so a gap list counting it
would publish refusals as holes in the knowledge base. See
`ONE_REASON_IS_A_FACT_ABOUT_THE_INSTALL_AND_THE_REST_ARE_FACTS_ABOUT_A_READER`.

**That one gap can be read now, without a record of it.** The answer lane abstains with
`NOTHING_CONNECTED` exactly when `brain.api_routes.row_readers` returns no reader, which is a
property of the tool registry the process holds and not of any question. The route reads that
same function over that same registry, so the screen says what every asker is being told at the
moment it is opened, and cannot disagree with the lane about it. It cannot say how many questions
met that sentence, because nothing counts them, and it does not try. See
`THE_GAP_IS_READ_FROM_THE_REGISTRY_THE_ANSWER_LANE_READS`.

**Any holder of the screen's grant may be told it, whatever the grant's scope.** The sentence is
the one every asker in the company receives while nothing is connected, so a department-scoped
reader learns nothing from this screen that asking any question would not tell them. That is the
opposite answer from `brain.console.service_level_view`, and the difference is the row: a reading
is everybody's activity summed, and this is configuration identical for everybody. A reader who
holds no grant for the screen is answered as an install with something connected is answered,
and nothing on the response says which it was. See
`NOTHING_CONNECTED_IS_TOLD_TO_ANY_HOLDER_OF_THE_SCREENS_GRANT`.

**The two sentences the screen quotes are the lane's own objects.** `PUBLIC_TEXT` is read here and
carried to the page, so the page quotes the words an asker actually receives rather than a copy
that drifts the afternoon somebody improves the wording of one of them.

What is not built, and why. A ledger of unanswered questions needs to know which source would
have answered, which is `brain.adoption.Unanswered.missing_source`, and nothing in the answer
lane can tell that: it matches rules against the registry and has no notion of a source it was
not given. A ledger holding only `NOTHING_CONNECTED` would count questions asked on an install
with no sources, which the screen already says in the present tense. So M27.7.18 is claimed here
for what the screen can show and is not closed by it; `questions_gaps` goes red the day a ledger
starts recording how a question ended, which is the day the sentence saying nothing records it
stops being true.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything.

Task ids: M27.7.18
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.operate import GAP_REASONS
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.abstain import PUBLIC_TEXT, AbstentionReason
from brain.tables.adoption import QuestionAskedRow
from brain.tables.telemetry import RequestTelemetryRow

# ------------------------------------------------------------------ written-down reasons
#: Why the screen names one kind of gap and counts no other.
ONE_REASON_IS_A_FACT_ABOUT_THE_INSTALL_AND_THE_REST_ARE_FACTS_ABOUT_A_READER: Final = (
    "Nothing connected is said to everybody alike, because it describes the install. Nothing "
    "found is said both when a record does not exist and when the asker may not see it, and "
    "the two are one sentence on purpose. A gaps screen that counted the second would tell an "
    "administrator how often somebody was refused, dressed as a hole in the knowledge base."
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

#: Why the screen says unanswered questions are not recorded.
AN_UNANSWERED_QUESTION_IS_RECORDED_NOWHERE_AND_THE_SCREEN_SAYS_SO: Final = (
    "The question ledger holds who asked and nothing about the outcome, and the request ledger "
    "holds one status for every abstention whatever it was for. A table of unanswered "
    "questions drawn empty would say every question was answered, so the screen says in words "
    "that nothing records one."
)

#: The screen this module is the reader decision for.
SCREEN_KEY: Final = "questions"

#: The capability the screen is read behind, read off the registry rather than written here.
QUESTION_AUTHORITY: Final[Capability] = screen(SCREEN_KEY).read.requires

#: Whether anything on an install records a question that went unanswered. It does not. See
#: `AN_UNANSWERED_QUESTION_IS_RECORDED_NOWHERE_AND_THE_SCREEN_SAYS_SO`; `questions_gaps` reports
#: a ledger column that would make this untrue while it still reads false.
UNANSWERED_QUESTIONS_ARE_RECORDED: Final = False

#: Column names through which a ledger would start recording how a question ended.
OUTCOME_COLUMNS: Final[frozenset[str]] = frozenset(
    {"abstention", "abstention_reason", "answered", "outcome", "reason", "unanswered"}
)


@dataclass(frozen=True)
class QuestionsScreen:
    """What the questions screen may say to one reader.

    `nothing_connected` is true only when the reader may be told and it is so. The two
    sentences are always carried, because they are the product's words for every asker and say
    nothing about this install or this reader.
    """

    nothing_connected: bool
    #: What every asker receives while nothing is connected.
    answered_when_nothing_connected: str
    #: What an asker receives when nothing was found or they may not see it: one sentence.
    answered_when_nothing_found: str


def may_be_told_what_is_connected(entitlement: EntitlementSet, *, now: datetime) -> bool:
    """Whether this reader holds the screen's grant at all, in any scope.

    `scope_for` alone and no `Scope.matches`, which is
    `NOTHING_CONNECTED_IS_TOLD_TO_ANY_HOLDER_OF_THE_SCREENS_GRANT`: the fact has no department's
    version to match against, and it is the same for every department.
    """
    return entitlement.scope_for(QUESTION_AUTHORITY, now) is not None


def questions_for_reader(
    *, connected: bool, entitlement: EntitlementSet, now: datetime
) -> QuestionsScreen:
    """The questions screen for one reader, given whether any source is connected (M27.7.18).

    `connected` is whether `brain.api_routes.row_readers` found a reader in the registry. A
    reader who may not be told is answered as a connected install is, so the two are one object.
    """
    return QuestionsScreen(
        nothing_connected=not connected and may_be_told_what_is_connected(entitlement, now=now),
        answered_when_nothing_connected=PUBLIC_TEXT[AbstentionReason.NOTHING_CONNECTED],
        answered_when_nothing_found=PUBLIC_TEXT[AbstentionReason.NOTHING_RETRIEVED],
    )


def questions_gaps(
    gap_reasons: Collection[AbstentionReason] = GAP_REASONS,
    ledger_columns: Iterable[Iterable[str]] | None = None,
) -> tuple[str, ...]:
    """Everything that would make this screen say something untrue about gaps.

    Two checks. The first is the console's gap decision moving without this screen: a reason
    added to `GAP_REASONS` is a gap this screen has nowhere to show, and a reason removed is a
    sentence this screen goes on saying. The second is a ledger starting to record how a question
    ended, which makes `UNANSWERED_QUESTIONS_ARE_RECORDED` untrue while it still reads false.
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
    return tuple(gaps)
