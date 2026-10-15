"""The one door a change the agent learned goes through, so it is marked, listable and reversible.

M16.7.1 asks that every change learning applies to an agent be marked machine-authored in that
agent's per-field ownership, so that a person can list and revert exactly what the agent taught
itself, apart from what an administrator set. `brain.agents.template` already says who set each
path (`FieldOwner`), and it said it with two answers, the template's and this instance's; this adds
the third, `FieldSource.LEARNED`, and the rules for writing it.

**There is exactly one function that writes a learned value, and it is this module's.**
`learn_field` is the only caller that names `FieldSource.LEARNED`, and
`tests/unit/test_agent_learned.py` holds the source to that, so a learning that wrote an agent
through `set_field` with the default would be a value a person set as far as anybody could tell,
and nothing could list it. What the owner of a path is, is decided here and nowhere else.

**A learned change never replaces a value somebody here set.** The path must be the template's, or
an earlier learned value of the agent's own, and a path an administrator set is refused. The reason
is the revert: giving a learned path back returns it to the template (`clear_field`), which is what
nobody here had changed, so if learning could overwrite an administrator's value, reverting it would
destroy a decision a person made, and keeping the value beneath would be a second record of
configuration. Refusing is the cheaper design and it keeps "list exactly what the agent taught
itself, apart from what an administrator set" true by construction. See
`A_LEARNED_CHANGE_NEVER_REPLACES_WHAT_A_PERSON_SET`.

**Only the paths whose changes reach the ledger are learnable, which today is the instructions.**
`0059`'s trigger on the install appends an `instructions` entry for every change to the persona and
every give-back, naming who put it in force, and no other path of the manifest has one. A learning
that changed a skill pin or a golden question would change what an agent is without the record that
says who agreed, which is the failure this repository keeps finding in new form. So
`LEARNABLE_PATHS` is the instructions and nothing else, a path is added to it in the commit that
gives that path a ledger entry, and the test holds the tuple inside the settable paths and outside
every path that decides reach (`brain.builder.publish.REACH_PATHS`) and every sealed one. Learning
writes words and never reach, for the reason
`brain.builder.coauthor.THE_COAUTHOR_WRITES_WORDS_AND_NEVER_REACH` gives about a model: what it
learned from is text nobody reviewed.

**`set_by` is the person who approved, and the mark says a machine wrote it.** A learned change is
applied after a named person agrees (`brain.memory.tiers` puts everything that changes an answer
without changing who may see what at tier one, and what the agent says in its instructions above
that), so the owner of a learned path is `FieldOwner(source=LEARNED, set_by=<approver>)`: the
person to ask about it, with the source saying whose words they are. The upgrade review already
draws `owner.source` beside `set_by`, and keeping a learned value through an upgrade keeps this
owner (`brain.agents.upgrade.ACCEPTING_AN_UPGRADE_IS_NOT_SETTING_THE_VALUES_IT_KEEPS`), so it stays
listable across versions.

**Rejected: a separate table of learned changes.** It would be a second place saying what an agent
is, and the day the two disagreed the wrong one would be in force. The overlay is the record of what
this instance holds that its template does not, the owner map is the record of whose it is, and the
list below is read off the two.

Task ids: M16.7.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from brain.agents.template import (
    FieldSource,
    TemplateError,
    TemplateInstance,
    clear_field,
    set_field,
)

#: Why a learned change does not overwrite a person's.
A_LEARNED_CHANGE_NEVER_REPLACES_WHAT_A_PERSON_SET: Final = (
    "Giving a learned change back returns the path to its template. If learning could write over "
    "a value somebody here had set, giving it back would destroy that person's decision, and "
    "keeping the old value underneath would be a second record of the agent's configuration. So "
    "a path somebody set is refused, and what the agent teaches itself is only ever what nobody "
    "here had changed."
)

#: Why only some paths can be learned.
A_PATH_IS_LEARNABLE_ONLY_WHEN_ITS_CHANGES_REACH_THE_LEDGER: Final = (
    "A learned value is a machine's words put into what an agent is. The ledger records who "
    "approved it only for the paths that have an entry of their own, and today that is the "
    "instructions. A path with none could be changed by learning with nobody's name against it, so "
    "it is not learnable until it has one."
)

#: The manifest paths learning may change: the instructions the agent is given.
LEARNABLE_PATHS: Final[tuple[str, ...]] = ("persona",)


class NotLearnableError(TemplateError):
    """A learned change that may not be made, with the sentence saying why."""


class LearnedChange(BaseModel):
    """One thing the agent taught itself: where, what, who approved it and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    value: JsonValue
    #: The person who approved the change. Never a machine's name.
    approved_by: str
    approved_at: datetime


def learn_field(
    instance: TemplateInstance,
    path: str,
    value: JsonValue,
    *,
    approved_by: str,
    at: datetime,
) -> TemplateInstance:
    """Put a learned value on one learnable path, owned as the agent's own learning, or refuse.

    The instance with the path overlaid and its owner a learned one whose `set_by` is the person
    who approved it. Refused, in words, for a path that is not learnable and for a path somebody
    here set. A path the agent's own learning wrote earlier is replaced, and the owner is the new
    approval. See `A_LEARNED_CHANGE_NEVER_REPLACES_WHAT_A_PERSON_SET`.
    """
    if path not in LEARNABLE_PATHS:
        msg = (
            f"{path!r} is not something learning may change. "
            f"{A_PATH_IS_LEARNABLE_ONLY_WHEN_ITS_CHANGES_REACH_THE_LEDGER}"
        )
        raise NotLearnableError(msg)
    # An overlaid path always has an owner (`TemplateInstance` refuses one without), so the owner is
    # read directly: a guard for a missing one would be a branch no instance can reach.
    if path in instance.overlay and instance.overlay_owners[path].source is not FieldSource.LEARNED:
        msg = (
            f"{path!r} was set by a person on this agent, so learning leaves it alone. "
            f"{A_LEARNED_CHANGE_NEVER_REPLACES_WHAT_A_PERSON_SET}"
        )
        raise NotLearnableError(msg)
    return set_field(instance, path, value, by=approved_by, at=at, source=FieldSource.LEARNED)


def learned_changes(instance: TemplateInstance) -> tuple[LearnedChange, ...]:
    """Exactly what the agent taught itself, in path order, and nothing an administrator set.

    Read off the overlay and its owners together: a path counts only when it is overlaid and its
    owner is a learned one, so a forged owner row for a path that is not overlaid lists nothing, and
    a path somebody set is never here whatever else is true.
    """
    return tuple(
        LearnedChange(
            path=path,
            value=instance.overlay[path],
            approved_by=owner.set_by,
            approved_at=owner.set_at,
        )
        for path, owner in sorted(instance.overlay_owners.items())
        if owner.source is FieldSource.LEARNED and path in instance.overlay
    )


def give_back_learned(instance: TemplateInstance, path: str) -> TemplateInstance:
    """Return one learned path to its template, refusing a path the agent did not teach itself.

    The other half of the door: a person who wants to undo what the agent taught itself can undo
    that and nothing else through here, so giving back a learned change cannot take away an
    administrator's value. `brain.prompt_routes` has its own give-back for any instructions
    override, for the Prompts screen; this is the one that is about learning.
    """
    owner = instance.overlay_owners.get(path)
    if path not in instance.overlay or owner is None or owner.source is not FieldSource.LEARNED:
        msg = f"{path!r} is not something this agent taught itself, so it is not given back here"
        raise NotLearnableError(msg)
    return clear_field(instance, path)
