"""Installing a connector, turning it off, upgrading it, and refusing it on reconnect.

A connector is a deployment unit and is never granted: granting it would grant everything
behind it. So there is no capability here for *reaching through* a connector, and there must
not be one. What is here is the lifecycle, and the lifecycle exists because every one of its
transitions is a place a connector can change meaning without anybody deciding that it
should.

**There is a permission question in this file and there was not one until now.** "A
connector is never granted" answers who may read a source and it was being read as though it
answered who may install one, which is a different question with a different actor.
`read:connector` is the connector screen's read, and until M33.5.1.1 nothing at all stood
over the act: `register`, `enable`, `disable`, `upgrade` and `rebind` all took a manifest and
a clock and asked nobody. Installing a connector is the act that decides which sources exist
at all, and it comes before every other permission in the system rather than being bounded by
one. `INSTALL_AUTHORITY` is that capability, and it is named here rather than by a console,
which is `brain.console.scoped_authority`'s rule about the five acts it governs: a capability
invented in the rendering layer is one the administrator reviewing grants never meets.
`brain.console.reads.KNOWING_A_THING_EXISTS_IS_A_DISCLOSURE_OF_ITS_OWN` already says a
connector administrator "installs and binds and must never read a record", and
`brain.console.role_surfaces` already reasons about "every connector capability the registry
names". Both sentences were written against a registry that named none.

**`reconnect` deliberately does not ask.** It is the system checking a pin rather than a
person changing something, and a capability on it would mean a caller without one skips the
check: the connector goes on serving against a manifest nobody compared, and the quarantine
that should have fired reads as an authorisation problem in a log. See
`A_PIN_CHECK_THAT_ASKS_WHO_IS_CALLING_IS_A_PIN_CHECK_WITH_A_WAY_ROUND_IT`.

**Reconnect is the dangerous one.** A third-party server, an MCP server most of all, defines
its own tools and can redefine them between one connection and the next. The description is
what the model chooses on, so a server that rewrites "one invoice" to "every invoice for the
tenant" has changed what the connector does with no name anywhere changing. `reconnect`
compares the live manifest against the digest pinned at registration and fails closed, into
a state that `enable` cannot clear. A person has to look at the diff and accept it, which is
the whole point: the alternative is an operator clearing an amber badge at 2am.

**Upgrade is deliberate and reconnect is not.** They are the same digest comparison with
opposite defaults, and that is why they are two functions rather than one with a flag. A
flag would be set to `True` somewhere in a retry path within a month.

**Rotation is not a lifecycle event at all.** `brain.ops.secrets.borrow` takes a lease per
run and revokes it in a `finally`, and `assert_holds_no_credential` refuses a connector that
keeps one, so nothing here caches a credential and there is nothing for a rotation to
invalidate. `rebind` exists only for the case where the *path* moves, which is a
configuration edit rather than a deploy, and it deliberately cannot widen access: see
`REBINDING_CANNOT_WIDEN`.

**There is no unregister.** Removing a registration would leave projected rows keyed to a
source nothing can refresh, and they would go on being filtered, sorted and counted on
looking exactly like live ones. Disabling stops the fetching, which is the reversible half;
removing the rows is a decision about data with a retention answer attached, and it belongs
with whoever owns the projection store rather than with a registry that only holds
declarations.

Scope: domain logic. This holds declarations in memory; the table that survives a restart is
somebody else's, and this returns a `LifecycleEvent` per transition so that whoever owns the
ledger can record one without this module importing the audit layer.

Task ids: M11.1.6, M11.1.7, M11.2.6, M33.5.1.1
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Final

from brain.connectors.contract import AccessMode, ConnectorContractError, CredentialBinding
from brain.connectors.manifest import ConnectorManifest, ManifestError, manifest_digest
from brain.core.entitlement import Capability, EntitlementSet

# ------------------------------------------------------------------ written-down reasons
#: The capability that decides who may install, switch, upgrade or rebind a connector.
#:
#: `admin`, because this is configuration of the installation rather than agreement to
#: somebody else's act: `brain.ops.halt.HALT_CAPABILITY` and
#: `brain.ops.outbox.MANAGE_SUBSCRIBERS` are the two nearest neighbours and both are `admin:`
#: for the same reason. The noun is the connector screen's own noun, so the read and the act
#: govern one object and a reviewer reading a grant table sees `read:connector` beside
#: `admin:connector` rather than two unrelated strings.
INSTALL_AUTHORITY: Final = Capability(value="admin:connector")

#: Why the pin check is the one transition that does not ask who is calling.
A_PIN_CHECK_THAT_ASKS_WHO_IS_CALLING_IS_A_PIN_CHECK_WITH_A_WAY_ROUND_IT: Final = (
    "reconnect compares what the far side says it is against what was pinned, and it is "
    "reached on a connection rather than by somebody deciding something. Requiring a "
    "capability would mean a caller without one never performs the comparison: the connector "
    "goes on serving a manifest nobody checked, and the quarantine that should have fired "
    "arrives instead as an authorisation error in a log, which reads as a configuration "
    "problem with the caller. The refusals that matter for a redefinition are already there "
    "and they are about the manifest, not about the person."
)
#: Why a rebind may move a credential and never widen one.
REBINDING_CANNOT_WIDEN = (
    "A rebind points the connector at a different vault path. Widening it from read-only to "
    "write is a different decision with a different approver, and allowing both through one "
    "call means the audit line for 'somebody moved a path' and the line for 'somebody "
    "granted write' are the same line. Widening goes through `upgrade`, where the manifest "
    "changes, the digest moves, and a version number has to be bumped in front of a reviewer."
)

#: Why a failed pin cannot be cleared by enabling the connector again.
QUARANTINE_IS_NOT_CLEARED_BY_ENABLING = (
    "A pin failure means the far side is not the connector we installed. The remedy is a "
    "person reading the diff and accepting the new manifest through `upgrade`, which bumps a "
    "version and re-pins. If `enable` could clear it, the remedy would be one click on the "
    "amber badge, and the badge is looked at by whoever is on call at the time rather than by "
    "whoever understands what the tool descriptions now say."
)


class ConnectorState(enum.StrEnum):
    """Where a connector is in its life.

    `REGISTERED` and `ENABLED` are separate because installing is not switching on. The
    architecture's install wizard proves a template works before anybody uses it, and a
    connector that served traffic the instant it was declared would make that proof
    retrospective.
    """

    #: Declared and pinned, serving nothing.
    REGISTERED = "registered"
    #: Serving traffic.
    ENABLED = "enabled"
    #: Switched off deliberately. Reversible, and the projection is untouched.
    DISABLED = "disabled"
    #: The far side stopped matching its pin. Not reversible by `enable`; see
    #: `QUARANTINE_IS_NOT_CLEARED_BY_ENABLING`.
    QUARANTINED = "quarantined"


class ManifestPinError(ConnectorContractError):
    """The connector on the other end is not the one that was installed.

    Its own type rather than a `ManifestError`, because the two are found by different people
    at different times. A `ManifestError` is a badly written manifest and is caught at review;
    this is a manifest that was fine and has changed underneath us, and it is caught on a
    connection that used to work.
    """


class LifecycleError(ConnectorContractError):
    """A transition that is not available from where the connector is."""


class InstallAuthorityError(ConnectorContractError):
    """Somebody without `INSTALL_AUTHORITY` tried to change what is installed.

    Its own type rather than a `LifecycleError`, on the same argument `ManifestPinError`
    makes about itself: a `LifecycleError` says the connector is in the wrong state and is
    fixed by moving it, and this says the caller is the wrong person and is fixed by a grant.
    A caller catching one and retrying is right in one case and wrong in the other.
    """


def may_install(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this principal may change what is installed.

    One line, and it earns its place by being the only line: the capability is named once, so
    the console screen that does not exist yet cannot check a different one, and a test can
    pin it without importing a string literal from a template. This is
    `brain.ops.outbox.may_manage` at the connector.
    """
    return entitlement.holds(INSTALL_AUTHORITY, now)


