"""One table's column classification over HTTP: read it, review a change, upload and apply.

`brain.knowledge.columns` closed M7.5.1 and M7.5.2: a `TableClassification` is one entity,
a `ColumnRule` per column, and the derivations between them, and `project_row` narrows a
price-list row to the columns a caller may see. Nothing outside the process could read any
of it. So the rules that decide whether a person sees the cost beside the sell price were
legible only to whoever had the source tree open, which is the population that already
knows.

**This module adds no second model of what a classification is.** Every shape below is a
projection of `ColumnRule` and `TableClassification`, the current classification is read
through `brain.tools.startup.classification_for`, and the one interesting computation is
`brain.knowledge.columns.close_over_derivations` run twice. A route that built its own idea
of a column rule would be a second answer to "may this person see this field", and the
second answer is the one nobody keeps in step.

**The write capability carries the `admin` verb, and that is the whole security argument
for this surface.** A classification decides what other people may see. `gate.admission.
CHANNEL_VERBS` gives `admin` to CONSOLE and withholds it from API, so a client-credentials
token cannot retune what is confidential; `ASSURANCE_VERBS` gives it only to STRONG, so a
password-only session cannot either. Neither ceiling had to be written here and neither can
be argued with from here, which is the point: the verb is the declaration, and everything
that enforces it is upstream. `brain.routing_routes.MATRIX_WRITE` is the same choice for the
same reason one surface across.

**A caller who may not read a classification is refused in the words used for one that does
not exist.** An entity nothing classifies, an entity this caller holds nothing over, and a
caller who may read but not review all get `Absent` and one sentence. That is
`brain.api_routes.AN_ENTITY_IS_AS_ENUMERABLE_AS_A_RECORD` applied one level up and it is
why there is no route here that lists the classified entities: a list of them is a map of
what this installation holds, handed over for the price of one capability, and the console
already knows how to make a person name an entity because the records screen makes them.

**The review requires the read capability as well as the write one.** A review is a
comparison between the classification that stands and the one proposed, so its body carries
the current rules restated as a difference. Requiring only the write capability would make
the review a way to read what the read capability guards, one probe at a time, which is the
oracle the refusal above spends itself closing. `editable` on the read is therefore true
exactly when a review would be answered, and it is still presentation: the review checks
both capabilities again and refuses whatever the flag said. See
`AN_EDITABLE_FLAG_DECIDES_WHAT_IS_DRAWN_AND_NOTHING_ELSE`.

**A built-in classification is still a constant, and a review stores nothing.** `PRICE_LIST`
and a source's own entities are compiled into the process, so a change to one of them is a
source edit and a deploy, and reviewing one writes nothing. See
`A_REVIEW_STORES_NOTHING_AND_NO_AUDIT_ROW_IS_WRITTEN`.

**An uploaded table's classification is stored, and a mark applied to it is written and
ledgered (M7.5.3, M7.7.3).** An administrator uploads a price list as a CSV or an XLSX file,
it becomes `know.classified_table` and its rows, and each column is marked open, restricted
or derived (`brain.knowledge.columns.ColumnAccess`). A mark is reviewed exactly as a rule is,
through the same comparison, and applying it replaces the stored classification in one
statement whose ledger entry `0116`'s trigger writes under the administrator's name. See
`AN_APPLIED_MARK_IS_STORED_AND_LEDGERED`. Ask reads the stored tables on the next question,
through `brain.ops.classification_store.classified_lane_of`.

**An upload never widens anything, and a name the product classifies cannot be uploaded.**
Every column of a new table starts restricted unless `PRICE_LIST` already gives it a mark (see
`brain.knowledge.columns.first_classification`), and a second upload keeps the marks that
stand. The product's own entities are refused as names because `classification_for` is keyed
on the entity alone, and two classifications for one entity is the ambiguity its docstring
says it cannot survive.

**What a review answers is what the proposal does, including that it would not load.** A
classification that raises on construction leaves the previous one in place while a person
believes they changed it, which is the worst outcome available on this surface, so it is
reported as a finding rather than as a 422 about a malformed body. The words come from
`brain.knowledge.columns` and `brain.core.field_policy`, so a rule this module has never
heard of still explains itself.

**The widening verdict is computed here and never in the console.** See
`WIDENING_IS_DECIDED_ON_THIS_SIDE`. Two checks, and they catch different things. The
syntactic one compares two rules for one column. The closure one runs
`close_over_derivations` over both classifications for every caller short of exactly one
column and reports which columns such a caller would newly reach, which is the check that
names `margin` when somebody drops the derivation on `cost`.

**The policy epoch moves when a derivation changes, and it did not until 2026-09-28.** Two
causes, both now closed: `FieldPolicy.epoch` did not digest `FieldRule.derived_from` until
2026-09-21, and `ColumnRule.as_field_rule` dropped `derived_from` until this module's change,
so the policy a classification compiled to carried no derivation. Dropping the derivation on
`cost` changed what every caller short of the cost capability sees and left the epoch
identical, and the answer cache would have kept serving rows closed under the old rule.
`test_a_dropped_derivation_moves_the_epoch` holds it now. `widens` is still computed from the
rules rather than from the digests, because two digests that differ say something changed and
never which way.

**The closure check is bounded at callers short of one column, and that bound is real.**
Every subset of the columns is the honest question and it is exponential. One missing column
is the shape the derivation rule was written for, which is the price list: Finance holds
`read:price_list.cost` and nobody else does. A widening visible only to a caller short of
two columns at once is not reported, and this module does not pretend otherwise.

Rejected: a route that lists classified entities. See above; it is the installation's map.

Rejected: a body carrying the entity or the column. Both are path segments, for the reason
`brain.routing_routes` keeps `role` off `RungEdit`: a value that arrives twice is a value
two readers disagree about, and the address is the copy a person sent their colleague.

Rejected: taking a whole classification in one body. It reads as the safer shape and it is
the more dangerous one here, because the columns a proposal does not mention are then either
deleted or preserved, and whichever this module chose would be wrong for somebody. One
column's rule at a time cannot silently drop a column. What that costs is real and is stated
below: there is no way here to remove a classification, and removing one is how a field is
withheld from everybody at once.

Rejected: reporting a count of anything. `RungPage` argues it for the matrix and the console
keeps the rule everywhere; a classification is answered whole to every caller who may read
it at all, so there is nothing here for a count to disclose, and that is a fact about this
collection rather than a licence to start counting.

Task ids: M7.5.1, M7.5.2, M7.5.3, M7.7.3
"""

