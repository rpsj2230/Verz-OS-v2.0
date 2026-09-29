"""What a tool is allowed to be, decided at registration rather than per request.

`brain.gate.catalogue` already computes what a caller may see. This module is what it
computes over, and the split is the point: projection is a per-request question about a
person, while every rule here is a question about the tool itself, asked once, in front of
whoever wrote it. A tool is also the only grantable thing in the platform. A skill is a
procedure an agent loads and a connector is a deployment unit; a capability is asked for by
a tool and by nothing else, so this is where a mistake about reach is still cheap.

**What breaks without it.** Every refusal below moves to request time, where it is an
answer going wrong rather than a build going red.

*A malformed name reaches the model as an option.* The model picks from what it is shown,
so a name that does not read as `source.verb_noun` is either never selected or selected for
the wrong reason, and neither failure raises anything anybody sees.

*A tool that cannot be redacted raises inside a request that has already fetched rows.*
`brain.core.redaction.require_typed_result` makes exactly that refusal at the boundary, and
it is the right refusal one request too late: the connector has run, a person is waiting,
and the outcome is an exception instead of a fix.

*A malformed required capability fails closed in `catalogue._admits` and tells nobody.* The
tool then disappears from every catalogue for every caller, which looks exactly like a
permission problem, while the typo that caused it sits in a file nobody is reading. Failing
closed is right at request time and useless as a way of finding out.

*A SERVICE identity-mode tool with no scope predicate reaches everything its shared
credential reaches.* The source will not narrow it for us. That is the whole difference
between DELEGATED, where the source enforces its own permissions as well, and SERVICE,
where ours are the only ones there are.

*Two tools sharing a name resolve by import order*, and which one runs is decided by
whichever module happened to be imported second.

**A tool switched off is refused at the door every call already walks through (M12.4.3).**
Every caller in this tree reaches a handler by `get(name).handler`: the records route, the
answer lane's row readers and passage search, and a workflow's piece call. So the handler a
registration stores is a guard, and the guard asks the switch source at the moment of the call.
Not at `get`: `brain.app` builds the passage search once at startup and holds its handler for
the life of the process, so a check made at lookup would have been made once, before anybody
could switch anything. The guard is installed at registration, so no path to a handler skips
it, and the source is attached afterwards by `govern`, so the order `brain.app` wires things in
cannot open a gap. See `THE_SWITCH_IS_ASKED_AT_THE_CALL_AND_NOT_AT_THE_LOOKUP`.

**A switch only ever narrows.** There is a stop and there is no start: the switch table holds
the tools somebody switched off, for the install or for one department's people, and switching
a tool back on retires its stop. Nothing a department's administrator writes can reopen what
the install closed, because no row says a tool is on. It is not an entitlement and takes no
part in `EntitlementSet`: reach is decided before the call and a switch then refuses calls
inside it, which is `brain.ops.halt`'s position for the same reason. See
`A_SWITCH_ONLY_EVER_NARROWS`.

**The person asking is never told which switch.** The refusal is `Denied`, whose sentence is
the one every refusal carries; the switch, who threw it and when are in the detail, which goes
to the log an administrator reads and never into a response. See
`THE_ASKER_IS_NEVER_TOLD_WHICH_SWITCH`.

**A tool whose name says it does something the owner named as sensitive must declare it
(M12.3.8).** M3.8.5 gave a definition a way to say a person approves every call, and nothing
asked any tool to use it. What a declaration buys is `brain.gate.leash.effective_tier`'s cap:
such a call is prepared, suspended and run only after a person approves that exact action,
whatever rung its leash entry or a promotion gives it. See
`A_TOOL_WHOSE_NAME_SAYS_IT_ACTS_SENSITIVELY_MUST_DECLARE_IT`.

Scope: this is domain logic. Nothing here opens a connection, reads a table or calls a model.
The switches arrive through `SwitchSource`, which `brain.ops.tool_store` implements over
`agent.tool_switch`, and `agent.tool_definition` is that module's to write.

Task ids: M12.1.1, M12.1.2, M12.1.3, M12.1.4, M12.1.5, M12.3.8, M12.4.3
"""

from __future__ import annotations

import enum
import functools
import inspect
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol, Self, assert_never

import structlog

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import (
    OBJECT_NAME_PATTERN,
    TOOL_NAME_PATTERN,
    IdentityMode,
    SideEffect,
    ToolDefinition,
)
from brain.core.errors import Denied
from brain.core.redaction import OPAQUE_CAPABILITY, assert_tool_returns_typed_result
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import SENSITIVE_EFFECT_RUNG, Leash, LeashEntry

log = structlog.get_logger()

# --------------------------------------------------------------------- grammars

#: Both compiled from the patterns in `brain.core.envelope`, which is the one place either
#: shape is written down. They used to differ: this module was strict, the model and the
#: sweep were not, and a name all three should have agreed on was refused in exactly one of
#: them, at registration, which is the latest and least useful of the three places to find
#: out. Compiling rather than restating means the next person to loosen one loosens all
#: three, deliberately, in the file whose comment says why it is tight.
TOOL_NAME_RE: Final = re.compile(TOOL_NAME_PATTERN)