def _assert_may_install(
    installer: EntitlementSet, *, act: str, connector: str, now: datetime
) -> None:
    """Refuse the act, naming the capability and nothing about the connector's state.

    Deliberately asked before the registry is consulted, in every transition below. Asking
    afterwards would let somebody without the capability learn whether a connector is
    installed, and which connectors a company reads is exactly the sort of thing a refusal
    must not confirm: `LifecycleError` from `get` says "no connector named x is installed",
    which is an answer to a question this caller was not entitled to ask.

    `now` is the transition's own instant rather than the wall clock, because every function
    here already has one and an expired contractor's grants stay on file. Letting `holds`
    default would make whether a rebind is refused depend on when the process happened to run
    rather than on when the decision was made.
    """
    if may_install(installer, now):
        return
    msg = (
        f"{installer.principal_id!r} does not hold {INSTALL_AUTHORITY.value} and cannot "
        f"{act} {connector!r}; installing a connector decides which sources exist at all, "
        "which is a decision before every other permission in the system rather than one "
        "bounded by them"
    )
    raise InstallAuthorityError(msg)


@dataclass(frozen=True)
class LifecycleEvent:
    """One transition, in the shape whoever owns the ledger needs.

    Returned rather than written. This module importing `brain.audit` would make a registry
    depend on an audit implementation, and the audit layer already refuses details it cannot
    classify; handing back a value lets the caller record it in whatever form their ledger
    takes without two modules agreeing on a schema.

    `digest` is carried on every event, including the ones that did not change it, because
    the question asked of this log afterwards is always "what was pinned when this happened".
    """

    connector: str
    action: str
    at: datetime
    state: ConnectorState
    digest: str
    detail: str = ""