from __future__ import annotations

import base64
import binascii
import enum
import re
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import of_request
from brain.core.entitlement import CAPABILITY_RE, Capability
from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.core.errors import Absent, Failed
from brain.core.field_policy import Classification
from brain.knowledge.classified_rows import StoredTable, next_upload
from brain.knowledge.columns import (
    ColumnAccess,
    ColumnClassificationError,
    ColumnRule,
    TableClassification,
    access_of,
    close_over_derivations,
    column_name_for,
    marked,
)
from brain.knowledge.table_file import MAX_TABLE_FILE_BYTES, TableFileError, read_table_file
from brain.ops.classification_store import (
    ClassifiedTables,
    ClassifiedTableStoreError,
    classified_tables_of,
)
from brain.tools.startup import classification_for, every_row_classification

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why a console may not work out for itself whether a change widens access.
WIDENING_IS_DECIDED_ON_THIS_SIDE: Final = (
    "Whether a proposed rule widens who may reach a column is computed here, from the "
    "classification that stands and the one proposed, and it is sent as an answer. A "
    "console that worked it out from the two rule sets would hold a second copy of the "
    "derivation closure, in the one place an attacker can edit, and the copy would drift "
    "the first time the closure changed. What the console does with the answer is "
    "presentation: it draws the widened columns loudly, and nothing about the request it "
    "made depends on what came back."
)

#: Why an editable flag is on the read, and the one thing it must never be.
AN_EDITABLE_FLAG_DECIDES_WHAT_IS_DRAWN_AND_NOTHING_ELSE: Final = (
    "editable says whether this caller holds both capabilities, for this classification, "
    "on this request. It exists so a console can leave out a control nobody can use. It is "
    "not a permission: the review checks the same two capabilities again and refuses "
    "whatever the flag said, and a console that skipped the request because the flag was "
    "false would be enforcing a rule in the copy an attacker edits."
)

#: Why a review changes nothing, and what does not exist as a result.
A_REVIEW_STORES_NOTHING_AND_NO_AUDIT_ROW_IS_WRITTEN: Final = (
    "A review reads two classifications, compares them and answers, and writes nothing: no "
    "row and no audit entry. For a built-in classification, compiled into this process, "
    "applying the change is a source edit and a deploy, and anything on a screen reading as a "
    "save would be describing a mechanism that does not exist, which is worse than the gap it "
    "hides, because a person would stop checking. An uploaded table's column is changed by "
    "applying a mark, which is a separate request: see AN_APPLIED_MARK_IS_STORED_AND_LEDGERED."
)

#: Why applying a mark is its own request, and what it leaves behind.
AN_APPLIED_MARK_IS_STORED_AND_LEDGERED: Final = (
    "Applying a mark to an uploaded table's column replaces the table's stored classification "
    "whole, in one statement, and 0116's trigger appends a ledger entry naming the "
    "administrator, their reach and the request. It is a PUT of its own rather than a flag on "
    "the review, so a review can never be the thing that changed who may see a column, and the "
    "answer to it carries the same verdict a review would have given, so the widening is named "
    "in the response that made it as well as in the one that proposed it."
)

