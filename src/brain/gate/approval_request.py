"""An approver's view of a held action: rendered at their own reach, locked where they cannot read.

Needs-rupash item 14 was closed on 2026-09-06 by a card builder that took no suspension, only a body
and the approver's entitlements, and refused a body computed at any other reach. Three weeks later
both approval surfaces showed the approver `SuspendedAction.artefact`: the Approvals screen's
`brain.console.approvals.Card` carried it on the argument that a re-rendered artefact is an approval
of something nobody read, and the Lark card put that same string into its payload. The artefact is
`brain.gate.leash.render_artefact` of the requester's action, every argument's value included, so an
approver holding the action's capability but not a field's read capability was shown the field.

**The guards were bypassed, not removed, and each bypass is now a named rule.** The structural test
pinned the card's dataclass fields, and the artefact arrived inside `payload`, a free-form record
the pin allowed (`NO_CARD_CARRIES_A_FREE_FORM_RECORD_OF_REQUEST_CONTENT`). The reach check compared
a hash the caller supplied, and the caller supplied the approver's own hash for a body never
computed at that reach (`NO_REACH_CHECK_COMPARES_A_VALUE_THE_CALLER_ASSERTS`).

**So the request is a value only this module makes.** `render_request` takes the action, the
reader's entitlements and the field policy of the action's entity, and computes the mask the same
way the leash's own mask check does (`brain.core.redaction.compute_mask`, over the action's row for
the scope). An argument the reader may read shows its value; every other one shows
`brain.core.redaction.LOCK_TEXT`, the one lock every viewer sees, with no count and no reason
(M4.3.1). The result carries whom it was rendered for and the reach hash it was rendered at, both
taken from the reader at that moment, and `RenderedRequest` refuses construction anywhere else, so
a hash cannot be written onto one by a caller. `SuspendedAction.artefact` stays where it is, as the
record of what the requester was shown, and no approver surface reads it.

Rejected: keeping the artefact and redacting its text. It is a rendered string, so redacting it
means parsing the requester's rendering back into fields, which is a second renderer that agrees
with the first only until one of them changes. Rendering from the action is one renderer.

Task ids: M33.8.1, M10.2.3, M4.3.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import LOCK_TEXT, compute_mask
from brain.gate.leash import Action

#: Why an approver's view of an action is rendered at their reach and never copied.
A_REQUEST_IS_RENDERED_AT_ITS_READER_S_REACH: Final = (
    "The approver is chosen for their authority over an action, not for their reach over the data "
    "it carries. So what they are shown is rendered from the action at their own reach, an "
    "argument they could not look up is shown locked, and the requester's rendering, which holds "
    "every value the requester could see, never reaches them."
)

#: The first bypass, named. Held by tests on every surface an approval is drawn on.
NO_CARD_CARRIES_A_FREE_FORM_RECORD_OF_REQUEST_CONTENT: Final = (
    "A card's fields and its payload's keys are each a closed list a test holds, and the request "
    "travels only as a RenderedRequest. A field or a key that could hold an arbitrary string of "
    "request content is how the requester's artefact came back inside a card whose own fields "
    "were pinned."
)

#: The second bypass, named.
NO_REACH_CHECK_COMPARES_A_VALUE_THE_CALLER_ASSERTS: Final = (
    "A check that compares a hash the caller hands it is satisfied by the caller saying the right "
    "thing. The reach a request was rendered at is computed by render_request from the reader it "
    "rendered for, at that moment, and a RenderedRequest cannot be built with a hash of anybody's "
    "choosing, so the card builder compares two values neither of which a caller wrote."
)

#: Why the product's own actions show their arguments to whoever may decide them.
AN_ACTION_S_OWN_TERMS_ARE_NOT_DATA: Final = (
    "A promotion's statement of what will be published, and a browsing run's id, writes and "
    "envelope digest, are written by the product as the terms of the decision for whoever may "
    "decide it, and no source classifies them. A field rule may only require a read capability, "
    "and an approver of these holds the action's own capability, so classifying them would lock "
    "every term from everybody who may decide. So for a closed set of the product's own tools, "
    "which a test holds, the product's statement is shown whole; every other action is rendered "
    "from its arguments under its entity's classification."
)


class RequestRefusedError(ValueError):
    """A request that would show its reader nothing, which an approval must never be."""


#: Only `render_request` holds this, and `RenderedRequest` refuses construction without it.
_MINTED: Final = object()


@dataclass(frozen=True)
class RenderedRequest:
    """A held action as one reader may see it. Made by `render_request` and nothing else.

    `text` is what they are shown. `rendered_for` and `ent_hash` are the reader it was rendered for
    and their reach at that moment, as `EntitlementSet.ent_hash` renders it; a card is built only
    for a reader whose principal and reach are those. See
    `NO_REACH_CHECK_COMPARES_A_VALUE_THE_CALLER_ASSERTS`.
    """

    text: str
    rendered_for: str
    ent_hash: str
    minted: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.minted is not _MINTED:
            msg = (
                "a request shown to an approver is rendered at their reach by render_request, "
                "and is never written by hand. "
                f"{NO_REACH_CHECK_COMPARES_A_VALUE_THE_CALLER_ASSERTS}"
            )
            raise ValueError(msg)
        if not self.text.strip():
            msg = (
                "this request would show its reader nothing, and an approver pressing approve on "
                "an empty card has approved whatever it was"
            )
            raise RequestRefusedError(msg)


def render_request(
    action: Action, reader: EntitlementSet, policy: FieldPolicy, now: datetime
) -> RenderedRequest:
    """The action as `reader` may see it, under `policy`, at `now`.

    The first three lines are `render_artefact`'s: the tool and its target, the agent and the
    effect, none of which is a value from anybody's data. Each argument follows in name order with
    its value where the reader may read that field of the action's entity on its row, and
    `LOCK_TEXT` where they may not. See `A_REQUEST_IS_RENDERED_AT_ITS_READER_S_REACH`.
    """
    shown = compute_mask(
        action.tool.entity,
        tuple(action.args),
        entitlement=reader,
        policy=policy,
        row=action.row,
        now=now,
    ).allowed
    lines = [
        f"{action.tool.name} on {action.target}",
        f"agent: {action.agent_id}",
        f"effect: {action.tool.side_effect.value}",
    ]
    lines.extend(
        f"  {key}: {action.args[key] if key in shown else LOCK_TEXT}" for key in sorted(action.args)
    )
    return RenderedRequest(
        text="\n".join(lines),
        rendered_for=reader.principal_id,
        ent_hash=reader.ent_hash(),
        minted=_MINTED,
    )


def render_terms(statement: str, reader: EntitlementSet) -> RenderedRequest:
    """The product's own statement of a decision's terms, for `reader`.

    Only for an action of the closed set `brain.console.approvals.terms_not_data` holds, which
    `brain.console.approvals.request_for` is the one caller to decide. See
    `AN_ACTION_S_OWN_TERMS_ARE_NOT_DATA`.
    """
    return RenderedRequest(
        text=statement,
        rendered_for=reader.principal_id,
        ent_hash=reader.ent_hash(),
        minted=_MINTED,
    )
