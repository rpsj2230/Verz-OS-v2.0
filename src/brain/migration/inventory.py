"""What the system being replaced holds, what happens to each of it, and who could see it.

The first week of a migration is spent finding out what the old system contains, and the
finding-out is the part that gets skipped, because the parts anybody can name are the parts
somebody already remembered. This module is the register for that survey and for the two
decisions that follow it: one disposition per item, and one explicit mapping from every old
permission onto the capability model here.

**A catalogue is a claim about what was looked at, not a list of what was found.** That is
the whole design. A survey that returns no conversations and a survey where nobody opened
the conversation history produce the same empty list, and they mean opposite things: the
first is a system with no history, the second is a system whose history is about to be
deleted by a decommission nobody argued about. `Catalogue` therefore carries the kinds that
were surveyed separately from the items, an item of an unsurveyed kind is refused as
incoherent, and `unsurveyed` is the finding. See
`AN_EMPTY_SURVEY_AND_AN_UNOPENED_ONE_LOOK_THE_SAME_IN_A_LIST`.

**Only knowledge can be carried across as it stands.** A prompt and a tool definition are
written against the permission model of the system they came from, and that system had no
ceiling and no leash to carry over: a prompt that worked there worked because nothing
narrowed it. So `MIGRATE` is refused for a prompt or a tool, which leaves rebuild or retire,
and the refusal is at the decision rather than at the import, because by import time somebody
has already promised the client their prompts move. Conversation history is refused for a
different reason and points at `brain.migration.carry`: history is archived, and importing a
conversation is a decision about the archive rather than about the item. See
`A_PROMPT_FROM_A_SYSTEM_WITH_NO_LEASH_IS_NOT_A_PROMPT_HERE`.

**A permission mapping that explains itself by restating its own name has explained nothing.**
`admin becomes admin` is the mapping a hurried afternoon produces, and it reads as a decision
in a document that later gets signed. A reason equal to the old permission's name, or to the
name of a capability it maps onto, is refused here for exactly the reason `CLAUDE.md` records
about tests satisfied by their own docstrings: a restatement passes every check that looks
for the presence of words. See `A_MAPPING_THAT_RESTATES_ITS_OWN_NAME_IS_AN_ASSUMPTION`.

A mapping onto no capabilities at all is allowed and is often the right answer, because an
old system's permissions include ones this model has no equivalent for. It still needs its
reason, and the reason is then the record of what somebody loses on cutover day.

Capabilities are `brain.core.entitlement.Capability` rather than strings, so a mapping onto a
name the model does not define cannot be written down at all. That is the one part of this
that needs no test, and it is the part most worth having.

What was rejected. A `dict[str, Disposition]` instead of a sequence of `Decision` objects was
the obvious shape and loses the reason, which is the only part of a disposition worth keeping
six months later; it also makes two people deciding the same item differently unrepresentable,
so the conflict is resolved silently by whoever wrote last. `contradicted` exists because that
conflict is the normal state of a migration in week two.

Nothing here reads a database. The catalogue arrives from an exporter plugin and the
decisions arrive from a console screen, and the interesting case in both is the one with a
gap in it, which a module holding a session could not be made to produce in a test.

Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from brain.core.entitlement import Capability


class MigrationError(Exception):
    """Raised when a migration register would record a decision nobody made."""


# ------------------------------------------------------------------ written-down reasons
#: Why the kinds surveyed are carried separately from the items found.
AN_EMPTY_SURVEY_AND_AN_UNOPENED_ONE_LOOK_THE_SAME_IN_A_LIST: Final = (
    "A survey that found no conversations and a survey where nobody opened the conversation "
    "history are the same empty list, and they mean opposite things. The first describes a "
    "system with no history. The second describes history that a decommission is about to "
    "delete, decided by nobody, discovered by the client. The kinds that were looked at are "
    "therefore recorded separately from what was found, an item of a kind nobody surveyed is "
    "refused as incoherent, and the kinds nobody looked at are the finding."
)

#: Why a prompt or a tool definition may not be carried across as it stands.
A_PROMPT_FROM_A_SYSTEM_WITH_NO_LEASH_IS_NOT_A_PROMPT_HERE: Final = (
    "A prompt and a tool definition are written against the permission model of the system "
    "they came from, and that system narrowed nothing: the prompt worked there because it "
    "could reach everything the account could. Carried across unchanged it is a prompt "
    "written for a ceiling that does not exist, and the first thing anybody notices is a "
    "refusal it has no wording for. Rebuild or retire are the two honest answers, and the "
    "refusal sits at the decision rather than at the import, because by import time the "
    "client has been told their prompts move."
)

#: Why a mapping may not be explained by its own name.
A_MAPPING_THAT_RESTATES_ITS_OWN_NAME_IS_AN_ASSUMPTION: Final = (
    "'admin becomes admin' is what a hurried afternoon writes, and it reads in a signed "
    "document as a decision somebody took. A reason equal to the old permission's name, or "
    "to the name of a capability it maps onto, is a restatement: it passes every check that "
    "looks for words being present, which is the failure this repository has already found "
    "twice in tests satisfied by their own docstrings. The mapping from an old permission "
    "onto this model is the one step of a migration that cannot be inferred, so the reason "
    "has to say something the names do not."
)

#: Why an incomplete register raises with everything at once.
A_MIGRATION_AGREED_IN_PIECES_IS_AGREED_BY_NOBODY: Final = (
    "Findings are returned together because a register handed back one finding at a time is "
    "worked through one finding at a time, and the person doing that stops when the screen "
    "goes green rather than when the survey is complete. agreed raises with every finding it "
    "has; catalogue_gaps is the same answer without the exception, for a screen that shows "
    "what is outstanding while the work is still going on."
)


# ------------------------------------------------------- what the old system holds (M37.1.1.1)
class Holding(enum.StrEnum):
    """The four kinds of thing a predecessor system holds.

    Read against the M37.1.1.1 leaf sentence rather than against a list here, in the same way
    `brain.launch.Responsibility` is read against its own leaf, so the vocabulary and the leaf
    cannot drift apart without a test going red.
    """

    KNOWLEDGE = "knowledge"
    PROMPT = "prompt"
    TOOL = "tool"
    CONVERSATION = "conversation"


class Disposition(enum.StrEnum):
    """What happens to one catalogued item.

    Three, and the three are the M37.1.1.2 leaf sentence. A fourth would be a decision this
    register cannot record, which is how items end up moved by default.
    """

    MIGRATE = "migrate"
    REBUILD = "rebuild"
    RETIRE = "retire"


#: The kinds that may be carried across unchanged.
#:
#: One. See `A_PROMPT_FROM_A_SYSTEM_WITH_NO_LEASH_IS_NOT_A_PROMPT_HERE` for prompts and tools,
#: and `brain.migration.carry` for why conversation history is archived rather than imported.
CAN_BE_CARRIED_ACROSS: Final = frozenset({Holding.KNOWLEDGE})


@dataclass(frozen=True)
class Item:
    """One thing the system being replaced holds.

    `permissions` are the old system's permission names as they appear on the item, kept as
    strings deliberately: they are somebody else's vocabulary and coercing them into this
    model's `Capability` at read time is the assumption M37.1.1.3 exists to prevent.
    """

    item_id: str
    holding: Holding
    name: str
    permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            msg = f"a {self.holding.value} was catalogued with no id, so nothing can decide it"
            raise MigrationError(msg)
        if not self.name.strip():
            msg = f"{self.item_id!r} was catalogued with no name, so nobody can recognise it"
            raise MigrationError(msg)
        if any(not one.strip() for one in self.permissions):
            msg = f"{self.item_id!r} carries a blank permission name"
            raise MigrationError(msg)


@dataclass(frozen=True)
class Catalogue:
    """What was looked at, and what was found in it.

    Two fields rather than one list, for the reason in
    `AN_EMPTY_SURVEY_AND_AN_UNOPENED_ONE_LOOK_THE_SAME_IN_A_LIST`.
    """

    surveyed: frozenset[Holding]
    items: tuple[Item, ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for one in self.items:
            if one.holding not in self.surveyed:
                msg = (
                    f"{one.item_id!r} is a {one.holding.value} and the survey did not cover "
                    f"{one.holding.value}, so it was found by a search nobody recorded"
                )
                raise MigrationError(msg)
            if one.item_id in seen:
                msg = f"{one.item_id!r} appears twice in the catalogue"
                raise MigrationError(msg)
            seen.add(one.item_id)

    def unsurveyed(self) -> tuple[Holding, ...]:
        """The kinds nobody looked at, in declaration order."""
        return tuple(one for one in Holding if one not in self.surveyed)

    def permissions(self) -> tuple[str, ...]:
        """Every distinct old permission name appearing anywhere in the catalogue, sorted."""
        return tuple(sorted({name for one in self.items for name in one.permissions}))


# ------------------------------------------------- migrate, rebuild or retire (M37.1.1.2)
@dataclass(frozen=True)
class Decision:
    """One disposition against one item, with the reason it was taken.

    The reason is required. A register of dispositions without them is a register that
    answers "what did we decide" and not "why", and the second question is the one asked
    after cutover, by somebody looking for a document that no longer exists.
    """

    item_id: str
    disposition: Disposition
    because: str

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            msg = f"a {self.disposition.value} decision names no item"
            raise MigrationError(msg)
        if not self.because.strip():
            msg = (
                f"{self.item_id!r} is set to {self.disposition.value} with no reason, which "
                "is what a form full of defaults produces"
            )
            raise MigrationError(msg)


def undecided(catalogue: Catalogue, decisions: Sequence[Decision]) -> tuple[str, ...]:
    """Catalogued items nothing has decided, in catalogue order (M37.1.1.2)."""
    decided = {one.item_id for one in decisions}
    return tuple(one.item_id for one in catalogue.items if one.item_id not in decided)


def contradicted(decisions: Sequence[Decision]) -> tuple[str, ...]:
    """Items two people decided differently, sorted, as findings naming both dispositions.

    Two decisions agreeing is not a finding: the same disposition recorded twice is a screen
    submitted twice, and refusing it would make the register harder to use than the spreadsheet
    it replaces.
    """
    taken: dict[str, set[Disposition]] = {}
    for one in decisions:
        taken.setdefault(one.item_id, set()).add(one.disposition)
    return tuple(
        f"{item_id}: decided {' and '.join(sorted(one.value for one in dispositions))}"
        for item_id, dispositions in sorted(taken.items())
        if len(dispositions) > 1
    )


def cannot_be_carried(catalogue: Catalogue, decisions: Sequence[Decision]) -> tuple[str, ...]:
    """Items set to migrate that may not be, in catalogue order.

    See `A_PROMPT_FROM_A_SYSTEM_WITH_NO_LEASH_IS_NOT_A_PROMPT_HERE`. Conversations are named
    separately because the answer for them is a different one: archive them, and record the
    reason on the archive if any are to be imported.
    """
    carried = {one.item_id for one in decisions if one.disposition is Disposition.MIGRATE}
    findings: list[str] = []
    for one in catalogue.items:
        if one.item_id not in carried or one.holding in CAN_BE_CARRIED_ACROSS:
            continue
        if one.holding is Holding.CONVERSATION:
            findings.append(
                f"{one.item_id}: history is archived rather than imported, and an import is "
                "recorded against the archive by brain.migration.carry"
            )
            continue
        findings.append(
            f"{one.item_id}: a {one.holding.value} is rebuilt or retired, never carried "
            "across, because it was written for a system that narrowed nothing"
        )
    return tuple(findings)


# ----------------------------------------------- old permissions, explicitly (M37.1.1.3)
@dataclass(frozen=True)
class PermissionMapping:
    """One old permission name and what it becomes here, with the argument for it.

    An empty `capabilities` is a real answer and not a gap: an old system's permissions
    include ones this model has no equivalent for, and saying so is the record of what
    somebody loses on cutover day. It still needs its reason.
    """

    old: str
    capabilities: tuple[Capability, ...]
    because: str

    def __post_init__(self) -> None:
        if not self.old.strip():
            msg = "a permission mapping names no old permission"
            raise MigrationError(msg)
        if not self.because.strip():
            msg = f"{self.old!r} is mapped with no reason, which is a mapping by assumption"
            raise MigrationError(msg)
        restated = {self.old.strip().casefold()}
        restated.update(one.value.strip().casefold() for one in self.capabilities)
        if self.because.strip().casefold() in restated:
            msg = (
                f"{self.old!r} is explained by restating a name. "
                f"{A_MAPPING_THAT_RESTATES_ITS_OWN_NAME_IS_AN_ASSUMPTION}"
            )
            raise MigrationError(msg)


def unmapped(catalogue: Catalogue, mappings: Sequence[PermissionMapping]) -> tuple[str, ...]:
    """Old permissions the catalogue carries that nothing maps, sorted (M37.1.1.3).

    The direction matters. Mapping every permission somebody remembered leaves the ones only
    the export knows about, and those are the permissions that get mapped by assumption at
    cutover, by whoever is holding the keyboard at the time.
    """
    mapped = {one.old.strip().casefold() for one in mappings}
    return tuple(one for one in catalogue.permissions() if one.strip().casefold() not in mapped)


def mapped_twice(mappings: Sequence[PermissionMapping]) -> tuple[str, ...]:
    """Old permissions with more than one mapping, sorted.

    Unlike two identical dispositions, two mappings are always a finding even when they agree:
    a duplicate mapping is two people having the conversation separately, and the next edit
    changes one of them.
    """
    counted: dict[str, int] = {}
    for one in mappings:
        key = one.old.strip().casefold()
        counted[key] = counted.get(key, 0) + 1
    return tuple(
        f"{old}: mapped {count} times, so the next edit changes one of them"
        for old, count in sorted(counted.items())
        if count > 1
    )


# ------------------------------------------------------------- the register, or its gaps
@dataclass(frozen=True)
class Agreed:
    """A catalogue whose every item is decided and whose every permission is mapped.

    Obtainable only from `agree`, in the same way `brain.launch.ServiceLevel` is obtainable
    only from `service_level`: every state that would let somebody read a half-finished
    migration as a finished one is refused there rather than left to a renderer.
    """

    catalogue: Catalogue
    decisions: tuple[Decision, ...]
    mappings: tuple[PermissionMapping, ...]

    def disposition_of(self, item_id: str) -> Disposition:
        """What happens to one item. Raises for an id the catalogue does not hold."""
        for one in self.decisions:
            if one.item_id == item_id:
                return one.disposition
        msg = f"{item_id!r} is not in the catalogue"
        raise MigrationError(msg)

    def capabilities_for(self, old: str) -> tuple[Capability, ...]:
        """What one old permission becomes. Raises for a permission the catalogue lacks."""
        for one in self.mappings:
            if one.old.strip().casefold() == old.strip().casefold():
                return one.capabilities
        msg = f"{old!r} is not a permission the catalogue carries"
        raise MigrationError(msg)


def catalogue_gaps(
    catalogue: Catalogue,
    decisions: Sequence[Decision],
    mappings: Sequence[PermissionMapping],
) -> tuple[str, ...]:
    """Everything outstanding in a migration register, worst first.

    Ordered by what a cutover loses. An unsurveyed kind first, because it is the only finding
    that says the register is measuring the wrong thing; then items nothing decided; then
    contradictions; then what cannot be carried; then the permission mapping.
    """
    findings: list[str] = [
        f"{one.value}: nobody looked, so an empty list here means nothing"
        for one in catalogue.unsurveyed()
    ]
    findings.extend(
        f"{item_id}: catalogued and nothing decided, so a cutover decides it by omission"
        for item_id in undecided(catalogue, decisions)
    )
    findings.extend(contradicted(decisions))
    findings.extend(cannot_be_carried(catalogue, decisions))
    findings.extend(
        f"{one}: reaches something in the catalogue and maps onto nothing here"
        for one in unmapped(catalogue, mappings)
    )
    findings.extend(mapped_twice(mappings))
    return tuple(findings)


def agree(
    catalogue: Catalogue,
    decisions: Sequence[Decision],
    mappings: Sequence[PermissionMapping],
) -> Agreed:
    """The register, or a refusal naming everything outstanding at once.

    See `A_MIGRATION_AGREED_IN_PIECES_IS_AGREED_BY_NOBODY`.
    """
    findings = catalogue_gaps(catalogue, decisions, mappings)
    if findings:
        msg = f"the migration register is not agreed: {'; '.join(findings)}"
        raise MigrationError(msg)
    return Agreed(catalogue=catalogue, decisions=tuple(decisions), mappings=tuple(mappings))