#: What a tool's object may be called.
OBJECT_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)

#: The one object name that may only be claimed by one tool, and the tool that claims it.
#:
#: The architecture is explicit that a skill's scripts run through a single tool carrying
#: the sandbox, the leash and output redaction. "Single" has to be enforced somewhere, and
#: a constant defined where it is not enforced is a constant somebody redefines. It lives
#: here rather than in `brain.tools.skills` because this module is the one that can refuse
#: a second claimant, and `skills` imports it back for the same reason.
SKILL_SCRIPT_OBJECT: Final = "skill_script"
RUN_SKILL_SCRIPT: Final = "skill.run_script"


class ResultContract(enum.StrEnum):
    """What shape a tool promises to return (M12.1.4).

    Two members and no third. `TYPED` is the ordinary case, walked field by field by
    `brain.core.redaction`. `OPAQUE` is the escape hatch for data that genuinely cannot be
    field-typed, and it is a declaration on the tool rather than a flag on a call so that
    "which tools bypass field-level redaction" is a list somebody can read.

    Declaring `OPAQUE` does **not** exempt a tool from returning a `TypedResult`. The
    opaque path in `redact` still calls `require_typed_result` before it dumps anything, so
    a tool that cannot be walked cannot be registered under either contract.
    """

    TYPED = "typed"
    OPAQUE = "opaque"


class ToolRegistrationError(Exception):
    """A tool was declared in a way that cannot be made safe.

    Outside the user-facing taxonomy in `brain.core.errors`, deliberately, and for the
    reason `brain.core.redaction.UntypedShapeError` gives: nobody asking a question should
    ever see this. It is a contract violation by whoever wrote the tool, and it should stop
    that tool existing rather than degrade somebody's answer at request time.

    One exception type for every refusal, as `ChannelPathError` is. The refusals differ in
    message and not in what the caller can do about them, and a taxonomy of registration
    errors would invite a caller to catch some of them.
    """


# ------------------------------------------------------------------ the refusals


def assert_tool_name(name: str) -> None:
    """Refuse anything that is not `source.verb_noun` (M12.1.1)."""
    if not TOOL_NAME_RE.match(name):
        msg = (
            f"tool name {name!r} is not source.verb_noun; the catalogue is projected per "
            "request and the model picks from what it is shown, so a malformed name is a "
            "tool that is either never selected or selected for the wrong reason"
        )
        raise ToolRegistrationError(msg)


def assert_object_name(definition: ToolDefinition) -> None:
    """Refuse an object name no field policy could ever match."""
    if not OBJECT_NAME_RE.match(definition.entity):
        msg = (
            f"tool {definition.name!r} declares object {definition.entity!r}, which is not a "
            "name; a field policy is looked up by entity, so every field of every record it "
            "returns would be withheld as unclassified and read as a permission failure"
        )
        raise ToolRegistrationError(msg)


def assert_source_agrees(definition: ToolDefinition) -> None:
    """The name's first segment is the source, so a declared source must be the same one.

    Checked only when `source` is set, because it defaults to empty and most tools carry
    the source in the name alone. Where both are present and they disagree, one of them is
    wrong about which system the call goes to, and the identity mode and the credential
    follow the source rather than the name.
    """
    if not definition.source:
        return
    declared = definition.name.split(".", 1)[0]
    if definition.source != declared:
        msg = (
            f"tool {definition.name!r} declares source {definition.source!r} but is named "
            f"for {declared!r}; the name is what a reader and a trace believe, and the "
            "credential follows the source"
        )
        raise ToolRegistrationError(msg)


def capability_for(definition: ToolDefinition) -> Capability:
    """The tool's requirement, parsed (M12.1.2).

    `ToolDefinition.required_capability` is a string, so this is the one place it becomes a
    `Capability`. An unparseable one is refused here rather than carried: `catalogue._admits`
    already treats it as unreachable, which is the correct request-time behaviour and a
    terrible way to find out, because the tool simply never appears for anybody.

    What must never happen is the other reading. Treating an unparseable requirement as "no
    requirement" turns a typo into an open door, and it is the natural shape of a defensive
    `try: ... except: pass` written by somebody who wanted registration to stop failing.
    """
    try:
        return Capability(value=definition.required_capability)
    except ValueError as exc:
        msg = (
            f"tool {definition.name!r} requires {definition.required_capability!r}, which is "
            "not a capability; an unparseable requirement must make a tool unreachable and "
            "never unrestricted, so it is refused here rather than skipped at request time"
        )
        raise ToolRegistrationError(msg) from exc