@dataclass(frozen=True)
class RegisteredConnector:
    """One installed connector: what it declared, what was pinned, and where it is.

    The pin is stored beside the manifest rather than recomputed on demand. Recomputing would
    make the check tautological: a manifest object that had been replaced in place would hash
    to whatever it now says, and the comparison would pass every time.
    """

    manifest: ConnectorManifest
    digest: str
    state: ConnectorState

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def is_serving(self) -> bool:
        return self.state is ConnectorState.ENABLED


@dataclass
class ConnectorRegistry:
    """Every connector that has been installed, and the door each one came through.

    An instance rather than a module-level singleton, for the reason
    `brain.tools.registry.ToolRegistry` gives about its own: a singleton is process state in
    a layer that otherwise holds none, one test's registration would be visible to the next,
    and "which connectors exist" would depend on import order.
    """

    _entries: dict[str, RegisteredConnector] = field(default_factory=dict)

    # ------------------------------------------------------------------ installing
    def register(
        self, manifest: ConnectorManifest, *, installer: EntitlementSet, now: datetime
    ) -> LifecycleEvent:
        """Install a connector and pin its manifest (M33.5.1.1). It serves nothing until enabled.

        A second registration under the same name is refused rather than replacing the first.
        Replacing silently is how a redefinition arrives through the front door: the digest
        would be recomputed over the new manifest, the pin would match by construction, and
        the check in `reconnect` would be checking the new connector against itself.

        `installer` is required rather than defaulted, and that is the whole of the guard. An
        optional entitlement meaning "not checked" is a capability every existing caller
        skips, which is a rule written down and enforced nowhere.
        """
        _assert_may_install(installer, act="install", connector=manifest.name, now=now)
        if manifest.name in self._entries:
            msg = (
                f"connector {manifest.name!r} is already installed; registering over it "
                "would re-pin the digest against the new manifest, which is a redefinition "
                "arriving through the front door. Use upgrade, which requires a version bump"
            )
            raise LifecycleError(msg)
        digest = manifest_digest(manifest)
        self._entries[manifest.name] = RegisteredConnector(
            manifest=manifest, digest=digest, state=ConnectorState.REGISTERED
        )
        return LifecycleEvent(
            connector=manifest.name,
            action="register",
            at=now,
            state=ConnectorState.REGISTERED,
            digest=digest,
            detail=f"{manifest.transport} transport, version {manifest.version}",
        )

    def enable(self, name: str, *, installer: EntitlementSet, now: datetime) -> LifecycleEvent:
        """Start serving traffic from a connector that is not quarantined (M33.5.1.1)."""
        _assert_may_install(installer, act="enable", connector=name, now=now)
        entry = self.get(name)
        if entry.state is ConnectorState.QUARANTINED:
            msg = (
                f"connector {name!r} is quarantined and cannot be enabled. "
                f"{QUARANTINE_IS_NOT_CLEARED_BY_ENABLING}"
            )
            raise LifecycleError(msg)
        return self._transition(entry, ConnectorState.ENABLED, action="enable", now=now)

    def disable(
        self, name: str, *, installer: EntitlementSet, now: datetime, detail: str = ""
    ) -> LifecycleEvent:
        """Stop serving traffic (M33.5.1.1). Reversible, and it touches no projected row.

        Available from quarantine as well as from enabled, deliberately: disabling a
        quarantined connector is the correct first move during an incident, and a transition
        that refused it would leave an operator with nothing to do but clear the quarantine.

        It still takes the capability, although stopping something is the fail-safe
        direction. The company-wide stop that must not need a connector grant already exists
        and is a different capability on a different screen: `brain.ops.halt.HALT_CAPABILITY`,
        which is the global kill switch. Two paths to stopping, and the one an incident uses
        is not this one.
        """
        _assert_may_install(installer, act="disable", connector=name, now=now)
        entry = self.get(name)
        return self._transition(
            entry, ConnectorState.DISABLED, action="disable", now=now, detail=detail
        )

    # ------------------------------------------------------------------- upgrading
    def upgrade(
        self, manifest: ConnectorManifest, *, installer: EntitlementSet, now: datetime
    ) -> LifecycleEvent:
        """Accept a new manifest for an installed connector, and re-pin it (M33.5.1.1).

        Three refusals, and each closes a way a connector could change meaning quietly.

        **A different transport.** Refused. A connector that was a read-only database view
        and is now custom code is a different deployment unit with a different blast radius,
        and calling it an upgrade means it inherits the approval the first one was given.

        **A changed manifest with an unchanged version.** Refused. The version is the only
        thing a person reads in a console row, so a redefinition that keeps it is invisible
        exactly where it would be noticed.

        **A changed version with an unchanged manifest.** Allowed, and it re-pins to the same
        digest. Bumping a version because something outside the manifest changed is ordinary,
        and refusing it would teach people to avoid the version field.

        An upgrade leaves the connector where it was: an enabled connector goes on serving,
        and a quarantined one is released, because accepting the new manifest is exactly the
        remedy quarantine is waiting for. It is also the one path that clears a quarantine,
        which is why it takes the capability and `reconnect` does not: accepting a changed
        manifest is a person deciding something, and comparing one against its pin is not.
        """
        _assert_may_install(installer, act="upgrade", connector=manifest.name, now=now)
        entry = self.get(manifest.name)
        if manifest.transport is not entry.manifest.transport:
            msg = (
                f"connector {manifest.name!r} was installed as {entry.manifest.transport} and "
                f"the new manifest is {manifest.transport}; a different transport is a "
                "different deployment unit, and calling it an upgrade inherits the approval "
                "the first one was given"
            )
            raise LifecycleError(msg)
        digest = manifest_digest(manifest)
        if digest != entry.digest and manifest.version == entry.manifest.version:
            msg = (
                f"connector {manifest.name!r} changed without a version bump; the version is "
                "what a person reads in a console row, so a redefinition that keeps it is "
                "invisible in the one place it would be noticed"
            )
            raise ManifestError(msg)
        state = (
            ConnectorState.REGISTERED if entry.state is ConnectorState.QUARANTINED else entry.state
        )
        self._entries[manifest.name] = RegisteredConnector(
            manifest=manifest, digest=digest, state=state
        )
        return LifecycleEvent(
            connector=manifest.name,
            action="upgrade",
            at=now,
            state=state,
            digest=digest,
            detail=f"{entry.manifest.version} to {manifest.version}",
        )

    # ------------------------------------------------------------------ reconnecting
    def reconnect(self, name: str, observed: ConnectorManifest, *, now: datetime) -> LifecycleEvent:
        """Check what the far side says it is against what was pinned, and fail closed.

        Fails closed means quarantined and raising, not logged and continued. A pin that
        warns is a pin that has been overridden by the time anybody reads the warning, and
        the thing on the other side is by then already being described to a model.

        The event is returned inside the exception's flow by being recorded first: the state
        change happens whether or not the caller catches the error, because a connector that
        failed its pin and then stayed enabled because somebody swallowed an exception is the
        exact outcome this exists to prevent.
        """
        entry = self.get(name)
        observed_digest = manifest_digest(observed)
        if observed_digest == entry.digest:
            return LifecycleEvent(
                connector=name,
                action="reconnect",
                at=now,
                state=entry.state,
                digest=entry.digest,
                detail="manifest matches its pin",
            )
        self._entries[name] = replace(entry, state=ConnectorState.QUARANTINED)
        msg = (
            f"connector {name!r} no longer matches the manifest it was installed with: "
            f"pinned {entry.digest[:12]}, observed {observed_digest[:12]}. A tool "
            "description is what the model chooses on, so a silent redefinition changes "
            "what this connector does with no name changing. It is quarantined until "
            "somebody reads the diff and accepts it through upgrade"
        )
        raise ManifestPinError(msg)

    # -------------------------------------------------------------------- rebinding
    def rebind(
        self,
        name: str,
        binding: CredentialBinding,
        *,
        installer: EntitlementSet,
        now: datetime,
    ) -> LifecycleEvent:
        """Point a connector at a different vault path (M33.5.1.1). No redeploy, no re-pin.

        The digest deliberately does not cover the credential binding, so this changes
        nothing a reconnect would notice: see `manifest.WHAT_THE_DIGEST_COVERS_AND_WHY`. What
        it cannot do is widen access; see `REBINDING_CANNOT_WIDEN`.

        Ordinary rotation, where the vault mints a new value behind the same path, does not
        reach this function at all. Nothing holds a credential between runs, so the next
        `borrow` picks up the new value with no call to anything here.
        """
        _assert_may_install(installer, act="rebind", connector=name, now=now)
        entry = self.get(name)
        current = entry.manifest.credential
        if current.mode is AccessMode.READ_ONLY and binding.mode is AccessMode.WRITE:
            msg = (
                f"rebinding {name!r} would widen it from read-only to write. "
                f"{REBINDING_CANNOT_WIDEN}"
            )
            raise LifecycleError(msg)
        rebound = replace(entry.manifest, credential=binding)
        self._entries[name] = replace(entry, manifest=rebound)
        return LifecycleEvent(
            connector=name,
            action="rebind",
            at=now,
            state=entry.state,
            digest=entry.digest,
            detail=f"{current.ref.path} to {binding.ref.path}",
        )

    # ----------------------------------------------------------------------- reading
    def get(self, name: str) -> RegisteredConnector:
        entry = self._entries.get(name)
        if entry is None:
            msg = f"no connector named {name!r} is installed"
            raise LifecycleError(msg)
        return entry

    def has(self, name: str) -> bool:
        return name in self._entries

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def serving(self) -> tuple[str, ...]:
        """Every connector that may be called right now, sorted.

        This is the list a fan-out plan is built from. Deriving it here rather than letting
        each caller filter on `state` means a state added later is excluded until somebody
        decides it should serve traffic, which is the direction a default should fail in.
        """
        return tuple(sorted(name for name, e in self._entries.items() if e.is_serving))

    def __len__(self) -> int:
        return len(self._entries)

    # ----------------------------------------------------------------------- internal
    def _transition(
        self,
        entry: RegisteredConnector,
        state: ConnectorState,
        *,
        action: str,
        now: datetime,
        detail: str = "",
    ) -> LifecycleEvent:
        self._entries[entry.name] = replace(entry, state=state)
        return LifecycleEvent(
            connector=entry.name,
            action=action,
            at=now,
            state=state,
            digest=entry.digest,
            detail=detail,
        )