#: Why a classification is answered whole rather than narrowed to the caller.
A_CLASSIFICATION_IS_NOT_FILTERED_PER_CALLER: Final = (
    "Every column of a classification is answered to every caller who may read the "
    "classification at all. It is one decision rather than a filtered list, so there is no "
    "difference between the columns that exist and the columns this caller was shown, and "
    "nothing on the page discloses anything by subtraction. That is a fact about this "
    "collection and not a general licence: the console still renders no count, because the "
    "rule it keeps is about what a screen may do."
)


# ----------------------------------------------------------------- the capabilities

#: Reading a classification. Not the same as reading a row of the table it governs: what it
#: discloses is which columns this company treats as confidential and what it takes to see
#: them, which is a statement about the policy rather than about anybody's data.
CLASSIFICATION_READ: Final = Capability(value="read:field_classification")

#: Reviewing a change to one. An `admin` verb, which `gate.admission.CHANNEL_VERBS` grants
#: to CONSOLE and withholds from API, and which `ASSURANCE_VERBS` gives only to a caller who
#: used a second factor. Both ceilings matter here for one reason: a change to a
#: classification is a change to what everybody else may see, and a change attributable to a
#: secret in a configuration file is a change nobody made.
CLASSIFICATION_WRITE: Final = Capability(value="admin:field_classification")


# ------------------------------------------------------------------------ the bounds

#: How many sibling columns one rule may name as its inputs. Far above any real table, and
#: present so that one body cannot ask this module to close over an unbounded set. A
#: derivation naming more columns than the table has refuses to load anyway; this is the
#: bound that applies before anything is constructed.
MAX_DERIVED_FROM: Final = 64

#: The longest a `would_not_load` sentence may be. The words come from the classification
#: layer and quote the caller's own submitted rule, so there is nothing here to leak; the
#: bound exists because a pydantic message over a large body is long enough to fill a screen.
MAX_REFUSAL_CHARS: Final = 300