def assert_effect_matches_capability(definition: ToolDefinition, capability: Capability) -> None:
    """A tool that changes something may not ask only for permission to read it.

    Asymmetric on purpose. A read-only tool demanding `write:ticket.status` is merely
    over-strict: fewer people reach it than need to, and nothing is disclosed. A SEND tool
    demanding `read:invoice.status` is an escalation, because everybody who can read an
    invoice can then send one, and the catalogue will happily show it to them.

    Rejected: requiring the verb to match the effect exactly, so that WRITE implies `write:`
    and MONEY implies `approve:`. The architecture's own money example requires
    `approve:payment.release` while its send example requires `write:invoice.status`, so an
    exact mapping would refuse one of the two, and the pair is what the mapping was drawn
    from.
    """
    if definition.side_effect is not SideEffect.NONE and capability.verb == "read":
        msg = (
            f"tool {definition.name!r} has side effect {definition.side_effect.value!r} and "
            f"requires {capability.value!r}; a tool that changes something while asking only "
            "to read it makes everybody who can read the record able to change it"
        )
        raise ToolRegistrationError(msg)


def assert_service_tool_is_scoped(definition: ToolDefinition, scope: Scope | None) -> None:
    """A SERVICE identity-mode tool must carry a scope predicate that narrows something.

    `ToolDefinition` has nowhere to put a scope, so the registry carries it beside the
    definition. That is why this is a registration rule and not a validator on the model.

    An unrestricted scope is refused as firmly as a missing one. `Scope()` satisfies "it has
    a scope" and admits every row, so accepting it would leave the rule enforceable only by
    whoever remembers what it was for, and a shared credential reaching everything is exactly
    the failure the rule exists to name.
    """
    if definition.identity_mode is not IdentityMode.SERVICE:
        return
    if scope is None or scope.is_unrestricted():
        msg = (
            f"tool {definition.name!r} runs as SERVICE and carries "
            f"{'no scope' if scope is None else 'an unrestricted scope'}; a shared credential "
            "is not narrowed by the source, so a service tool with nothing to narrow it "
            "reaches everything that credential can reach"
        )
        raise ToolRegistrationError(msg)


def assert_result_contract(
    definition: ToolDefinition, capability: Capability, contract: ResultContract
) -> None:
    """An opaque tool must require the opaque capability, or it is shown and then refused.

    `redact(opaque=True)` raises `Denied` for a caller who does not hold
    `read:opaque_payload`. If an opaque tool required anything else, it would pass the
    catalogue's entitlement check, be described to the model, be selected, and fail after the
    fetch. `brain.gate.catalogue` exists to stop precisely that: an unreachable tool is
    absent, never described and refused, because the model explains the refusal and the
    explanation is the leak.

    The cost is real and accepted. `ToolDefinition` carries one requirement, so an opaque
    tool cannot also demand `read:client.name`; its reach is governed by a capability almost
    nobody holds instead of by the entity. That is the right trade only because the opaque
    path returns everything anyway, so an entity-level requirement in front of it would be
    decoration.
    """
    if contract is ResultContract.OPAQUE and capability != OPAQUE_CAPABILITY:
        msg = (
            f"tool {definition.name!r} declares an opaque result but requires "
            f"{capability.value!r}; the redactor demands {OPAQUE_CAPABILITY.value!r} for an "
            "opaque payload, so this tool would be shown to callers who cannot receive it "
            "and refused after the fetch"
        )
        raise ToolRegistrationError(msg)


def assert_object_not_reserved(definition: ToolDefinition) -> None:
    """Only `skill.run_script` may claim the skill-script object.

    A second tool that ran a skill's scripts would be a second path to execution, and the
    sandbox, the leash and the output redaction are properties of the path rather than of
    the script. The reservation is checked on the object rather than on the name because the
    object is what a policy, a leash target and a slug collision are all written about.
    """
    if definition.entity != SKILL_SCRIPT_OBJECT:
        return
    if definition.name != RUN_SKILL_SCRIPT:
        msg = (
            f"tool {definition.name!r} claims the {SKILL_SCRIPT_OBJECT!r} object, which is "
            f"reserved for {RUN_SKILL_SCRIPT!r}; a second way to run a skill's scripts is a "
            "second path that the sandbox and the leash do not sit on"
        )
        raise ToolRegistrationError(msg)


# ---------------------------------------------- the owner's sensitive effects (M12.3.8)


class SensitiveEffect(enum.StrEnum):
    """The seven effects the owner named as needing a person's approval every time.

    Closed, one member per effect he named, so "which tools can do this" is a question about a
    column rather than a reading of descriptions. A tool declares at most one: a tool that does
    two of these things is two tools, because an approver is shown one prepared action and
    approves one thing.
    """

    CLIENT_MESSAGE = "client_message"
    QUOTATION = "quotation"
    DNS_OR_HOSTING = "dns_or_hosting"
    FINANCIAL_RECORD = "financial_record"
    DELETION = "deletion"
    PUBLICATION = "publication"
    PRODUCTION_CHANGE = "production_change"


