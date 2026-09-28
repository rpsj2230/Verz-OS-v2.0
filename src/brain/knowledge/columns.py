"""Classifying the columns inside one document, so a price list can be shared once.

Pricing is a field-level problem wearing a document-level costume. A price list carries the
sell price everybody needs beside the cost and margin almost nobody may see, and the obvious
move is to restrict the document and keep a second, safer copy for the rest of the company.
Within a year there are three near-identical price lists and two of them are stale, which is
a worse outcome than the leak the restriction was meant to prevent, because a wrong price
quoted to a client is noticed by the client.

So the columns are classified and the document is not. A caller sees the sell price; the cost
column is a lock beside it.

**Derivation is the part that gets missed.** Classifying `cost` and leaving `sell_price` and
`margin` visible hides nothing at all: cost is a subtraction away, and the person doing the
subtraction is not doing anything wrong, because both numbers were shown to them. This is the
same rule `brain.core.redaction` applies to counts, where a total beside a filtered list hands
over the hidden remainder by subtraction. A column that can be reconstructed from visible
columns is a visible column, and the only way to withhold it is to withhold one of its inputs.

**The most sensitive input is the one withheld.** Two alternatives were rejected. Withholding
every input, which takes the sell price away from everybody and returns the whole company to
asking Finance for a number. And withholding nothing and reporting the risk, which is a
warning in a log about a disclosure that has already happened.

**This does not reimplement redaction.** The mask comes from `brain.core.redaction.compute_mask`
and the default-deny rule comes with it: a column nobody classified is withheld rather than
returned. What this module adds is the derivation closure, which the walker cannot do because
it sees one field at a time and derivation is a property of a set.

The rules are a knowledge-layer type rather than an extension of `brain.core.field_policy`,
because derivation is a relationship between the columns of one table and not a property every
field in the system has. It compiles down to ordinary `FieldRule`s, so the redactor stays the
single place a field-level decision is made.

**The compiled rule carries the derivation, and until 2026-09-28 it did not.**
`ColumnRule.as_field_rule` dropped `derived_from`, so the policy a classification compiled to
held no derivation: the redactor's own closure never fired for a column classification, and
`FieldPolicy.epoch`, which has digested derivations since 2026-09-21, could not see one.
Dropping the derivation on `cost` changed what every caller short of the cost capability sees
and left the epoch identical, so the answer cache keyed on it would have gone on serving rows
closed under the old rule. See `A_DERIVATION_IS_PART_OF_THE_POLICY_IT_COMPILES_TO`.

**A table somebody uploads is classified by marks, not by capabilities.** An administrator
says of each column whether it is open, restricted or derived, and `marked` turns that into
a `ColumnRule`: an open column needs only the grant on the table, `read:<table>`, so everyone
permitted the table reads it; a restricted column needs its own grant,
`read:<table>.<column>`; a derived one is restricted and names the columns it can be worked
out from. The capability is computed rather than typed because a typed one is where a
column meant to be restricted ends up governed by the table grant through a slip of the
keyboard, and the review would only see a capability change with no direction.

Task ids: M7.5.1, M7.5.2, M7.5.3
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.redaction import compute_mask, render_lock

#: Why `as_field_rule` carries the derivation into the rule it compiles to.
A_DERIVATION_IS_PART_OF_THE_POLICY_IT_COMPILES_TO: Final = (
    "A classification reaches the rest of the system as a FieldPolicy: the redactor masks with "
    "it and the answer cache keys on its epoch. A derivation left out of the compiled rule is "
    "invisible to both, so the redactor never closes over it and dropping one leaves the epoch "
    "where it was, while every caller short of the derived column now sees an input that "
    "reconstructs it. The derivation is therefore compiled in with the capability and the "
    "classification, and the epoch moves when it does."
)


#: Why a derivation whose every input is open refuses to load.
A_DERIVATION_FROM_OPEN_COLUMNS_PROTECTS_NOTHING: Final = (
    "Everyone permitted the table reads an open column, so a column derived only from open "
    "columns can be worked out by all of them, and the closure could keep it hidden only by "
    "withholding one of the open inputs from everybody. It did exactly that until 2026-09-28: "
    "opening the cost while the margin stayed derived from the sell price and the cost withheld "
    "the sell price, the one column the company needs, because two open columns tie on "
    "sensitivity and the tie is broken by name. Such a classification is refused, so an open "
    "column is never withheld from anybody the table admits, and the administrator decides "
    "which of the three to change."
)


class ColumnClassificationError(Exception):
    """A column classification that could not do what it says.

    Outside the `brain.core.errors` taxonomy, like `PolicyConflictError` and for the same
    reason: this is a build-time failure that should stop a classification from loading,
    rather than something that degrades an answer at request time.
    """


@dataclass(frozen=True)
class ColumnRule:
    """One column of a tabular document, and what it takes to see it (M7.5.1).

    `derived_from` names the columns this one can be reconstructed from. It is a set rather
    than a formula because the arithmetic does not matter: whether the relationship is a
    subtraction, a ratio or a lookup, the disclosure is identical once every input is visible.
    Storing a formula would invite somebody to evaluate it, and a classification that computes
    values is a classification that has copied the data.
    """

    column: str
    required_capability: Capability
    classification: Classification
    derived_from: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.column in self.derived_from:
            msg = (
                f"{self.column!r} is declared as derived from itself, which is a rule with "
                "no answer; a derivation names the other columns that reconstruct this one"
            )
            raise ColumnClassificationError(msg)

    def as_field_rule(self, entity: str) -> FieldRule:
        """The ordinary field rule this column compiles to, derivation included.

        `FieldRule` validates that the capability is a read, so a column governed by a write
        capability is refused here without this module restating the reason. The derivation
        is sorted because it is a set, and a frozenset's order is a property of the hashes in
        it: see `A_DERIVATION_IS_PART_OF_THE_POLICY_IT_COMPILES_TO`.
        """
        return FieldRule(
            entity=entity,
            field=self.column,
            required_capability=self.required_capability,
            classification=self.classification,
            derived_from=tuple(sorted(self.derived_from)),
        )


@dataclass(frozen=True)
class TableClassification:
    """Every column of one tabular document, and the derivations between them.

    The entity name is the table's, not the document's, because that is what the field policy
    and every capability are written against: `read:price_list.cost` has to mean the same
    thing whether it arrives from an uploaded spreadsheet or from a connector.
    """

    entity: str
    rules: tuple[ColumnRule, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.column in seen:
                # Two rules for one column make "may this person see it" an evaluation-order
                # question, which is the ambiguity `PolicyConflictError` exists to refuse.
                msg = f"{self.entity}.{rule.column} is classified twice"
                raise ColumnClassificationError(msg)
            seen.add(rule.column)
        for rule in self.rules:
            unknown = sorted(rule.derived_from - seen)
            if unknown:
                # A derivation pointing at a column that does not exist never fires, and a
                # rule that never fires reads as a control while being a comment.
                msg = (
                    f"{self.entity}.{rule.column} is declared as derived from {unknown}, "
                    f"which {'are' if len(unknown) > 1 else 'is'} not classified here"
                )
                raise ColumnClassificationError(msg)
        # Spelled out rather than calling `table_capability`, which is declared further down
        # and would not exist yet when `PRICE_LIST` is built at import.
        table_grant = Capability(value=f"read:{self.entity}")
        for rule in self.rules:
            inputs = [self.rule_for(name) for name in sorted(rule.derived_from)]
            if inputs and all(
                one is not None and one.required_capability == table_grant for one in inputs
            ):
                # See `A_DERIVATION_FROM_OPEN_COLUMNS_PROTECTS_NOTHING`.
                msg = (
                    f"{self.entity}.{rule.column} is derived from {sorted(rule.derived_from)}, "
                    "which are all open, so everybody the table admits can work it out; mark "
                    "one of them restricted, or stop marking this column derived"
                )
                raise ColumnClassificationError(msg)

    def policy(self) -> FieldPolicy:
        """The field policy these columns compile to.

        Built fresh rather than cached, because a `FieldPolicy` carries the epoch that goes
        into the answer cache key, and a stale cached policy would hold an epoch that no
        longer describes the rules.
        """
        return FieldPolicy(rules=tuple(rule.as_field_rule(self.entity) for rule in self.rules))

    def rule_for(self, column: str) -> ColumnRule | None:
        for rule in self.rules:
            if rule.column == column:
                return rule
        return None

    def columns(self) -> tuple[str, ...]:
        """Every classified column, sorted, so two identical classifications report alike."""
        return tuple(sorted(rule.column for rule in self.rules))


def _most_sensitive(columns: Iterable[str], classification: TableClassification) -> str:
    """Which of these columns to withhold when a derivation has to be broken.

    Highest classification wins, and the column name breaks a tie. The tie-break is not
    cosmetic: without it, two equally sensitive inputs are chosen between by iteration order,
    so the same caller asking the same question twice could see different columns and would
    reasonably conclude the permission model is random.
    """
    ranked: list[tuple[int, str]] = []
    for column in columns:
        rule = classification.rule_for(column)
        rank = rule.classification.rank if rule is not None else Classification.RESTRICTED.rank
        ranked.append((rank, column))
    return max(ranked, key=lambda pair: (pair[0], pair[1]))[1]


def close_over_derivations(
    allowed: frozenset[str], classification: TableClassification
) -> frozenset[str]:
    """Remove visible columns that together reconstruct a withheld one.

    Iterated to a fixed point rather than swept once. Withholding one column can make a second
    derivation resolvable that was not before, and a single pass would leave the second one
    standing while every test about the first passed.

    The loop terminates because each round removes at least one column from a finite set, and
    a column is never added back.
    """
    surviving = set(allowed)
    changed = True
    while changed:
        changed = False
        for rule in classification.rules:
            if rule.column in surviving or not rule.derived_from:
                continue
            if rule.derived_from <= surviving:
                surviving.discard(_most_sensitive(rule.derived_from, classification))
                changed = True
    return frozenset(surviving)


@dataclass(frozen=True)
class ColumnView:
    """One row as one caller may see it.

    `locked` names the columns withheld and carries no reason, exactly as
    `brain.core.redaction.LockedField` does: the reason is the part that leaks, because "out
    of scope" tells the asker the column has values elsewhere and "unclassified" tells them
    about the policy. Every lock is the same lock.

    A locked column name is shown, and that is deliberate rather than an oversight. This is a
    row the caller is already entitled to see, and within such a row the lock is the product:
    it is what makes "you may see the sell price and not the cost" legible instead of leaving
    a person to wonder whether the column exists.
    """

    entity: str
    values: dict[str, Any]
    locked: tuple[str, ...] = ()

    def render(self, column: str) -> str:
        """What one column shows: its value, or the same lock text every viewer sees."""
        if column in self.values:
            return str(self.values[column])
        return render_lock()


def project_row(
    classification: TableClassification,
    row: Mapping[str, Any],
    *,
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> ColumnView:
    """One row of a tabular document, narrowed to what this caller may see (M7.5.2).

    The mask is computed by the redactor, so default-deny, the scope predicate and the reason
    taxonomy all behave here exactly as they do everywhere else. The derivation closure runs
    afterwards, because it needs the whole visible set and the walker only ever sees one field.

    The row is passed to the mask before anything is removed from it, which is the ordering
    `compute_mask` documents: a scope predicate evaluated against a row whose `department` key
    had already been dropped refuses everything for everybody, and that failure reads as a
    permission problem rather than as an ordering one.
    """
    present = [key for key in row if key not in ("entity", "id", "@entity", "@id")]
    mask = compute_mask(
        classification.entity,
        present,
        entitlement=entitlement,
        policy=classification.policy(),
        row=row,
        now=now,
    )
    visible = close_over_derivations(
        frozenset(name for name in mask.allowed if name in present), classification
    )
    return ColumnView(
        entity=classification.entity,
        values={name: row[name] for name in present if name in visible},
        # Sorted, so the order locks are reported in cannot carry the order the source
        # returned its columns in. That order differs between callers and is readable as a
        # signal about what each of them was refused.
        locked=tuple(sorted(name for name in present if name not in visible)),
    )


# ------------------------------------------------------- the price list (M7.5.2)

#: The classification a price list ships with. A default rather than a fixture, because the
#: architecture names this exact case as the one that drives the whole feature, and a default
#: nobody wrote down is a default every installation reinvents differently.
#:
#: `cost` and `margin` each name the other two columns as inputs, which is what makes the
#: subtraction visible to `close_over_derivations`. Sell price is deliberately not derived
#: from anything: it is the column the whole company needs, and a derivation on it would make
#: it the first thing withheld.
PRICE_LIST: Final = TableClassification(
    entity="price_list",
    rules=(
        ColumnRule(
            column="sku",
            required_capability=Capability(value="read:price_list.sku"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="name",
            required_capability=Capability(value="read:price_list.name"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="sell_price",
            required_capability=Capability(value="read:price_list.sell_price"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="cost",
            required_capability=Capability(value="read:price_list.cost"),
            classification=Classification.CONFIDENTIAL,
            derived_from=frozenset({"sell_price", "margin"}),
        ),
        ColumnRule(
            column="margin",
            required_capability=Capability(value="read:price_list.margin"),
            classification=Classification.CONFIDENTIAL,
            derived_from=frozenset({"sell_price", "cost"}),
        ),
    ),
)


# ----------------------------------------------- a table somebody uploaded (M7.5.3)


class ColumnAccess(enum.StrEnum):
    """What an administrator says about one column of a table they uploaded.

    Three words rather than a capability and a sensitivity level, because these are the three
    decisions a person classifying a price list is actually making, and each one fixes the
    other two fields. `marked` is the one translation from a word to a rule.
    """

    #: Everyone permitted the table reads it: the column needs only `read:<table>`.
    OPEN = "open"
    #: Only a person holding the column's own grant, `read:<table>.<column>`, reads it.
    RESTRICTED = "restricted"
    #: Restricted, and it can be worked out from the columns it names, so seeing all of those
    #: withholds the most sensitive of them. See `close_over_derivations`.
    DERIVED = "derived"


#: The sensitivity an open column is recorded at, and a restricted or derived one.
#:
#: Fixed by the mark rather than chosen beside it. The level decides which input the closure
#: withholds when a derivation has to be broken (`_most_sensitive`), so an open column ranked
#: above a restricted one would have the closure take the sell price and leave the cost.
OPEN_SENSITIVITY: Final = Classification.INTERNAL
RESTRICTED_SENSITIVITY: Final = Classification.CONFIDENTIAL

#: The words a column name is built from, and how long one may be. A column is a field name to
#: every layer below (`brain.core.field_policy.NAME_PATTERN`), and 60 characters is the entity
#: width, which is far past any heading a spreadsheet carries.
_NOT_A_NAME_CHARACTER: Final = re.compile(r"[^a-z0-9]+")
MAX_COLUMN_NAME_CHARS: Final = 60

#: Names the row plane reads as a record's tag rather than as a field. A column by either name
#: would overwrite the tag and the redactor would drop the record whole (`RowTool` refuses the
#: same two for the same reason).
RESERVED_COLUMN_NAMES: Final = frozenset({"entity", "id"})


def table_capability(entity: str) -> Capability:
    """`read:<table>`: the grant that admits a row of this table, and every open column of it.

    The same string `brain.knowledge.rows.entity_capability` builds, which a test holds equal;
    it is not imported from there because that module imports this one.
    """
    return Capability(value=f"read:{entity}")


def column_capability(entity: str, column: str) -> Capability:
    """`read:<table>.<column>`: the grant a restricted or derived column needs of its own."""
    return Capability(value=f"read:{entity}.{column}")


def marked(
    entity: str, column: str, access: ColumnAccess, derived_from: Iterable[str] = ()
) -> ColumnRule:
    """The rule one mark stands for.

    A derived column must name what it is derived from and nothing else may. An open column
    with a derivation would be a rule the closure never consults, because an open column is
    never withheld from anybody who reaches the table (`TableClassification` refuses the one
    arrangement that would withhold it: see `A_DERIVATION_FROM_OPEN_COLUMNS_PROTECTS_NOTHING`),
    and a derivation that never fires reads as a control while being a comment. A derived
    column with none is a restricted column with a misleading word on it.
    """
    inputs = frozenset(derived_from)
    if access is ColumnAccess.DERIVED and not inputs:
        msg = f"{column!r} is marked derived and names no column it is derived from"
        raise ColumnClassificationError(msg)
    if access is not ColumnAccess.DERIVED and inputs:
        msg = (
            f"{column!r} is marked {access.value} and names columns it is derived from; only "
            "a derived column names its inputs"
        )
        raise ColumnClassificationError(msg)
    if access is ColumnAccess.OPEN:
        return ColumnRule(
            column=column,
            required_capability=table_capability(entity),
            classification=OPEN_SENSITIVITY,
        )
    return ColumnRule(
        column=column,
        required_capability=column_capability(entity, column),
        classification=RESTRICTED_SENSITIVITY,
        derived_from=inputs,
    )


def access_of(entity: str, rule: ColumnRule) -> ColumnAccess | None:
    """The mark a rule was made from, or None for a rule no mark describes.

    None is a built-in classification's rule: `PRICE_LIST` gives the sell price a grant of its
    own, so it is neither open (the table grant) nor restricted in the uploaded sense. Reported
    as None rather than as the nearest word, because a nearest word on a policy screen is a
    statement about who may see a column that is not true.
    """
    if rule == marked(entity, rule.column, ColumnAccess.OPEN):
        return ColumnAccess.OPEN
    if not rule.derived_from and rule == marked(entity, rule.column, ColumnAccess.RESTRICTED):
        return ColumnAccess.RESTRICTED
    if rule.derived_from and rule == marked(
        entity, rule.column, ColumnAccess.DERIVED, rule.derived_from
    ):
        return ColumnAccess.DERIVED
    return None


def column_name_for(heading: str) -> str:
    """The field name a spreadsheet heading becomes: `Sell Price (SGD)` is `sell_price_sgd`.

    Lowercase words joined by underscores, because every layer below reads a column as a field
    name and nothing else. Refuses rather than inventing one: a heading with no letters in it,
    one that starts with a digit, a reserved name, or one past the width. An invented name is a
    column nobody recognises on the classification screen, which is where they decide who sees
    it.
    """
    name = _NOT_A_NAME_CHARACTER.sub("_", heading.strip().casefold()).strip("_")
    if not name:
        msg = f"the heading {heading!r} has no letters or digits to name a column with"
        raise ColumnClassificationError(msg)
    if not name[0].isalpha():
        msg = f"the heading {heading!r} starts with a digit; a column name starts with a letter"
        raise ColumnClassificationError(msg)
    if len(name) > MAX_COLUMN_NAME_CHARS:
        msg = f"the heading {heading!r} is longer than {MAX_COLUMN_NAME_CHARS} characters"
        raise ColumnClassificationError(msg)
    if name in RESERVED_COLUMN_NAMES:
        msg = (
            f"the heading {heading!r} would be the column {name!r}, which every record already "
            "uses for its own tag; rename that heading"
        )
        raise ColumnClassificationError(msg)
    return name


def first_classification(entity: str, columns: Sequence[str]) -> TableClassification:
    """How a freshly uploaded table's columns start, before anybody marks one.

    **Every column starts restricted**, which is default-deny arriving at upload: nobody reads a
    column of a new table until an administrator opens it, so an upload can never be the act
    that widens anything.

    The one exception is a column `PRICE_LIST` already classifies, which starts with the mark
    that classification gives it: the sell price, the name and the SKU open, and the cost and
    the margin derived from the columns of theirs this table also carries. That is what the
    shipped price list is for (see its own comment), and a derivation whose inputs are not all
    here starts restricted instead, because a derivation naming a missing column refuses to
    load.
    """
    rules: list[ColumnRule] = []
    present = set(columns)
    for column in columns:
        known = PRICE_LIST.rule_for(column)
        if known is None:
            rules.append(marked(entity, column, ColumnAccess.RESTRICTED))
        elif known.derived_from and known.derived_from <= present:
            rules.append(marked(entity, column, ColumnAccess.DERIVED, known.derived_from))
        elif known.derived_from or known.classification.rank > OPEN_SENSITIVITY.rank:
            rules.append(marked(entity, column, ColumnAccess.RESTRICTED))
        else:
            rules.append(marked(entity, column, ColumnAccess.OPEN))
    return TableClassification(entity=entity, rules=tuple(rules))