#: The longest an uploaded file may be once base64-encoded: four characters per three bytes.
MAX_UPLOAD_CHARS: Final = 4 * ((MAX_TABLE_FILE_BYTES + 2) // 3)

#: A table's title and a file's name, bounded as `know.classified_table.title` is.
MAX_TITLE_CHARS: Final = 200

#: The widest a table's name may be, as `know.classified_table.entity` is.
MAX_ENTITY_CHARS: Final = 60

_ENTITY_RE: Final = re.compile(OBJECT_NAME_PATTERN)

#: What an administrator is told when the name they chose is one the product classifies.
A_NAME_THE_PRODUCT_CLASSIFIES: Final = (
    "that name is a classification this product ships with; choose another name for the table"
)


# ------------------------------------------------------------------------ the shapes


class Change(enum.StrEnum):
    """What one proposed rule does to the column it governs.

    A closed vocabulary rather than a sentence, because the console renders each of these
    and the console must not be composing prose about a permission change. There is no
    member for removing a column, and that is honest rather than an omission: this surface
    edits one column's rule and cannot express a deletion. See the module docstring.
    """

    #: Nothing classified this column, so it was withheld from everybody by default-deny.
    ADDED = "added"
    #: A different capability reaches it. Which way that goes is not knowable here.
    CAPABILITY = "capability"
    #: A higher classification. Narrower channels may carry it and artifacts live less long.
    MORE_SENSITIVE = "more_sensitive"
    #: A lower one, which is the widening direction of the same fact.
    LESS_SENSITIVE = "less_sensitive"
    #: An input this column was declared to be reconstructable from is no longer named, so
    #: the closure has one fewer reason to withhold something.
    DERIVATION_DROPPED = "derivation_dropped"
    #: An input was added, so the closure has one more.
    DERIVATION_ADDED = "derivation_added"


#: The changes that widen who or what may reach a column.
#:
#: `LESS_SENSITIVE` is here and the reason is worth stating, because
#: `brain.core.field_policy` says a classification never permits: lowering one does not hand
#: anybody the capability. What it does widen is which channels may carry the value and how
#: long an artifact built from it is kept, and it moves the column's place in
#: `close_over_derivations._most_sensitive`, which decides which input is withheld when a
#: derivation has to be broken. Both are exposure.
#:
#: `CAPABILITY` is deliberately absent. Whether `read:price_list.cost` reaches more people
#: than `read:finance.cost` is a question about who holds what, and this module has no grant
#: store in front of it. Calling it a narrowing would be a guess in the dangerous direction.
#:
#: **Two of these three overlap the closure check completely, and both are kept.** Mutation
#: showed it: removing `ADDED` or `DERIVATION_DROPPED` changes no answer, because under the
#: one-missing-column sweep both always leave a column in `exposed` as well. `ADDED` does
#: because a classified column is reachable by every caller short of some other column;
#: `DERIVATION_DROPPED` does because a derivation on a column always fires for the caller
#: short of that column, so removing it always gives that caller something back. They are
#: kept because the overlap is a property of the sweep's bound rather than of the rule: a
#: widening visible only to a caller short of two columns at once is outside what the closure
#: check looks at, and the syntactic verdict still names it. `LESS_SENSITIVE` does not
#: overlap, which is why `test_lowering_a_classification_widens_even_when_no_column_becomes_
#: reachable` exists and is written against a column no derivation touches.
WIDENING_CHANGES: Final = frozenset(
    {Change.ADDED, Change.LESS_SENSITIVE, Change.DERIVATION_DROPPED}
)


class ColumnView(BaseModel):
    """One column's rule, as a console reads it.

    Every field of `ColumnRule` and nothing else. `required_capability` is flattened to its
    string because that is the spelling a grant table, a policy row and every support
    conversation use; the `Capability` wrapper is a validator rather than a vocabulary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str
    required_capability: str
    classification: Classification
    #: Sorted, so two identical classifications answer identically. `ColumnRule` holds a
    #: frozenset, whose iteration order is a property of the hashes in it.
    derived_from: list[str]
    #: The mark an uploaded table's column carries, or None: a built-in classification's
    #: rules were not made from marks. See `brain.knowledge.columns.access_of`.
    access: ColumnAccess | None = None


class ClassificationView(BaseModel):
    """One document's classification, whole.

    Not a `Page`. There is no cursor, no limit and no truncation: a classification is every
    column of one table, it is answered entire or not at all, and a shape carrying
    `next_cursor` would invite a pager over something that has no second page. See
    `A_CLASSIFICATION_IS_NOT_FILTERED_PER_CALLER`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    columns: list[ColumnView]
    #: `FieldPolicy.epoch`, the digest that changes when any rule does. Safe to answer
    #: because it is a digest over rules this response already carries in full, and useful
    #: because it is what says a classification is the one a review was computed against.
    epoch: str
    #: Whether this caller may have a change reviewed. Presentation only. See
    #: `AN_EDITABLE_FLAG_DECIDES_WHAT_IS_DRAWN_AND_NOTHING_ELSE`.
    editable: bool
    #: Whether this is an uploaded table's classification, so a mark can be applied to it.
    stored: bool = False
    #: The administrator's name for an uploaded table, and the column a question names a row
    #: by. Empty for a built-in classification.
    title: str = ""
    key_column: str = ""


class ColumnEdit(BaseModel):
    """The rule a console proposes for one column.

    `extra="forbid"`, so a body carrying `entity`, `column` or anything else is refused with
    a 422 naming the key rather than accepted and quietly ignored. Both of those are path
    segments and a model that accepted them as well would let a console change a column the
    address does not name.

    Every field is required, the derivation included, and that is `RungEdit`'s argument
    rather than a new one: a partial body means the field the console left out is the field
    a reader assumed it sent, and the form on the screen always holds all three. A rule that
    names no inputs says so with an empty list, which is a thing somebody wrote, where an
    absent key is a thing nobody did. The difference matters here more than it does on a
    rung, because dropping a derivation is the widening this whole surface exists to name.

    The capability's grammar is `brain.core.entitlement.CAPABILITY_RE` itself rather than a
    copy of it, so the pattern in the published document is the pattern the model enforces.
    What the pattern does not check is the verb set and the rule that a field rule must
    require a read; those live in `Capability` and `FieldRule`, and a body that breaks either
    is reported as a classification that would not load rather than as a malformed request,
    because that is what it is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    required_capability: Annotated[
        str, Field(min_length=3, max_length=200, pattern=CAPABILITY_RE.pattern)
    ]
    classification: Classification
    derived_from: Annotated[list[str], Field(max_length=MAX_DERIVED_FROM)]


class ColumnMark(BaseModel):
    """What an administrator says about one column of a table they uploaded.

    The mark and, for a derived column, the columns it is derived from. Nothing else: the
    capability and the sensitivity follow from the mark (`brain.knowledge.columns.marked`),
    and a body that could carry either would let a column marked restricted be governed by the
    table grant through a slip nobody reviewed. Every field is required, for `ColumnEdit`'s
    reason: an absent derivation is a thing nobody did, and an empty list is a thing somebody
    wrote.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    access: ColumnAccess
    derived_from: Annotated[list[str], Field(max_length=MAX_DERIVED_FROM)]


class ReviewView(BaseModel):
    """What one proposed rule would do, decided here.

    Deliberately carries no identifier, no timestamp and no revision. There is nothing
    stored for any of them to name, and a field that looked like the handle of a saved thing
    is the first thing a console would render as a receipt. See
    `A_REVIEW_STORES_NOTHING_AND_NO_AUDIT_ROW_IS_WRITTEN`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    column: str
    #: Why the proposed classification would not construct, in the classification layer's
    #: own words, or empty. When this is set every field below it is empty, because a
    #: classification that does not load has no consequences to report.
    would_not_load: str = ""
    #: What changed about this column. Empty means the rule is the one that stands.
    changes: list[Change] = []
    #: Whether any of it widens exposure. Computed here. See `WIDENING_IS_DECIDED_ON_THIS_SIDE`.
    widens: bool = False
    #: Columns a caller short of exactly one column would reach under the proposal and does
    #: not reach now. Never a count of anything withheld: these are named because the person
    #: reading them is deciding whether to expose them.
    exposed: list[str] = []
    #: The epoch of the classification that stands, and of the proposed one.
    #:
    #: The digest the answer cache is keyed on. It covers the capability, the sensitivity
    #: and the derivation of every column, so a proposal that changes any of them has two
    #: epochs that differ. Nothing in this response is derived from them: they say that a
    #: rule changed and never whether the change widens.
    epoch_now: str = ""
    epoch_after: str = ""


# -------------------------------------------------------------------- the comparison


def view_of(
    classification: TableClassification, *, editable: bool, stored: StoredTable | None = None
) -> ClassificationView:
    """One classification, copied field by field.

    Written out rather than built from `dataclasses.asdict`, for the reason
    `brain.routing_routes.view_of` gives about its own: a field added to `ColumnRule` would
    otherwise arrive in a response because a copy loop was generous, and the fields on a
    rule that governs disclosure are the last ones to publish by accident.

    Columns come back in `TableClassification.columns()` order, which is sorted, so the
    order a rule was declared in cannot be read off the answer.
    """
    return ClassificationView(
        entity=classification.entity,
        columns=[
            ColumnView(
                column=rule.column,
                required_capability=rule.required_capability.value,
                classification=rule.classification,
                derived_from=sorted(rule.derived_from),
                access=None if stored is None else access_of(classification.entity, rule),
            )
            for name in classification.columns()
            if (rule := classification.rule_for(name)) is not None
        ],
        epoch=classification.policy().epoch(),
        editable=editable,
        stored=stored is not None,
        title="" if stored is None else stored.title,
        key_column="" if stored is None else stored.key_column,
    )


def replacing(current: TableClassification, rule: ColumnRule) -> TableClassification:
    """The classification with this rule in place of whatever governed the same column.

    Replacement rather than addition, which is the shape `FieldPolicy.with_rules` takes and
    for its stated reason: this is the deliberate-edit path, so the caller is saying what the
    rule should now be. Adding would raise `ColumnClassificationError` for a column that is
    already classified, and a review that refused to look at the commonest edit there is
    would be a review of nothing.
    """
    kept = tuple(existing for existing in current.rules if existing.column != rule.column)
    return TableClassification(entity=current.entity, rules=(*kept, rule))


def changes_between(current: ColumnRule | None, proposed: ColumnRule) -> tuple[Change, ...]:
    """What one proposed rule does to the column it governs.

    A tuple rather than a single verdict, because a rule can change in two directions at
    once: a column can become less sensitive while gaining a derivation, and a precedence
    order that reported only the first would hide whichever the reader needed. Sorted, so
    two identical proposals report identically.
    """
    if current is None:
        # Nothing classified this column, so `compute_mask` withheld it from everybody by
        # default-deny. Classifying it is therefore a widening whatever the rule says, and
        # nothing else about the rule is a change, because there was nothing to change from.
        return (Change.ADDED,)
    found: list[Change] = []
    if current.required_capability != proposed.required_capability:
        found.append(Change.CAPABILITY)
    if proposed.classification.rank > current.classification.rank:
        found.append(Change.MORE_SENSITIVE)
    elif proposed.classification.rank < current.classification.rank:
        found.append(Change.LESS_SENSITIVE)
    if current.derived_from - proposed.derived_from:
        found.append(Change.DERIVATION_DROPPED)
    if proposed.derived_from - current.derived_from:
        found.append(Change.DERIVATION_ADDED)
    return tuple(sorted(found))


def newly_reachable(current: TableClassification, proposed: TableClassification) -> tuple[str, ...]:
    """Columns a caller short of exactly one column would see under the proposal, and not now.

    The check the syntactic comparison cannot make. Dropping the derivation on `cost` is one
    line in a rule and its consequence is that `margin` stops being withheld from everybody
    who lacks the cost capability, which is a fact about a different column entirely. This
    runs `close_over_derivations`, the function M7.5.1 shipped, over both classifications
    rather than reimplementing the closure.

    One missing column at a time, and `None` for the caller missing none. Every subset is the
    honest question and there are two to the power of the column count of them; one missing
    column is the shape the derivation rule was written for, and it is the price list:
    Finance holds `read:price_list.cost` and nobody else does.

    **The caller missing none earns its place on exactly one classification: an empty one.**
    Mutation established the bound rather than a comment guessing at it. Wherever both
    classifications name two columns or more, anything the whole-set comparison would find is
    already found by the sweep, because a column newly reachable to everybody is newly
    reachable to each caller short of some other column. The case it does not cover is the
    first column ever classified, where the sweep's only iteration removes that very column
    from both sides and compares two empty sets.
    `test_the_only_column_of_a_new_classification_is_reported_as_newly_reachable` is that
    case.

    A widening that only a caller short of two columns at once would see is not found here.
    That is a gap and it is stated rather than papered over; `WIDENING_CHANGES` is the
    syntactic half that still names one.
    """
    names = set(current.columns()) | set(proposed.columns())
    gained: set[str] = set()
    for missing in [*sorted(names), None]:
        short = set() if missing is None else {missing}
        before = close_over_derivations(frozenset(set(current.columns()) - short), current)
        after = close_over_derivations(frozenset(set(proposed.columns()) - short), proposed)
        gained |= after - before
    return tuple(sorted(gained))


def _would_not_load(exc: ColumnClassificationError | ValidationError) -> str:
    """The classification layer's own sentence for why a proposal does not construct.

    Quoted rather than composed, so a rule this module has never heard of still explains
    itself and so there is one wording per failure rather than two. Bounded, because a
    pydantic report over a body with sixty-four derivation entries in it is longer than a
    screen and the useful part is at the front.
    """
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        return str(first.get("msg", ""))[:MAX_REFUSAL_CHARS]
    return str(exc)[:MAX_REFUSAL_CHARS]


def review(entity: str, column: str, edit: ColumnEdit) -> ReviewView:
    """What this proposal does to this column of this classification.

    Pure: it takes the entity's name and a proposed rule, reads the classification out of
    the same registry `brain.tools.startup` builds row tools from, and returns an answer. No
    session, no request, no state. That is what makes the property below assertable at all:
    a review is answered identically on a process with a database and on one without,
    because there is nothing here that could want one.

    A classification that would not construct is an answer rather than a refusal. See the
    module docstring: the failure it stands for is a person believing they changed something
    while the previous rules stayed in place.
    """
    current = classification_for(entity)
    if current is None:
        # Unreachable through the route, which checks this first. Written as a refusal
        # anyway, because the alternative is an `AttributeError` for whoever calls this
        # function directly, and the one thing this module must never do is answer a
        # comparison against a classification it does not have.
        raise _no_classification_here()
    return review_against(current, column, edit)


def review_against(
    current: TableClassification, column: str, edit: ColumnEdit | ColumnMark
) -> ReviewView:
    """What a proposed rule or mark does to one column of the classification that stands.

    One comparison for both bodies, so a mark on an uploaded table and a rule on a built-in
    one are judged by the same arithmetic. A mark becomes its rule through `marked` inside the
    same `try` that builds a rule, so a derived mark naming no input is a classification that
    would not load, reported in the columns layer's own words.
    """
    entity = current.entity
    epoch_now = current.policy().epoch()
    try:
        if isinstance(edit, ColumnMark):
            rule = marked(entity, column, edit.access, edit.derived_from)
        else:
            rule = ColumnRule(
                column=column,
                required_capability=Capability(value=edit.required_capability),
                classification=edit.classification,
                derived_from=frozenset(edit.derived_from),
            )
        after = replacing(current, rule)
        # The policy is built here rather than at the end, because this is where `FieldRule`
        # checks that the column is a name and that the capability is a read, and both are
        # findings rather than crashes.
        epoch_after = after.policy().epoch()
    except (ColumnClassificationError, ValidationError) as exc:
        return ReviewView(
            entity=entity,
            column=column,
            would_not_load=_would_not_load(exc),
            epoch_now=epoch_now,
        )

    changes = changes_between(current.rule_for(column), rule)
    exposed = newly_reachable(current, after)
    return ReviewView(
        entity=entity,
        column=column,
        changes=list(changes),
        widens=bool(set(changes) & WIDENING_CHANGES) or bool(exposed),
        exposed=list(exposed),
        epoch_now=epoch_now,
        epoch_after=epoch_after,
    )


# ------------------------------------------------------------------------- the wiring


def _no_classification_here() -> Absent:
    """The one refusal this router makes.

    Named rather than raised inline in four places, so the four refusals are the same
    refusal. A caller who may not read a classification, a caller who may read but not
    review one, and anybody asking about an entity nothing classifies get one answer;
    `brain.app.handle_brain_error` sends `Absent.public_message` and the string below reaches
    a log.
    """
    return Absent("no classification is answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["classification"])


async def _resolved(
    request: Request, entity: str
) -> tuple[TableClassification, StoredTable | None] | None:
    """The classification governing this entity: an uploaded table's, else a built-in one.

    Uploaded first, and the two can never both answer, because an upload under a name the
    product classifies is refused. A name that is not a name is not looked up, so a path
    segment never reaches a query it could not match anyway.
    """
    tables = classified_tables_of(request.app.state)
    if tables is not None and _ENTITY_RE.match(entity):
        stored = await tables.table(entity)
        if stored is not None:
            return stored.classification, stored
    built_in = classification_for(entity)
    return None if built_in is None else (built_in, None)


def _may_change(asked: Asking) -> bool:
    """Both capabilities, which every route that reviews or writes requires alike."""
    return asked.reach.holds(CLASSIFICATION_READ, asked.now) and asked.reach.holds(
        CLASSIFICATION_WRITE, asked.now
    )


def _tables_or_fault(request: Request) -> ClassifiedTables:
    """Where uploaded tables are kept, or a process-level fault on a process with no database.

    `Failed` rather than `Absent`, for `brain.routing_routes._require_sessions`'s reason: an
    instance with no pool is broken rather than empty, and only a caller already holding both
    capabilities reaches this line.
    """
    tables = classified_tables_of(request.app.state)
    if tables is None:
        raise Failed("no database on this process")
    return tables


@router.get(
    "/classifications/{entity}", response_model=ClassificationView, responses=COMMON_RESPONSES
)
async def classification(request: Request, entity: str, asked: Asked) -> ClassificationView:
    """Every column of one table's classification, and what it takes to see each.

    The capability first and the entity second, which reads as the ordering property
    `brain.routing_routes.rungs` has and is not one. What makes the two refusals one refusal
    here is that both raise `_no_classification_here`, so the answer is identical whichever
    check fires and swapping the two lines changes no response. The order is kept because the
    entity is now looked up in a database for an uploaded table, and a lookup made before the
    capability is checked is a query a stranger can time.
    """
    if not asked.reach.holds(CLASSIFICATION_READ, asked.now):
        log.info("classification not answerable", principal=asked.caller.principal.id)
        raise _no_classification_here()

    found = await _resolved(request, entity)
    if found is None:
        log.info("classification not found", entity=entity)
        raise _no_classification_here()

    classification, stored = found
    return view_of(
        classification,
        editable=asked.reach.holds(CLASSIFICATION_WRITE, asked.now),
        stored=stored,
    )


@router.post(
    "/classifications/{entity}/columns/{column}/review",
    response_model=ReviewView,
    responses=COMMON_RESPONSES,
)
async def review_column(
    request: Request, entity: str, column: str, edit: ColumnEdit, asked: Asked
) -> ReviewView:
    """What a proposed rule for one column would do. Nothing is stored.

    Both capabilities, and the same refusal for either. A caller who may read a
    classification and not review a change to it gets the answer a caller who may do neither
    gets, so the reply says nothing about which half they are missing.

    The entity is checked after the capabilities and produces the same refusal again, so a
    caller cannot use a proposal to find out what this installation classifies.
    """
    if not _may_change(asked):
        log.info("classification not reviewable", principal=asked.caller.principal.id)
        raise _no_classification_here()

    found = await _resolved(request, entity)
    if found is None:
        log.info("classification not found", entity=entity)
        raise _no_classification_here()

    return review_against(found[0], column, edit)


# --------------------------------------------------------- an uploaded table (M7.5.3)


class MarkApplied(BaseModel):
    """What applying a mark did: whether it was written, the verdict, and the table after.

    `applied` is false exactly when the review says the proposal would not load, or names a
    column the table does not carry, and then nothing was written and `classification` is the
    one that stands.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    applied: bool
    review: ReviewView
    classification: ClassificationView


class TableUpload(BaseModel):
    """One file to hold as a classified table, and what to call it.

    The file travels as base64 inside JSON rather than as a multipart form, because this
    application carries no multipart parser and a price list is small; the bound is
    `MAX_TABLE_FILE_BYTES` once decoded. `key_column` is the heading a question names a row
    by, as the file spells it; absent, the table keeps the one it had, or takes its first
    column. The entity is the address, for `ColumnEdit`'s reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE_CHARS)]
    filename: Annotated[str, Field(min_length=1, max_length=MAX_TITLE_CHARS)]
    content_base64: Annotated[str, Field(min_length=1, max_length=MAX_UPLOAD_CHARS)]
    key_column: Annotated[str, Field(max_length=MAX_TITLE_CHARS)] | None = None


class TableUploaded(BaseModel):
    """What an upload did: the classification it produced, or why nothing was stored.

    A refusal is an answer rather than an error status, for the reason `would_not_load` is:
    the person holding the file needs the sentence saying which heading or which row is
    wrong, and a 422 about a body would hand them the request's shape instead.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refused: str = ""
    classification: ClassificationView | None = None


def _in_place(current: TableClassification, rule: ColumnRule) -> TableClassification:
    """The classification with this rule where the old one was, so the upload's order stands."""
    return TableClassification(
        entity=current.entity,
        rules=tuple(rule if old.column == rule.column else old for old in current.rules),
    )


def _upload_refusal(entity: str) -> str:
    """Why this name cannot be an uploaded table's, or empty."""
    if not _ENTITY_RE.match(entity) or len(entity) > MAX_ENTITY_CHARS:
        return (
            "a table's name is lowercase letters, digits and underscores, starting with a "
            f"letter, at most {MAX_ENTITY_CHARS} characters"
        )
    if any(known.entity == entity for known in every_row_classification()):
        return A_NAME_THE_PRODUCT_CLASSIFIES
    return ""


@router.put(
    "/classifications/{entity}/table", response_model=TableUploaded, responses=COMMON_RESPONSES
)
async def upload_table(
    request: Request, entity: str, body: TableUpload, asked: Asked
) -> TableUploaded:
    """Hold a CSV or an XLSX price list as this table's rows, and answer its classification.

    Both capabilities, refused as every other route here refuses. A first upload classifies
    every column restricted unless `PRICE_LIST` already marks it; a later one keeps the marks
    that stand and moves Ask to the new rows in the same transaction. See
    `brain.knowledge.classified_rows.next_upload`.
    """
    if not _may_change(asked):
        log.info("classification not uploadable", principal=asked.caller.principal.id)
        raise _no_classification_here()
    tables = _tables_or_fault(request)

    refused = _upload_refusal(entity)
    if refused:
        return TableUploaded(refused=refused)
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        return TableUploaded(refused="the file did not arrive intact; choose it again")
    try:
        parsed = read_table_file(body.filename, content)
    except TableFileError as exc:
        return TableUploaded(refused=str(exc)[:MAX_REFUSAL_CHARS])

    key: str | None = None
    if body.key_column:
        try:
            key = column_name_for(body.key_column)
        except ColumnClassificationError as exc:
            return TableUploaded(refused=str(exc)[:MAX_REFUSAL_CHARS])
        if key not in parsed.columns:
            return TableUploaded(refused="no heading in the file is the key column named")

    existing = await tables.table(entity)
    try:
        table = next_upload(
            existing,
            entity=entity,
            title=body.title.strip(),
            key_column=key,
            columns=parsed.columns,
        )
        stored = await tables.upload(
            table,
            parsed.rows,
            actor_id=asked.caller.principal.id,
            attribution=of_request(asked),
        )
    except (ColumnClassificationError, ClassifiedTableStoreError) as exc:
        return TableUploaded(refused=str(exc)[:MAX_REFUSAL_CHARS])

    log.info("classified table uploaded", entity=entity, version=stored.version)
    return TableUploaded(
        classification=view_of(stored.classification, editable=True, stored=stored)
    )


@router.post(
    "/classifications/{entity}/columns/{column}/marks/review",
    response_model=ReviewView,
    responses=COMMON_RESPONSES,
)
async def review_mark(
    request: Request, entity: str, column: str, mark: ColumnMark, asked: Asked
) -> ReviewView:
    """What marking one column of an uploaded table would do. Nothing is stored.

    Only an uploaded table takes a mark; a built-in classification is refused as an absent
    one is, because its rules were never marks and the console never offers it.
    """
    if not _may_change(asked):
        log.info("mark not reviewable", principal=asked.caller.principal.id)
        raise _no_classification_here()
    stored = await _stored_or_absent(request, entity)
    return _mark_review(stored, column, mark)


@router.put(
    "/classifications/{entity}/columns/{column}/marks",
    response_model=MarkApplied,
    responses=COMMON_RESPONSES,
)
async def apply_mark(
    request: Request, entity: str, column: str, mark: ColumnMark, asked: Asked
) -> MarkApplied:
    """Mark one column of an uploaded table, and store the classification that makes.

    The review is computed first and returned with the result, so the response that made a
    widening names it. See `AN_APPLIED_MARK_IS_STORED_AND_LEDGERED`.
    """
    if not _may_change(asked):
        log.info("mark not appliable", principal=asked.caller.principal.id)
        raise _no_classification_here()
    tables = _tables_or_fault(request)
    stored = await _stored_or_absent(request, entity)
    verdict = _mark_review(stored, column, mark)
    if verdict.would_not_load:
        return MarkApplied(
            applied=False,
            review=verdict,
            classification=view_of(stored.classification, editable=True, stored=stored),
        )
    after = _in_place(stored.classification, marked(entity, column, mark.access, mark.derived_from))
    written = await tables.classify(
        entity, after, actor_id=asked.caller.principal.id, attribution=of_request(asked)
    )
    if written is None:
        # Retired between the read and the write. The same refusal an absent table gets.
        raise _no_classification_here()
    log.info("classified table marked", entity=entity, widens=verdict.widens)
    return MarkApplied(
        applied=True,
        review=verdict,
        classification=view_of(written.classification, editable=True, stored=written),
    )


async def _stored_or_absent(request: Request, entity: str) -> StoredTable:
    """The uploaded table with this name, or the one refusal this router makes."""
    tables = _tables_or_fault(request)
    stored = await tables.table(entity) if _ENTITY_RE.match(entity) else None
    if stored is None:
        log.info("classified table not found", entity=entity)
        raise _no_classification_here()
    return stored


def _mark_review(stored: StoredTable, column: str, mark: ColumnMark) -> ReviewView:
    """The review of one mark, refusing a column the upload did not carry.

    A mark can only describe a column that has values under it. Marking a name the file did
    not have would classify a column with no rows, and the review would call it an addition
    and a widening of something that does not exist.
    """
    if stored.classification.rule_for(column) is None:
        return ReviewView(
            entity=stored.entity,
            column=column,
            would_not_load="no column of this table has that name",
            epoch_now=stored.classification.policy().epoch(),
        )
    return review_against(stored.classification, column, mark)