def sensitive_words(effect: SensitiveEffect) -> frozenset[str]:
    """The words in a tool's name that say it has this effect.

    A name is read as its words split on the dot and the underscore, source included, so
    `dns.update_record` and `wordpress.update_plugin` are both read. Exhaustive by `match`, so
    an eighth effect cannot be added without somebody writing down how a name says it.
    """
    match effect:
        case SensitiveEffect.CLIENT_MESSAGE:
            return frozenset({"send", "email", "reply", "forward", "notify", "sms", "whatsapp"})
        case SensitiveEffect.QUOTATION:
            return frozenset({"quotation", "quotations", "quote", "quotes"})
        case SensitiveEffect.DNS_OR_HOSTING:
            return frozenset(
                {
                    "dns",
                    "domain",
                    "domains",
                    "nameserver",
                    "nameservers",
                    "zone",
                    "hosting",
                    "cname",
                    "mx",
                    "ssl",
                    "certificate",
                }
            )
        case SensitiveEffect.FINANCIAL_RECORD:
            return frozenset(
                {
                    "invoice",
                    "invoices",
                    "payment",
                    "payments",
                    "pay",
                    "bill",
                    "bills",
                    "ledger",
                    "journal",
                    "expense",
                    "expenses",
                    "refund",
                    "payroll",
                    "credit",
                    "void",
                    "reconcile",
                }
            )
        case SensitiveEffect.DELETION:
            return frozenset(
                {"delete", "remove", "purge", "erase", "destroy", "drop", "wipe", "truncate"}
            )
        case SensitiveEffect.PUBLICATION:
            return frozenset({"publish", "unpublish", "post", "posts"})
        case SensitiveEffect.PRODUCTION_CHANGE:
            return frozenset(
                {
                    "deploy",
                    "release",
                    "restart",
                    "rollback",
                    "reboot",
                    "migrate",
                    "provision",
                    "production",
                    "prod",
                    "server",
                    "servers",
                    "plugin",
                    "plugins",
                    "theme",
                    "themes",
                }
            )
        case _:
            assert_never(effect)


#: The side effects nothing leaves the building through, so the vocabulary is not asked about
#: them: a read changes nothing, and a draft is the prepared action itself, whose sending or
#: saving is what a person approves.
NOTHING_LEAVES: Final[frozenset[SideEffect]] = frozenset({SideEffect.NONE, SideEffect.DRAFT})

#: Why a tool's name can refuse its registration.
A_TOOL_WHOSE_NAME_SAYS_IT_ACTS_SENSITIVELY_MUST_DECLARE_IT: Final = (
    "M3.8.5 gave a tool a way to declare that a person approves every call to it, and nothing "
    "asked any tool to use it: a tool called drive.delete_file registered as an ordinary write "
    "would run at whatever rung its leash held, Autonomous included. The name is the one thing "
    "every registration carries and every reviewer reads, so a tool that changes something and "
    "whose name says it sends a client a message, issues a quotation, changes DNS or hosting, "
    "changes a financial record, deletes, publishes or changes a production system is refused "
    "until it declares a sensitive effect. The vocabulary errs wide: a word it reads wrongly "
    "costs an author one flag, and a word it misses is an approval nobody asks for."
)


def sensitive_effects_named_by(name: str) -> frozenset[SensitiveEffect]:
    """The sensitive effects a tool's name reads as, from its words. Empty for most tools."""
    words = frozenset(re.split(r"[._]", name))
    return frozenset(effect for effect in SensitiveEffect if words & sensitive_words(effect))


def assert_sensitive_effect_declared(
    definition: ToolDefinition, named: SensitiveEffect | None
) -> None:
    """Every tool with one of the owner's sensitive effects declares it, and a declaration is kept.

    Three refusals and they close different doors. A named effect on a definition that does not
    declare a sensitive effect is an approval the gate never asks for, because
    `brain.gate.leash.effective_tier` reads the definition and not this registration. A
    definition flagged sensitive with no effect named leaves the approver and the Tools screen
    unable to say which of the owner's effects a call has. And a tool that changes something and
    whose name reads as one of them must declare it: see
    `A_TOOL_WHOSE_NAME_SAYS_IT_ACTS_SENSITIVELY_MUST_DECLARE_IT`.

    A send or money tool declares a sensitive effect by its kind, so it passes without a flag,
    and naming which effect it has is then optional rather than required: `invoice.send_reminder`
    is a client message by its name and sensitive by its kind, and asking it to say so twice
    would be a rule with no failure behind it.
    """
    if named is not None and definition.side_effect is SideEffect.NONE:
        msg = (
            f"tool {definition.name!r} names the sensitive effect {named.value!r} and has no side "
            "effect; a tool that only reads cannot do what the name says it does"
        )
        raise ToolRegistrationError(msg)
    if named is not None and not definition.declares_sensitive_effect():
        msg = (
            f"tool {definition.name!r} names the sensitive effect {named.value!r} and its "
            "definition does not declare one; the leash reads the definition, so the approval "
            "this promises would never be asked for"
        )
        raise ToolRegistrationError(msg)
    if definition.sensitive and named is None:
        msg = (
            f"tool {definition.name!r} is declared sensitive and names no effect; an approver and "
            "the Tools screen are told which of the owner's sensitive effects a call has"
        )
        raise ToolRegistrationError(msg)
    if definition.side_effect in NOTHING_LEAVES:
        return
    read = sensitive_effects_named_by(definition.name)
    if read and not definition.declares_sensitive_effect():
        msg = (
            f"tool {definition.name!r} is named as a tool with the sensitive effect "
            f"{sorted(one.value for one in read)} and declares none; a person approves every "
            "such call only when the definition says so"
        )
        raise ToolRegistrationError(msg)


