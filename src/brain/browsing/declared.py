"""What a person declared about a system a browser may be pointed at, and what they signed.

`brain.browsing.targets` defines a target and says it is "a declaration by a person who has an
account on that system". Until this module the declaration had nowhere to live: the registry was a
value a check or a test built, `website_check` defaulted to an empty one, and an exception or an
exemption (`brain.browsing.autonomy`, `brain.browsing.skill_gate`) was a value type that said, in
both docstrings, that nothing kept it. This is the codec between a document a person writes and
those types, and the two small stores (`agent.browser_target`, `agent.browser_grant`, `0275`).

**The document is closed, and it derives what it could be tricked into stating.** Every key is
named and an unknown one is refused, so a field that would widen a target cannot ride in under a
name nobody reads. A surface does not declare its capability: it is derived from its verbs, the
browse capability for a surface that only opens and reads and the write capability for one that
does anything else, so a surface cannot be declared as a read that writes. A control names a verb
the surface admits and a credential binding names an origin the target allows, and a control that
types a credential names a placeholder some binding has, so an unresolvable credential is found
when the target is declared and not halfway through a run (`credentials.unresolvable`).

**A binding is a path and never a value, and the path is the one the runner may read.** The browser
runner's vault policy reads `browser/creds/+` and nothing else, so a binding to any other path is
refused when it is declared and not when a login fails. The seed of a one-time code is a binding of
kind `totp_seed` and is read in the control plane only (`credentials.resolve`).

**Reading a stored declaration can fail, and then the target is not declared.** A row written by an
older release that no longer parses is left out of the registry and named in the listing, because a
registry that kept a target it could not read would be keeping one it could not check.

**A grant is signed through the types that already refuse a bad one.** An exception is
`autonomy.sign`, which refuses a signer who could not perform the write, a surface with no write, a
past end and an end beyond a quarter; an exemption is `skill_gate.Exemption`, which refuses a
missing approver and a short reason. The table refuses the same again for a writer that is not
this one. The live ones are read at the moment a run is compiled and at the moment a skill is
assigned, with that moment's clock, so one that lapsed or was revoked is not read.

Rejected: one document holding everything, so that a grant could be edited in place; the grant
would then have no history and no signature that outlived the next edit. Rejected: storing the
capability a surface needs, which would make the declaration the place a read is quietly given a
write's permission.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.browsing.autonomy import AutonomyError, SurfaceException, sign
from brain.browsing.credentials import Binding, Bindings, CredentialError, SecretKind
from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
from brain.browsing.skill_gate import MAX_EXEMPTION, Exemption, SkillGateError
from brain.browsing.targets import (
    Control,
    Surface,
    Target,
    TargetError,
    TargetRegistry,
    Verb,
    is_write,
)
from brain.core.entitlement import EntitlementSet
from brain.gate.suspension_store import PRINCIPAL_SETTING
from brain.ops.secrets import SecretRef, VaultRole
from brain.tables.audit import attributed_to
from brain.tables.browsing import BrowserGrantRow, BrowserTargetRow

#: The keys a target document may carry, at each level. Closed: see the module docstring.
TARGET_KEYS: Final = frozenset({"name", "origins", "api_tools", "surfaces", "bindings"})
SURFACE_KEYS: Final = frozenset(
    {"name", "origin", "path", "verbs", "reads", "read_back", "controls"}
)
CONTROL_KEYS: Final = frozenset({"verb", "role", "label", "text", "placeholder"})
BINDING_KEYS: Final = frozenset({"placeholder", "path", "origin", "kind"})

#: The only vault paths a browser binding may name: the one mount the runner's policy reads.
BINDING_PATH_RE: Final = re.compile(r"^browser/creds/[a-z][a-z0-9_-]{0,62}$")

#: What a grant's kind is, as the table spells it.
EXCEPTION: Final = "exception"
EXEMPTION: Final = "exemption"

#: Why a surface is not asked for its capability.
A_SURFACE_CANNOT_BE_DECLARED_AS_A_READ_THAT_WRITES: Final = (
    "The capability a surface needs is derived from the verbs it admits: browse for a surface that "
    "only opens and reads, write for any other. Accepting one in the declaration would make the "
    "declaration the place a read is quietly given a write's permission."
)

#: Why a binding to any other vault path is refused when it is declared.
A_BINDING_NAMES_THE_ONE_MOUNT_THE_RUNNER_MAY_READ: Final = (
    "The browser runner's vault policy reads browser/creds/<name> and nothing else, so a binding "
    "to another path would fail at the first login, in a run, with a credential refused. It is "
    "refused here, where the person can still change it."
)


class DeclarationError(Exception):
    """A declaration or a grant could not be read or kept. The sentence says what to change."""


@dataclass(frozen=True)
class Declared:
    """One declared system: the target a plan is made against, and the bindings its login uses."""

    target: Target
    bindings: Bindings


@dataclass(frozen=True)
class Stored:
    """A declared system as the install holds it: who declared it, and when."""

    declared: Declared
    set_by: str
    at: datetime


@dataclass(frozen=True)
class Loaded:
    """Every system this install declares, and the names of the ones that could not be read."""

    declared: Mapping[str, Stored]
    unreadable: tuple[str, ...] = ()

    def registry(self) -> TargetRegistry:
        return TargetRegistry(
            targets=tuple(self.declared[name].declared.target for name in sorted(self.declared))
        )


# ------------------------------------------------------------------ the document
def _closed(document: Mapping[str, Any], keys: frozenset[str], where: str) -> None:
    unknown = sorted(set(document) - keys)
    if unknown:
        msg = f"{where} has {', '.join(unknown)}, which a declaration does not take"
        raise DeclarationError(msg)


def _list_of(document: Mapping[str, Any], key: str, where: str) -> list[Any]:
    found = document.get(key, [])
    if not isinstance(found, list):
        msg = f"{where} has {key} that is not a list"
        raise DeclarationError(msg)
    return found


def _text_of(document: Mapping[str, Any], key: str, where: str, *, required: bool = True) -> str:
    found = document.get(key, "")
    if not isinstance(found, str) or (required and not found.strip()):
        msg = f"{where} needs {key} as text"
        raise DeclarationError(msg)
    return found


def _verb(name: object, where: str) -> Verb:
    try:
        return Verb(str(name))
    except ValueError:
        msg = (
            f"{where} names the verb {name!r}, which is not one of {sorted(v.value for v in Verb)}"
        )
        raise DeclarationError(msg) from None


def _control(document: object, where: str) -> Control:
    if not isinstance(document, dict):
        msg = f"{where} is not an object"
        raise DeclarationError(msg)
    _closed(document, CONTROL_KEYS, where)
    try:
        return Control(
            verb=_verb(document.get("verb"), where),
            role=_text_of(document, "role", where),
            label=_text_of(document, "label", where),
            text=_text_of(document, "text", where, required=False),
            placeholder=_text_of(document, "placeholder", where, required=False),
        )
    except TargetError as refused:
        raise DeclarationError(f"{where}: {refused}") from None


def _surface(document: object, where: str) -> Surface:
    if not isinstance(document, dict):
        msg = f"{where} is not an object"
        raise DeclarationError(msg)
    _closed(document, SURFACE_KEYS, where)
    verbs = frozenset(_verb(one, where) for one in _list_of(document, "verbs", where))
    reads = tuple(str(one) for one in _list_of(document, "reads", where))
    controls = tuple(
        _control(one, f"{where} control {index + 1}")
        for index, one in enumerate(_list_of(document, "controls", where))
    )
    capability = (
        ACT_ON_SURFACE_CAPABILITY if any(is_write(one) for one in verbs) else BROWSE_SURFACE
    )
    try:
        return Surface(
            name=_text_of(document, "name", where),
            origin=_text_of(document, "origin", where),
            path=_text_of(document, "path", where),
            verbs=verbs,
            capability=capability,
            reads=reads,
            read_back=_text_of(document, "read_back", where, required=False),
            controls=controls,
        )
    except TargetError as refused:
        raise DeclarationError(f"{where}: {refused}") from None


def _binding(document: object, where: str) -> Binding:
    if not isinstance(document, dict):
        msg = f"{where} is not an object"
        raise DeclarationError(msg)
    _closed(document, BINDING_KEYS, where)
    path = _text_of(document, "path", where)
    if not BINDING_PATH_RE.match(path):
        msg = f"{where}: {A_BINDING_NAMES_THE_ONE_MOUNT_THE_RUNNER_MAY_READ}"
        raise DeclarationError(msg)
    try:
        kind = SecretKind(_text_of(document, "kind", where, required=False) or "password")
        return Binding(
            placeholder=_text_of(document, "placeholder", where),
            ref=SecretRef(path=path, role=VaultRole.BROWSER_RUNNER),
            origin=_text_of(document, "origin", where),
            kind=kind,
        )
    except (CredentialError, ValueError) as refused:
        raise DeclarationError(f"{where}: {refused}") from None


def declared_from(document: object) -> Declared:
    """A system as a person wrote it, or the sentence saying what to change."""
    if not isinstance(document, dict):
        msg = "a declaration is an object"
        raise DeclarationError(msg)
    _closed(document, TARGET_KEYS, "the declaration")
    name = _text_of(document, "name", "the declaration")
    surfaces = tuple(
        _surface(one, f"surface {index + 1}")
        for index, one in enumerate(_list_of(document, "surfaces", "the declaration"))
    )
    bindings_list = tuple(
        _binding(one, f"credential {index + 1}")
        for index, one in enumerate(_list_of(document, "bindings", "the declaration"))
    )
    try:
        target = Target(
            name=name,
            origins=frozenset(str(one) for one in _list_of(document, "origins", "the declaration")),
            surfaces=surfaces,
            api_tools=tuple(str(one) for one in _list_of(document, "api_tools", "the declaration")),
        )
        bindings = Bindings(bindings=bindings_list)
    except (TargetError, CredentialError) as refused:
        raise DeclarationError(str(refused)) from None
    for one in bindings_list:
        if one.origin not in target.origins:
            msg = (
                f"the credential {one.placeholder} is bound to an origin the target does not allow"
            )
            raise DeclarationError(msg)
    wanted = {
        control.placeholder
        for surface in surfaces
        for control in surface.controls
        if control.placeholder
    }
    missing = sorted(wanted - bindings.placeholders())
    if missing:
        msg = f"a control types {', '.join(missing)}, which no credential in the declaration binds"
        raise DeclarationError(msg)
    return Declared(target=target, bindings=bindings)


def document_of(declared: Declared) -> dict[str, Any]:
    """The document `declared_from` reads back into the same value."""
    target = declared.target
    return {
        "name": target.name,
        "origins": sorted(target.origins),
        "api_tools": list(target.api_tools),
        "surfaces": [
            {
                "name": surface.name,
                "origin": surface.origin,
                "path": surface.path,
                "verbs": sorted(verb.value for verb in surface.verbs),
                "reads": list(surface.reads),
                "read_back": surface.read_back,
                "controls": [
                    {
                        "verb": control.verb.value,
                        "role": control.role,
                        "label": control.label,
                        "text": control.text,
                        "placeholder": control.placeholder,
                    }
                    for control in surface.controls
                ],
            }
            for surface in target.surfaces
        ],
        "bindings": [
            {
                "placeholder": one.placeholder,
                "path": one.ref.path,
                "origin": one.origin,
                "kind": one.kind.value,
            }
            for one in declared.bindings.bindings
        ],
    }


# ------------------------------------------------------------------ the targets
async def _as(session: AsyncSession, principal: str) -> None:
    """Say whose session this is, so the row's policy judges the person who is acting."""
    await session.execute(
        text("SELECT set_config(:name, :value, true)").bindparams(
            name=PRINCIPAL_SETTING, value=principal
        )
    )


