"""A person's own agents, knowledge, history, memory and usage, narrowed by one predicate.

**"Their own" is a permission claim and not a filter, and the difference is where the
narrowing happens.** M33.3.1's five leaves all say "their own", and the surface that shows
somebody their own things by filtering a full list at read time has already computed the full
list: the rows left the store, the redactor walked them, the trace recorded the read, and the
narrowing happened afterwards in a renderer. Every one of those is a disclosure that already
occurred by the time the filter ran, and none of them appears in the answer, so the surface
looks identical either way.

**So the narrowing is a `Scope`, and it is the same `Scope` whether a store evaluates it or
this module does.** `own_scope` is `brain.knowledge.visibility.scope_for` at the personal
level, which is the repository's one statement of what a personal predicate is and which
refuses to build one without an owner, because a personal scope with a blank owner is
`Scope()`, and `Scope()` is the unrestricted scope: the narrowest level in the system turning
into the widest through an empty form field. Handed to a query it compiles through
`brain.core.scope_sql.compile_where` and the rows never leave the database; handed a record it
is `Scope.matches` over the one field that record's owner sits in. **One predicate, two
evaluators, and a test drives both.** That is the same relation `brain.console.scoped_authority`
records between a row and a scope, arriving at the other end of the same argument.

**What this module cannot fix, it declines to justify.** `brain.chat.turns.Turn`,
`brain.ops.spend.Actual`, `brain.memory.digest.Learning` and `brain.agents.model.AgentRecord`
all arrive here as sequences, because there is no repository layer anywhere in this
repository: `brain.tables.chat.ConversationRow` and `MessageRow` are declared and nothing in
`src` ever queries them. So the caller has already read whatever it read. The one thing a
module in this position can do is refuse to be the place where the wide read is justified:
every function below takes the principal as a required keyword, none of them has a default, an
`all` flag or a value meaning everybody, and `own_gaps` reads the signatures and reports one.
`brain.console.agent_automations` keeps the same rule about an agent id and states it the same
way. See `A_PARAMETER_MEANING_EVERYBODY_IS_HOW_A_PERSONAL_SURFACE_BECOMES_A_DIRECTORY`.

**An agent is somebody's own when they are its steward, never when they built it.**
`AgentRecord` keeps `created_by` and `audience.owner_id` apart deliberately: the first is
history and never moves, the second is who answers for the thing now. A personal surface
listing agents somebody built and handed over is a list of things they cannot change and are
not accountable for, and it grows forever. `brain.identity.lifecycle.agents_following` answers
a third question, which is which agents move with a person changing department, and it covers
the personal audience only; a department-visible agent somebody stewards is returned by
nothing today, which is the gap this closes.

**A memory's owner is who was asking when it formed, and that is authorship rather than
permission.** `brain.memory.formation.Formation.principal_id` is recorded "for the audit
question, never used to permit a recall", and this module does not turn it into one: what
comes back is the memories formed from this person's own conversations, and whether any of
them may still be recalled is `formation.may_recall` asking the reader's entitlement against
the formation's capabilities. A surface that read the owner as permission would recall a
memory because the same person came back rather than because they still reach what it was
formed from, which is the exact mistake that field's comment exists to prevent.

**The delete control writes a mark and this module says so rather than implying a removal.**
`brain.memory.review.delete` is `digest.undo` renamed for the surface, and it returns a
`Undo` carrying a supersession or a demotion. There is no removal behind it and there cannot
be one today: `brain.tables.memory` grants SELECT and INSERT on both memory tables and nothing
else, `brain.ops.erasure.StoreEraser` is a protocol with no implementation anywhere, and the
only DELETE grant in the whole schema is on the directory's role-grant table.
`brain.console.reach_view` declined its own edit-and-delete leaf on the same evidence. So what
is claimed here is the control the leaf asks for, which exists and runs, and
`DELETE_MEANS_A_MARK_AND_THIS_SURFACE_MAY_NOT_IMPLY_OTHERWISE` is the sentence that stops the
next reader promising a purge.

**Usage against allowance needed a join that existed nowhere.** `brain.ops.budgets` builds a
person's daily and monthly ceilings and says in its own docstring that nothing there counts
anything; `brain.ops.spend` counts and takes the ceilings as an argument. Between them sits
the question the leaf asks, and `own_allowances` is it: the rows at the user level for this
person, each paired with what they have actually spent inside that period's window.

**Rejected: defaulting a missing window to zero spend.** A `BudgetRow` whose period the caller
gave no window for would produce an `Allowance` with `spent_minor` of nought, which reads as
full headroom on the one screen a person checks before starting something expensive. The row
is dropped instead. See `A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM`.

**Rejected: a basis parameter.** `brain.console.workspace.Basis` decides whether an agent's
front page shows one person's figures or everybody's, and it is right there because that page
is about an agent. This surface is about a person and the person is in the signature, so a
basis here could only ever widen it, which is `brain.console.reads.console_gaps`' argument
about `audience` and the reason that function has no `union` parameter either.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` and the
windows are parameters, as in every sibling in this package.

Task ids: M33.3.1.1, M33.3.1.2, M33.3.1.3, M33.3.1.4, M33.3.1.5
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.chat.turns import Turn
from brain.core.scope import Scope
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.visibility import OWNER_FIELD, Visibility, scope_for
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import Learning, Undo
from brain.memory.review import delete as delete_memory
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.export import ConversationExport, conversation_export
from brain.ops.spend import Actual, Dimension, spend_by

# ------------------------------------------------------------------ written-down reasons
#: Why the narrowing is a predicate rather than a pass over rows already read.
THEIR_OWN_IS_A_PREDICATE_AND_THE_FILTER_IS_WHAT_HAPPENS_AFTER_THE_DISCLOSURE: Final = (
    "A surface that shows somebody their own things by filtering a full list has already "
    "computed the full list: the rows left the store, the redactor walked them, the read is "
    "in the trace, and the narrowing happened in a renderer afterwards. None of that appears "
    "in what comes back, so the two designs look identical from the screen and differ "
    "entirely in what was disclosed. The narrowing is therefore a Scope, which a store "
    "evaluates in SQL and this module evaluates in Python, and it is the same Scope both "
    "times so the two cannot disagree about what personal means."
)

#: Why no function here has a parameter that could mean everybody.
A_PARAMETER_MEANING_EVERYBODY_IS_HOW_A_PERSONAL_SURFACE_BECOMES_A_DIRECTORY: Final = (
    "The principal is a required keyword on every function here and there is no default, no "
    "all flag and no value meaning everybody. A personal surface acquires one the first time "
    "somebody needs an administrative view and notices that this code already does most of "
    "it, and from then on the same function serves both, with the difference between them "
    "one argument nobody reviews. brain.console.agent_automations keeps the same rule about "
    "an agent id, brain.ops.export.BulkExportRequest is what it looks like when the wide read "
    "is a deliberate separate type, and own_gaps reads these signatures."
)

#: Why an agent belongs to whoever answers for it rather than whoever wrote it.
A_STEWARD_ANSWERS_FOR_AN_AGENT_AND_AN_AUTHOR_IS_HISTORY: Final = (
    "brain.agents.model keeps created_by and audience.owner_id apart on purpose: the first "
    "records who built the thing, which is the question an audit asks, and the second records "
    "who answers for it now, which is the question everybody else asks. A personal surface "
    "listing what somebody built is a list of things they cannot change and are not "
    "accountable for, and it never shrinks, because created_by never moves. Ownership "
    "transfer is what changes this list, which is what transferring is for."
)

#: Why the owner of a memory is not a permission to recall it.
WHO_A_MEMORY_FORMED_FROM_IS_AUTHORSHIP_AND_NEVER_A_RECALL_PERMISSION: Final = (
    "brain.memory.formation records the principal who was asking and its own comment says "
    "the field is for the audit question and never permits a recall: a memory is recalled "
    "because whoever is here now still reaches what it was formed from, not because the same "
    "person came back. This surface reads it as authorship, which is what a person means by "
    "their own memory, and says nothing about what may be recalled. may_recall is still the "
    "only answer to that and it takes an entitlement, which this does not."
)

#: Why the delete control must not be described as a removal.
DELETE_MEANS_A_MARK_AND_THIS_SURFACE_MAY_NOT_IMPLY_OTHERWISE: Final = (
    "brain.memory.review.delete writes a supersession or a demotion and removes nothing, and "
    "no removal is reachable today: brain.tables.memory grants SELECT and INSERT on both "
    "memory tables and nothing else, brain.ops.erasure.StoreEraser is a protocol nothing "
    "implements, and the schema carries exactly one DELETE grant, on the directory's role "
    "grants. A console that told somebody their memory had been deleted would be making a "
    "promise the database cannot keep, and the person would find out from a later answer."
)

#: Why a budget row whose window is missing is dropped rather than reported at zero.
A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM: Final = (
    "Pairing a ceiling with no measured spend produces an Allowance whose spent_minor is "
    "nought, whose headroom is therefore the whole ceiling, and which is indistinguishable "
    "on a screen from a person who has spent nothing. That is the reassuring direction and "
    "it is wrong, and the screen it appears on is the one somebody checks before starting "
    "something expensive. A row whose period nobody supplied a window for is left out, so "
    "the absence is visible rather than the figure being confidently incorrect."
)


class OwnThingsError(Exception):
    """A personal surface was asked to act on something that is not this person's.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives about
    itself: those five outcomes describe an answer given to somebody who asked a question,
    and this is a refusal to operate a control on a personal screen.
    """


# ------------------------------------------------------------------------- the predicate
def own_scope(principal_id: str) -> Scope:
    """The row predicate that is this person's own things.

    `brain.knowledge.visibility.scope_for` at the personal level, called rather than
    reimplemented as a one-clause scope here. That function refuses an empty owner, and the
    refusal is the reason to route through it: a personal scope built without one is
    `Scope()`, which is the unrestricted scope, so the narrowest level in the system becomes
    the widest through a blank field. A second construction here would be a second place for
    that check to be missing.

    Returned rather than applied, because a store that can take a predicate should get one:
    compiled by `brain.core.scope_sql.compile_where`, the rows never leave the database. See
    `THEIR_OWN_IS_A_PREDICATE_AND_THE_FILTER_IS_WHAT_HAPPENS_AFTER_THE_DISCLOSURE`.
    """
    return scope_for(Visibility.PERSONAL, owner_id=principal_id)


def is_own(principal_id: str, owner_id: str) -> bool:
    """Whether a record belonging to `owner_id` is this person's, by the same predicate.

    `Scope.matches` over the one field an owner sits in, so the in-memory answer and the
    answer a query would give are the same predicate evaluated twice rather than two rules.
    An empty `owner_id` is refused by `Clause.matches`, which admits no row missing the field
    and no row whose value differs, so an unowned record is nobody's rather than everybody's.
    """
    return own_scope(principal_id).matches({OWNER_FIELD: owner_id})


# ------------------------------------------------------------------- own agents (M33.3.1.1)
def own_agents(
    records: Iterable[AgentRecord],
    *,
    principal_id: str,
) -> tuple[AgentRecord, ...]:
    """The agents this person answers for (M33.3.1.1). Steward, never author.

    See `A_STEWARD_ANSWERS_FOR_AN_AGENT_AND_AN_AUTHOR_IS_HISTORY`. Every visibility level, so
    a department-visible agent somebody stewards is here; `brain.identity.lifecycle.
    agents_following` covers the personal level only and answers a different question, which
    is which agents follow somebody moving department.

    An archived record is absent. `brain.agents.lifecycle` calls archiving terminal, so a
    listing that included one would offer controls over something that cannot come back; a
    disabled record is present, because disabling is reversible and the person who answers
    for it is the person who would re-enable it.

    Order follows `records`, for the reason `brain.console.screens.offerable` gives: the
    caller's order is usually meaningful and re-sorting discards it.
    """
    return tuple(
        one
        for one in records
        if one.archived_at is None and is_own(principal_id, one.audience.owner_id)
    )


# ---------------------------------------------------------------- own knowledge (M33.3.1.2)
def own_knowledge(
    items: Iterable[KnowledgeItem],
    *,
    principal_id: str,
) -> tuple[KnowledgeItem, ...]:
    """The knowledge items and uploads this person owns (M33.3.1.2).

    `KnowledgeItem.owner_id` is the steward in that module's own words, which is the same
    distinction agents make, and the predicate is `own_scope` rather than an equality written
    here, so this list and a query narrowed by the same scope agree by construction.

    **Not narrowed by visibility level, and that is deliberate.** An item somebody uploaded
    and later had promoted to the company is still theirs to steward, and dropping it at the
    moment of promotion would make a personal library shrink as a reward for publishing.
    `brain.knowledge.visibility.scope_for` at the personal level answers a different question,
    which is who may read an unpromoted item.
    """
    return tuple(one for one in items if is_own(principal_id, one.owner_id))


# ------------------------------------------------------------------ own history (M33.3.1.3)
def own_history(
    turns: Iterable[Turn],
    *,
    principal_id: str,
) -> tuple[Turn, ...]:
    """This person's own turns, in the order they arrived (M33.3.1.3).

    `Turn.principal_id` is who spoke, and it is the only identifier on a turn:
    `brain.chat.turns.Turn` carries no conversation id and no agent id, which
    `brain.console.workspace` records having to work around for the same reason. So the
    attribution to a conversation happens before the call and this narrows to a person.

    Order is preserved rather than sorted, because a conversation read out of order is not a
    conversation, and `Turn.at` is not guaranteed distinct within one exchange.
    """
    return tuple(one for one in turns if is_own(principal_id, one.principal_id))


def export_own_history(
    turns: Iterable[Turn],
    *,
    principal_id: str,
    conversation_id: str,
    at: datetime,
) -> ConversationExport:
    """This person's own turns, in the shape an export takes (M33.3.1.3).

    **Built from the narrowed turns and never from the input**, which is the whole of this
    function: `brain.ops.export.conversation_export` takes what it is given and its docstring
    says so, "turns is what this caller may see, decided before it gets here". This is that
    decision, made once, so a personal export cannot be assembled from a wider read by a
    caller who narrowed the screen and forgot the download.

    `subject_id` is the same principal the narrowing used rather than a separate argument,
    because an export whose subject and whose contents came from two parameters is one where
    somebody else's turns can be filed under this person's name.

    The export drops references and locked fields, which is that module's decision and not
    repeated here.
    """
    return conversation_export(
        subject_id=principal_id,
        conversation_id=conversation_id,
        at=at,
        turns=own_history(turns, principal_id=principal_id),
    )


# ------------------------------------------------------------------- own memory (M33.3.1.4)
def own_memory(
    learnings: Iterable[Learning],
    *,
    principal_id: str,
) -> tuple[Learning, ...]:
    """What the system learnt from this person's own conversations (M33.3.1.4).

    Authorship and never a recall permission; see
    `WHO_A_MEMORY_FORMED_FROM_IS_AUTHORSHIP_AND_NEVER_A_RECALL_PERMISSION`. Whether any of
    these may still be recalled is `brain.memory.formation.may_recall`, which takes an
    entitlement, and this function deliberately does not: a personal surface that decided
    recall from the owner would recall a memory because the same person came back.

    Order follows `learnings`. `brain.memory.review` sorts its own queues by what each is for,
    a digest newest first and a review queue oldest first, and this is neither.
    """
    return tuple(one for one in learnings if is_own(principal_id, one.formation.principal_id))


def delete_own_memory(
    learning: Learning,
    *,
    principal_id: str,
    at: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> Undo:
    """The delete control on a person's own memory (M33.3.1.4). It writes a mark.

    **Delete means a mark and this returns one**; see
    `DELETE_MEANS_A_MARK_AND_THIS_SURFACE_MAY_NOT_IMPLY_OTHERWISE`. The act itself is
    `brain.memory.review.delete`, called and never reimplemented, so the idempotence and the
    choice between a supersession and a demotion stay in the module that argues for them.

    What is added is the one thing that module cannot ask: whether this memory is this
    person's. It takes a `Learning` and no principal, correctly, because the review queue's
    delete is an administrator's and is decided by the entitlement filter on the queue. A
    personal control is decided by ownership, and a control that took the memory from a form
    would otherwise undo somebody else's by id.

    Refuses rather than returning `None`, because a delete that quietly did nothing would
    read on the screen as a delete that worked.
    """
    if not is_own(principal_id, learning.formation.principal_id):
        msg = (
            f"{principal_id!r} may not delete {learning.memory_id!r} from a personal memory "
            f"tab. {WHO_A_MEMORY_FORMED_FROM_IS_AUTHORSHIP_AND_NEVER_A_RECALL_PERMISSION}"
        )
        raise OwnThingsError(msg)
    return delete_memory(learning, at=at, supersessions=supersessions, demotions=demotions)


# -------------------------------------------------------------------- own usage (M33.3.1.5)
#: The budget level a person's own ceilings are written at. `brain.ops.budgets` owns the
#: enumeration; this names the member so the selection below reads as a decision rather than
#: as a comparison somebody could widen to DEPARTMENT without noticing what it published.
OWN_LEVEL: Final = BudgetLevel.USER


def own_allowances(
    rows: Iterable[BudgetRow],
    actuals: Sequence[Actual],
    *,
    principal_id: str,
    windows: Mapping[BudgetPeriod, tuple[datetime, datetime]],
) -> tuple[Allowance, ...]:
    """This person's ceilings, each with what they have actually spent against it (M33.3.1.5).

    **The join neither module could make.** `brain.ops.budgets` builds the ceilings and says
    nothing there counts anything; `brain.ops.spend` counts and takes the ceilings as an
    argument. This pairs them for one person, which is what the leaf asks for and what
    nothing did.

    Spend is `spend_by` at `Dimension.PRINCIPAL` rather than a sum written here, so the
    machine-row decision stays where that module made it: an automation running as a named
    principal is that principal's spend, which is `brain.console.workspace.visible_actuals`'
    reading of the same rows.

    A row at any level other than `OWN_LEVEL`, or belonging to somebody else, is not this
    person's allowance and is absent. A row whose period nobody supplied a window for is also
    absent, rather than reported against a zero: see
    `A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM`. `BudgetPeriod.RUN` is the ordinary case
    of that, and correctly so, since a per-run ceiling is a gate on one call rather than a
    figure anybody spends against over a period.

    Order follows `rows`, which `brain.ops.budgets.user_allowances` returns daily first, and
    that pair is what a person reads.
    """
    windowed = {
        period: tuple(one for one in actuals if since <= one.at <= until)
        for period, (since, until) in windows.items()
    }
    spent = {
        period: spend_by(inside, Dimension.PRINCIPAL).get(principal_id, 0)
        for period, inside in windowed.items()
    }
    return tuple(
        Allowance(row=row, spent_minor=spent[row.period])
        for row in rows
        if row.level is OWN_LEVEL and is_own(principal_id, row.subject) and row.period in spent
    )


# -------------------------------------------------------------------------- the diagnostic
#: Parameter names that would let one of these functions answer for somebody else.
#:
#: Names as well as the required-keyword check below, because the way this rule is actually
#: broken is not somebody deleting the principal parameter. It is somebody adding `everyone`
#: beside it for an administrative screen, and from then on the same function serves both.
NAMES_THAT_WOULD_MEAN_EVERYBODY: Final[frozenset[str]] = frozenset(
    {
        "all_principals",
        "all_subjects",
        "any_owner",
        "basis",
        "everybody",
        "everyone",
        "principal_ids",
        "subjects",
    }
)

#: The parameter every function here narrows by. One spelling, so the check below cannot be
#: satisfied by a function that named it something else.
THE_PRINCIPAL: Final = "principal_id"

#: The functions this module offers a person. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a function added here and not to this tuple
#: is one the checks below never see.
PERSONAL_SURFACE: Final[tuple[Callable[..., Any], ...]] = (
    own_agents,
    own_knowledge,
    own_history,
    export_own_history,
    own_memory,
    delete_own_memory,
    own_allowances,
)


def own_gaps(
    surface: Sequence[Callable[..., Any]] = PERSONAL_SURFACE,
) -> tuple[str, ...]:
    """Everything about this module that would let a personal surface answer for everybody.

    Takes its input rather than reading the module's own tuple, and a mutation is the reason
    `brain.console.govern.govern_gaps` gives about itself: a diagnostic that can only run
    against the healthy tree has nothing to report, so switching off any of its refusals
    changes nothing observable. Calling it with no arguments is the deployment check and
    calling it with a constructed function is the test.

    Three checks on every function. It narrows by the principal, that parameter is
    keyword-only and has no default, and no parameter beside it could mean everybody. The
    second is the one worth spelling out: a positional principal with a default is how a call
    site ends up omitting it, and a default of `""` would build a personal scope with no
    owner, which `scope_for` refuses loudly, while a default of `None` would need a branch
    somebody would write as "then show everything".
    """
    gaps: list[str] = []

    for one in surface:
        taken = inspect.signature(one).parameters
        found = taken.get(THE_PRINCIPAL)
        if found is None:
            gaps.append(
                f"{one.__name__} does not narrow by {THE_PRINCIPAL}, so a personal surface "
                f"is answering for whoever the caller handed it. "
                f"{A_PARAMETER_MEANING_EVERYBODY_IS_HOW_A_PERSONAL_SURFACE_BECOMES_A_DIRECTORY}"
            )
        else:
            if found.kind is not inspect.Parameter.KEYWORD_ONLY:
                gaps.append(
                    f"{one.__name__} takes {THE_PRINCIPAL} positionally, so a call site can "
                    "pass it in the wrong place and be narrowed to a conversation id"
                )
            if found.default is not inspect.Parameter.empty:
                gaps.append(
                    f"{one.__name__} defaults {THE_PRINCIPAL} to {found.default!r}, so the "
                    "argument that makes this surface personal can be left out"
                )
        gaps.extend(
            f"{one.__name__} takes {name}, which is how a personal surface becomes a "
            f"directory of everybody else's. "
            f"{A_PARAMETER_MEANING_EVERYBODY_IS_HOW_A_PERSONAL_SURFACE_BECOMES_A_DIRECTORY}"
            for name in taken
            if name in NAMES_THAT_WOULD_MEAN_EVERYBODY
        )

    return tuple(gaps)