# ------------------------------------------------------- side effect to leash (M12.1.3)


def default_rung(effect: SideEffect) -> AutonomyTier:
    """The rung a side effect suggests, for an admin writing a leash entry.

    Exhaustive by `match`, so a sixth side effect cannot reach production without somebody
    deciding how much supervision it needs. A dictionary with a `.get` default would accept
    it silently as whatever the default was, which is the argument
    `brain.gate.leash.route_for` makes about routes.

    The mapping is not injective and does not need to be. DRAFT, WRITE and SEND all land on
    ASSISTED: they differ in how far the mistake travels, which is what `max_side_effect` on
    an agent ceiling is for, and not in whether a person should see it first. MONEY is
    SHADOW because the architecture pins the money-touching templates to Shadow at manifest
    level regardless of promotion criteria.
    """
    match effect:
        case SideEffect.NONE:
            return AutonomyTier.AUTONOMOUS
        case SideEffect.DRAFT | SideEffect.WRITE | SideEffect.SEND:
            return AutonomyTier.ASSISTED
        case SideEffect.MONEY:
            return AutonomyTier.SHADOW
        case _:
            assert_never(effect)


def rung_ceiling(rung: AutonomyTier, effect: SideEffect) -> AutonomyTier:
    """The configured rung, tightened by what the side effect suggests. Never loosened.

    This is the only shape in which a default may be applied to a leash. `brain.gate.leash`
    has no default field at all, and says why: a default is read as a convenience, written
    once by whoever installed the agent, and inherited from then on by every target nobody
    considered. `min` cannot inherit anything. A tool classified NONE by mistake does not
    raise a SHADOW pin to AUTONOMOUS; it simply stops tightening.

    Mirrors `brain.gate.injection.autonomy_ceiling`, which composes the same way for the
    same reason. Two rules that must agree eventually disagree, and the one that disagrees
    in the permissive direction is the one nobody notices.
    """
    return min(rung, default_rung(effect))


def leash_ceiling(definition: ToolDefinition) -> AutonomyTier:
    """The highest rung a leash entry on this tool keeps once `ToolRegistry.tighten` reads it.

    `default_rung` of its side effect, and no higher than `brain.gate.leash.SENSITIVE_EFFECT_RUNG`
    for a tool declaring a sensitive effect, which is the cap `effective_tier` puts on such a
    call at the gate. Imported rather than restated, so the rung the Tools screen shows and the
    rung the gate applies are one number.
    """
    rung = default_rung(definition.side_effect)
    if definition.declares_sensitive_effect():
        return min(rung, SENSITIVE_EFFECT_RUNG)
    return rung


class EffectClass(enum.StrEnum):
    """The three words the Tools screen uses for what a tool does to the world.

    Three rather than `SideEffect`'s five, because a person reading the catalogue is asking
    whether a tool can change anything and whether a change can be taken back. IRREVERSIBLE is
    `ToolDefinition.declares_sensitive_effect`, the same reading the leash caps at Assisted, so
    the word on the screen and the rule at the gate are one reading of one declaration.
    """

    READ = "read"
    WRITE = "write"
    IRREVERSIBLE = "irreversible"


def effect_class(definition: ToolDefinition) -> EffectClass:
    """Read, write or irreversible, asked strictest first so a contradiction reads as the worse."""
    if definition.declares_sensitive_effect():
        return EffectClass.IRREVERSIBLE
    if definition.side_effect is SideEffect.NONE:
        return EffectClass.READ
    return EffectClass.WRITE


# ----------------------------------------------------------------- the switch (M12.4.3)


class SwitchScope(enum.StrEnum):
    """Where a stop applies: every call on the install, or the calls of one department's people."""

    INSTALL = "install"
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Switch:
    """One stop on one tool, as the switch table holds it."""

    switch_id: str
    tool: str
    #: None for the whole install; otherwise the department whose people's calls are refused.
    department: str | None
    switched_off_by: str
    switched_off_at: datetime

    @property
    def scope(self) -> SwitchScope:
        return SwitchScope.INSTALL if self.department is None else SwitchScope.DEPARTMENT

    def described(self) -> str:
        """The switch in the words an administrator's trace carries. Never a response body."""
        where = "the install" if self.department is None else f"department {self.department!r}"
        return (
            f"tool {self.tool!r} is switched off for {where} by {self.switched_off_by} at "
            f"{self.switched_off_at.isoformat()} (switch {self.switch_id})"
        )


class SwitchSource(Protocol):
    """Whatever says, at the moment of a call, whether a stop applies to it.

    Handed the caller's principal id, or None where the call carried no reach, and answering the
    widest stop that applies: the install's before a department's. A protocol for the reason
    `brain.knowledge.rows.RowSource` is one: the rule is here and the table is not.
    """

    async def stop_for(self, tool: str, principal_id: str | None) -> Switch | None: ...