async def _attributed(session: AsyncSession, who: str, ent_hash: str, trace_id: str) -> None:
    """Say whose session this is and whose act the ledger entry the row's trigger writes is.

    The trigger on `agent.browser_grant` appends a leash change in the same transaction and reads
    these three settings for its actor, its reach and its trace
    (`brain.tables.audit.attributed_to`). A route that skipped this would write the entry with
    thirty-two zeros for a reach.
    """
    await _as(session, who)
    for statement in attributed_to(actor_id=who, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


async def declare(session: AsyncSession, declared: Declared, *, by: str) -> None:
    """Keep a declaration as the newest for its name. Does not commit."""
    await _as(session, by)
    session.add(
        BrowserTargetRow(
            name=declared.target.name,
            definition=document_of(declared),
            retired=False,
            set_by=by,
        )
    )
    await session.flush()


async def retire(session: AsyncSession, name: str, *, by: str) -> bool:
    """Withdraw a declaration by writing a row that says so. False when nothing was declared."""
    held = (await load(session)).declared.get(name)
    if held is None:
        return False
    await _as(session, by)
    session.add(
        BrowserTargetRow(name=name, definition=document_of(held.declared), retired=True, set_by=by)
    )
    await session.flush()
    return True


async def load(session: AsyncSession) -> Loaded:
    """The newest row of every name, the ones not retired, read back through the codec."""
    rows = (
        (
            await session.execute(
                select(BrowserTargetRow)
                .distinct(BrowserTargetRow.name)
                .order_by(BrowserTargetRow.name, BrowserTargetRow.seq.desc())
            )
        )
        .scalars()
        .all()
    )
    found: dict[str, Stored] = {}
    unreadable: list[str] = []
    for row in rows:
        if row.retired:
            continue
        try:
            read = declared_from(row.definition)
        except DeclarationError:
            unreadable.append(row.name)
            continue
        found[row.name] = Stored(declared=read, set_by=row.set_by, at=row.created_at)
    return Loaded(declared=found, unreadable=tuple(unreadable))


async def registry_of(session: AsyncSession) -> TargetRegistry:
    """The targets this install declares, for a plan and for `website_check`."""
    return (await load(session)).registry()


# ------------------------------------------------------------------ the grants
@dataclass(frozen=True)
class GrantView:
    """One signed permission as a listing shows it. Revoked and lapsed ones are not listed."""

    seq: int
    kind: str
    target: str
    what: str
    signed_by: str
    reason: str
    expires_at: datetime


async def sign_exception(
    session: AsyncSession,
    target: Target,
    surface: str,
    *,
    signer: EntitlementSet,
    expires_at: datetime,
    reason: str,
    now: datetime,
    trace_id: str,
) -> SurfaceException:
    """Sign and keep an exception for one surface's writes. Does not commit.

    `autonomy.sign` decides everything: the surface must be declared and write, the signer must be
    able to perform the write, and the end must be ahead and within a quarter.
    """
    try:
        signed = sign(target, surface, signer=signer, expires_at=expires_at, reason=reason, now=now)
    except AutonomyError as refused:
        raise DeclarationError(str(refused)) from None
    await _attributed(session, signer.principal_id, signer.ent_hash(), trace_id)
    session.add(
        BrowserGrantRow(
            kind=EXCEPTION,
            target=target.name,
            surface=surface,
            signed_by=signer.principal_id,
            reason=reason,
            created_at=now,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return signed


async def sign_exemption(
    session: AsyncSession,
    *,
    skill: str,
    target: str,
    approver: str,
    expires_at: datetime,
    reason: str,
    now: datetime,
    ent_hash: str,
    trace_id: str,
) -> Exemption:
    """Keep an exemption for a skill to drive a target that has an API. Does not commit."""
    if expires_at <= now or expires_at - now > MAX_EXEMPTION:
        msg = f"an exemption ends in the future and within {MAX_EXEMPTION.days} days"
        raise DeclarationError(msg)
    try:
        signed = Exemption(
            skill=skill, target=target, approver=approver, expires_at=expires_at, reason=reason
        )
    except SkillGateError as refused:
        raise DeclarationError(str(refused)) from None
    await _attributed(session, approver, ent_hash, trace_id)
    session.add(
        BrowserGrantRow(
            kind=EXEMPTION,
            target=target,
            skill=skill,
            signed_by=approver,
            reason=reason,
            created_at=now,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return signed


async def revoke(
    session: AsyncSession, seq: int, *, by: str, now: datetime, ent_hash: str, trace_id: str
) -> bool:
    """End a grant now. False when it is not there, already revoked or already lapsed."""
    await _attributed(session, by, ent_hash, trace_id)
    changed = await session.execute(
        update(BrowserGrantRow)
        .where(
            BrowserGrantRow.seq == seq,
            BrowserGrantRow.revoked_at.is_(None),
            BrowserGrantRow.expires_at > now,
        )
        .values(revoked_at=now, revoked_by=by)
    )
    await session.flush()
    return bool(getattr(changed, "rowcount", 0))


async def _live(session: AsyncSession, now: datetime) -> Sequence[BrowserGrantRow]:
    """Every grant in force at `now`, whatever its kind, oldest first."""
    return (
        (
            await session.execute(
                select(BrowserGrantRow)
                .where(BrowserGrantRow.revoked_at.is_(None), BrowserGrantRow.expires_at > now)
                .order_by(BrowserGrantRow.seq)
            )
        )
        .scalars()
        .all()
    )


async def live_exceptions(
    session: AsyncSession, now: datetime, *, target: str | None = None
) -> tuple[SurfaceException, ...]:
    """The exceptions in force at `now`, for `compile_envelope`. One that lapsed is not here."""
    return tuple(
        SurfaceException(
            target=row.target,
            surface=str(row.surface),
            signed_by=row.signed_by,
            expires_at=row.expires_at,
            reason=row.reason,
        )
        for row in await _live(session, now)
        if row.kind == EXCEPTION and (target is None or row.target == target)
    )


async def live_exemptions(session: AsyncSession, now: datetime) -> tuple[Exemption, ...]:
    """The exemptions in force at `now`, for `skill_gate.may_load`."""
    return tuple(
        Exemption(
            skill=str(row.skill),
            target=row.target,
            approver=row.signed_by,
            expires_at=row.expires_at,
            reason=row.reason,
        )
        for row in await _live(session, now)
        if row.kind == EXEMPTION
    )


async def listing(session: AsyncSession, now: datetime) -> tuple[GrantView, ...]:
    """Every grant in force at `now`, oldest first: what the page shows until each lapses."""
    rows = await _live(session, now)
    return tuple(
        GrantView(
            seq=row.seq,
            kind=row.kind,
            target=row.target,
            what=str(row.surface or row.skill),
            signed_by=row.signed_by,
            reason=row.reason,
            expires_at=row.expires_at,
        )
        for row in rows
    )