#: Why a switch cannot widen anything, and why a table of stops is not a deny list.
A_SWITCH_ONLY_EVER_NARROWS: Final = (
    "Agent reach only narrows, and a switch is written so that it cannot do anything else. The "
    "table holds stops and nothing but stops: a tool switched off for the install, or stopped "
    "for one department's people. Switching a tool back on retires its stop, and there is no "
    "row that says a tool is on, so nothing a department administrator writes can reopen what "
    "the install closed. It takes no part in EntitlementSet, which stays additive with no deny "
    "list: reach is decided first and a switch then refuses calls inside it, as a halt does."
)

#: Why the check is made when the handler runs and not when it is looked up.
THE_SWITCH_IS_ASKED_AT_THE_CALL_AND_NOT_AT_THE_LOOKUP: Final = (
    "brain.app builds the answer lane's passage search once at startup and keeps its handler "
    "for the life of the process, and a workflow's caller looks a handler up once per step. A "
    "switch consulted at lookup would therefore be consulted once, before anybody could throw "
    "it, for exactly the calls a person is most likely to be making. So the guard is the "
    "handler, installed at registration, and it asks the source every time it runs."
)

#: Why the person asking is told nothing about the switch.
THE_ASKER_IS_NEVER_TOLD_WHICH_SWITCH: Final = (
    "The refusal a switched-off tool gives is Denied, and its sentence is the one every refusal "
    "carries, so a person cannot tell a switch from a tool they may not use or a record that is "
    "not there. The administrator's trace names the tool and whether the stop was the install's "
    "or a department's, and the exception's detail names the switch, who threw it and when; "
    "neither is ever a response body, because a response that named a switch would tell a "
    "department which of its tools somebody had decided it should not have."
)

#: Why a switch nobody could read refuses the call.
AN_UNREADABLE_SWITCH_REFUSES_THE_CALL: Final = (
    "If the switch table cannot be read, nobody can say whether an administrator switched this "
    "tool off, and carrying on would ignore a stop during whatever made the table unreachable. "
    "brain.ops.model_service decides the same for a provider switch nobody could read."
)


class ToolSwitchedOffError(Denied):
    """A call refused because its tool is switched off, for the install or the caller's department.

    `Denied`, so a response carries the sentence every refusal carries and a call site that
    already passes `BrainError` through turns it into the same answer as any other refusal. See
    `THE_ASKER_IS_NEVER_TOLD_WHICH_SWITCH`. `switch` is None when the switches could not be read.
    """

    def __init__(self, tool: str, switch: Switch | None) -> None:
        self.tool = tool
        self.switch = switch
        detail = (
            switch.described()
            if switch is not None
            else f"the switches for tool {tool!r} could not be read, so the call was refused"
        )
        super().__init__(detail)


def caller_of(args: tuple[object, ...], kwargs: Mapping[str, object]) -> str | None:
    """The principal a handler is being called for, read off the reach it was handed, or None.

    Every handler in this tree is called with `entitlement=`; a positional reach is read too.
    None is a call nobody can place in a department, which `SwitchSource.stop_for` answers with
    any stop on the tool at all.
    """
    for value in (kwargs.get("entitlement"), *args, *kwargs.values()):
        if isinstance(value, EntitlementSet):
            return value.principal_id
    return None


async def _checked_call(
    name: str,
    handler: Callable[..., object],
    source: SwitchSource,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    """Ask the source, refuse on a stop or on no answer, and otherwise run the handler."""
    try:
        stop = await source.stop_for(name, caller_of(args, kwargs))
    except Exception as exc:
        # Broad on purpose: whatever the driver raised, the answer is the same. See
        # `AN_UNREADABLE_SWITCH_REFUSES_THE_CALL`.
        log.warning("tool switch could not be read", tool=name, error=type(exc).__name__)
        raise ToolSwitchedOffError(name, None) from exc
    if stop is not None:
        log.warning("tool call refused by a switch", tool=name, control=stop.scope.value)
        raise ToolSwitchedOffError(name, stop)
    answered = handler(*args, **kwargs)
    return await answered if inspect.isawaitable(answered) else answered


# ----------------------------------------------------------------- the registration


@dataclass(frozen=True)
class RegisteredTool:
    """One tool that passed every refusal, with what the registry had to add.

    `capability` is a `Capability` and never the string it was parsed from, so no caller
    downstream has to re-parse it and no caller can decide for itself what an unparseable
    one means.

    `scope` is here rather than on `ToolDefinition` because that model is frozen with
    `extra="forbid"` and belongs to `brain.core.envelope`. It is None for a DELEGATED tool,
    where the source enforces its own permissions, and mandatory for a SERVICE one.
    """

    definition: ToolDefinition
    handler: Callable[..., object]
    capability: Capability
    result_contract: ResultContract = ResultContract.TYPED
    scope: Scope | None = None
    #: Which of the owner's sensitive effects this tool has, where it named one (M12.3.8).
    sensitive_effect: SensitiveEffect | None = None

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def effect(self) -> EffectClass:
        """Read, write or irreversible, as the Tools screen says it."""
        return effect_class(self.definition)

    @property
    def leash_ceiling(self) -> AutonomyTier:
        """The highest rung a leash entry on this tool keeps. See `leash_ceiling`."""
        return leash_ceiling(self.definition)

    @property
    def object_name(self) -> str:
        """The entity this tool returns. `sweep_slug_collisions` calls this a tool object."""
        return self.definition.entity

    @property
    def source(self) -> str:
        """The system the call goes to, taken from the name so it is always present."""
        return self.definition.name.split(".", 1)[0]


@dataclass
class ToolRegistry:
    """Every tool that may be called, and the door each one came through.

    An instance rather than a module-level singleton, for the reason
    `brain.core.redaction.ChannelAdapterRegistry` gives about its own: a singleton is
    process state in a layer that otherwise holds none, one test's registration would be
    visible to the next, and "which tools exist" would depend on import order in exactly the
    way the duplicate-name rule exists to prevent.

    Iterating a registry yields `ToolDefinition`s in name order, which is what
    `brain.gate.catalogue.project` takes. The registry therefore feeds the projector without
    either of them importing the other, and there is no second path by which a raw list of
    tools could reach a connector to be filtered there.
    """

    _tools: dict[str, RegisteredTool] = field(default_factory=dict)
    _frozen: bool = False
    #: Asked at every call once `govern` has attached it. See `A_SWITCH_ONLY_EVER_NARROWS`.
    _switches: SwitchSource | None = None

    # ------------------------------------------------------------------ registering
    def register(
        self,
        definition: ToolDefinition,
        handler: Callable[..., object],
        *,
        result_contract: ResultContract = ResultContract.TYPED,
        scope: Scope | None = None,
        sensitive_effect: SensitiveEffect | None = None,
    ) -> RegisteredTool:
        """Check a tool against every rule in this module, then record it.

        The handler is required and not optional. A definition registered without one could
        not be checked against `assert_tool_returns_typed_result`, so "registration refuses a
        tool that cannot be redacted" would hold for every tool except the ones somebody was
        in a hurry about. Rejected for the same reason: registering a definition now and
        attaching the handler later, which makes the check a step rather than a door.

        `UntypedShapeError` is allowed to propagate rather than being wrapped. It is the
        redaction contract's own refusal, documented where the contract lives, and wrapping
        it here would make a rule of the redactor look like an opinion of the registry, which
        is a thing a registry can be replaced without.
        """
        if self._frozen:
            msg = (
                f"tool {definition.name!r} was registered after the registry was frozen; a "
                "tool that appears once a catalogue has already been projected is one whose "
                "presence depends on when the request arrived"
            )
            raise ToolRegistrationError(msg)

        assert_tool_name(definition.name)

        existing = self._tools.get(definition.name)
        if existing is not None:
            # Refused outright, including for an identical re-registration.
            # `ChannelAdapterRegistry` permits re-registering the same object, because an
            # adapter is a function and a module can be imported under two names. A registry
            # is an instance built by one owner, so a second registration of a name is a bug
            # in that owner's wiring, and "identical" is a judgement about handler identity
            # that a decorator quietly breaks.
            msg = (
                f"two tools are registered as {definition.name!r}; which of them a caller "
                "reaches would be decided by import order, and the loser is invisible rather "
                "than broken"
            )
            raise ToolRegistrationError(msg)

        assert_object_name(definition)
        assert_source_agrees(definition)
        assert_object_not_reserved(definition)
        capability = capability_for(definition)
        assert_effect_matches_capability(definition, capability)
        assert_sensitive_effect_declared(definition, sensitive_effect)
        assert_service_tool_is_scoped(definition, scope)
        assert_result_contract(definition, capability, result_contract)
        # Last, because it is the only check that inspects something other than the
        # declaration, and its message is about the function rather than the tool.
        assert_tool_returns_typed_result(handler)

        registered = RegisteredTool(
            definition=definition,
            # The guard, never the handler itself, so no path to a handler skips the switch.
            # See `THE_SWITCH_IS_ASKED_AT_THE_CALL_AND_NOT_AT_THE_LOOKUP`.
            handler=self._guarded(definition.name, handler),
            capability=capability,
            result_contract=result_contract,
            scope=scope,
            sensitive_effect=sensitive_effect,
        )
        self._tools[definition.name] = registered
        return registered

    def _guarded(self, name: str, handler: Callable[..., object]) -> Callable[..., object]:
        """The handler behind the switch: unchanged until `govern`, and asked every call after.

        Wrapped with `functools.wraps`, so a caller reading the handler's signature and hints,
        as `brain.automation_routes` does to find its request model, reads the tool's own. With
        no source it returns whatever the handler returns, a coroutine or a value, exactly as
        before; with one it returns a coroutine, which every caller already awaits through
        `inspect.isawaitable` because the registry has always held handlers of both kinds.
        """

        @functools.wraps(handler)
        def guarded(*args: object, **kwargs: object) -> object:
            source = self._switches
            if source is None:
                return handler(*args, **kwargs)
            return _checked_call(name, handler, source, args, kwargs)

        return guarded

    # --------------------------------------------------------------- the switch (M12.4.3)
    def govern(self, source: SwitchSource) -> Self:
        """Attach the switch source every call is asked against from now on.

        Allowed on a frozen registry, because a switch only narrows and a registry that could
        not be governed after its checks ran would have to be governed before them, by whoever
        builds it, which is the one module this may not change. Refused a second time: a second
        source would replace the first, and replacing the source is the one way to make a switch
        stop refusing without anybody switching it on.
        """
        if self._switches is not None:
            msg = (
                "the tool registry is already governed by a switch source; replacing it would "
                "lift every stop without anybody switching a tool back on"
            )
            raise ToolRegistrationError(msg)
        self._switches = source
        return self

    @property
    def is_governed(self) -> bool:
        return self._switches is not None

    # ------------------------------------------------------ the default leash (M12.1.3)
    def tighten(self, leash: Leash) -> Leash:
        """The leash with every entry on a registered tool held to that tool's leash ceiling.

        `min`, the only shape in which a side effect may touch a leash (`rung_ceiling`), so a
        rung only ever falls. An entry whose target no tool here carries is kept as written:
        `Leash.rung_for` answers SHADOW for whatever matches nothing anyway.

        Called by `brain.gate.invoke.invoke`, the one place a run is assembled, and by nothing
        that draws a page: the leash a page shows is the configured one. See
        `brain.gate.invoke.A_RUN_IS_HELD_TO_THE_RUNG_ITS_TOOLS_SIDE_EFFECTS_ALLOW`.
        """
        return Leash(
            entries=tuple(
                LeashEntry(
                    agent_id=entry.agent_id,
                    target=entry.target,
                    scope=entry.scope,
                    rung=(
                        min(entry.rung, self._tools[entry.target].leash_ceiling)
                        if entry.target in self._tools
                        else entry.rung
                    ),
                )
                for entry in leash.entries
            )
        )

    # --------------------------------------------------------------------- reading
    def get(self, name: str) -> RegisteredTool:
        """One tool by name, or a refusal. Never None.

        Returning None would put the decision about a missing tool in every caller, and the
        cheapest thing a caller does with None is skip it.
        """
        found = self._tools.get(name)
        if found is None:
            msg = f"no tool is registered as {name!r}"
            raise ToolRegistrationError(msg)
        return found

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def object_names(self) -> tuple[str, ...]:
        """Every distinct tool object, sorted.

        `brain.ops.sweeps.sweep_slug_collisions` compares tool objects against scope and
        agent slugs by reading `ToolDefinition(...)` literals out of the source text. That
        finds tools written as literals and misses tools built at run time from a connector's
        manifest, which is how most of them will arrive. This is the same list computed from
        what is actually registered, so the sweep has something to read once it can.
        """
        return tuple(sorted({t.definition.entity for t in self._tools.values()}))

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """What `brain.gate.catalogue.project` consumes, in a stable order.

        Sorted here as well as in `project`, so that anything else reading a registry gets
        the same order and two identical builds produce identical catalogues.
        """
        return tuple(self._tools[name].definition for name in sorted(self._tools))

    def __iter__(self) -> Iterator[ToolDefinition]:
        return iter(self.definitions())

    def __len__(self) -> int:
        return len(self._tools)

    # ------------------------------------------------------- startup check (M12.1.5)
    def validate(self) -> tuple[str, ...]:
        """Everything that can only be checked once the whole registry is present.

        Today that is one rule: two tools may not carry the same description. Names are
        already unique, and the description is the other half of what the model chooses
        from, so two tools described identically are chosen between by position in a list.
        That is the same failure as a duplicate name arriving one layer later, and it cannot
        be caught at `register` time because it is a property of a pair.

        Compared on a folded form, so "Reads a client" and "reads a client." collide.
        Two descriptions only a machine can tell apart are one description to the reader
        that matters, which is a model.
        """
        by_description: dict[str, list[str]] = {}
        for name in sorted(self._tools):
            text = self._tools[name].definition.description
            folded = " ".join(text.lower().split()).rstrip(".")
            by_description.setdefault(folded, []).append(name)
        return tuple(
            f"tools {names} share the description {folded!r}; the model chooses between "
            "them by position rather than by meaning"
            for folded, names in sorted(by_description.items())
            if len(names) > 1
        )

    def freeze(self) -> Self:
        """Run the whole-registry checks and refuse further registration (M12.1.5).

        Called at startup, and it raises rather than logging. A registry that starts with a
        finding is a registry somebody has to notice; a warning at boot is a warning nobody
        reads after the first week.

        Every finding is reported at once rather than the first one. Whoever is fixing this
        is looking at a build, and a build that reveals one problem per run is a build that
        takes an afternoon.
        """
        findings = self.validate()
        if findings:
            msg = "the tool registry cannot be frozen:\n  " + "\n  ".join(findings)
            raise ToolRegistrationError(msg)
        self._frozen = True
        return self

    @property
    def is_frozen(self) -> bool:
        return self._frozen
