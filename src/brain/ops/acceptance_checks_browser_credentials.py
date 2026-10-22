"""Install acceptance check: a credential typed into a page reaches the page and is kept nowhere,
and a run's observation of a page is a tree and never a picture.

**What this joins that the credential and recording tests do not.** `credentials.resolve` is tested
with a vault, `recording.record` is tested with lines, and `driver._finish` is tested with a run.
The claim an owner cares about is the whole path: an instruction names a placeholder, the driver
turns it into a value at the moment of the action and in one line only, the page receives it, and
afterwards the stored transcript, the run's result and the vault's leases hold no trace of it. This
check sends one sealed envelope with a typing step through `driver.run_envelope` to the product's
own runner, over a page the check holds and a vault the check holds, four times:

- **The value reaches the page and goes no further** (M19.4.4): the page's `act` is given the value,
  the lease is revoked, and no object the run wrote and no field of the result holds it.
- **A page that shows the value back is an incident, and is still scrubbed** (M19.4.4): the result
  names the line it was found in, and the stored transcript still holds nothing.
- **A binding is for one origin** (M19.4.1 is not claimed, but the refusal is how a value is kept
  from a page that was not meant to have it): where the page is not the bound origin, no lease is
  issued and the run ends on that.
- **An observation is a tree** (M19.1.4): the snapshot a runner sends has the sequence, the origin
  and the nodes and no field a picture could arrive in, and `vision_gaps` finds none on the types.

**The vault and the page are stand-ins and say so.** The code that decides is run unchanged. What
this does not show is OpenBao issuing a lease or Chromium echoing a password into a tree.

The check writes nothing: the driver's ledger is a quiet stand-in and the recordings go to memory.

Task ids: M19.4.4, M19.1.4
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_browser import InProcessRunner, _Link, _Objects
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the enforcement check's (2307).
CHECK_ORDER: Final = 2308

#: The made-up website's origin, and one it is not. Nothing resolves either.
ORIGIN: Final = "https://acceptance-check.invalid"
ELSEWHERE: Final = "https://elsewhere.invalid"

#: The value the stand-in vault issues. Long enough to be scrubbed (`credentials.MIN_SCRUBBABLE`),
#: and with a quote and a backslash in it, because that is how a line holds a value that needs
#: escaping. It is a made-up value and no credential.
SECRET: Final = 'p"ass\\word-for-the-check-1'  # noqa: S105 - made up for the check

PLACEHOLDER: Final = "{{secret:portal_password}}"
FIELD: Final = "n12"

A_VALUE_WAS_KEPT: Final = "a credential value was found in what the run stored or returned"
A_VALUE_DID_NOT_REACH_THE_PAGE: Final = "a credential was not typed into the page it was bound to"
A_LEASE_WAS_LEFT: Final = "a credential's lease was not revoked after the action"
A_SHOWN_VALUE_WAS_NOT_AN_INCIDENT: Final = (
    "a page that showed the credential back was not reported as an incident"
)
A_VALUE_WENT_TO_THE_WRONG_ORIGIN: Final = (
    "a credential was issued or typed for an origin it is not bound to"
)
AN_OBSERVATION_HELD_A_PICTURE: Final = "an observation of a page carried more than a tree"


@dataclass
class _Page:
    """A browser with one text field. `shows_back` puts what was typed into the next tree."""

    shows_back: bool = False
    lands_on: str = ORIGIN
    at: str = "null"
    typed: str = ""
    acted: list[tuple[str, str, str]] = field(default_factory=list)

    def navigate(self, url: str) -> None:
        self.at = self.lands_on

    def origin(self) -> str:
        return self.at

    def accessibility_tree(self) -> Any:
        label = f"Welcome {self.typed}" if self.shows_back and self.typed else "Password"
        return {
            "nodes": [
                {
                    "nodeId": "1",
                    "backendDOMNodeId": 12,
                    "role": {"value": "textbox"},
                    "name": {"value": label},
                }
            ]
        }

    def act(self, verb: Any, ref: str, text: str) -> None:
        self.acted.append((str(verb), ref, text))
        self.typed = text

    def capture(self) -> bytes:
        return b"a masked picture"


@dataclass
class _Script:
    steps: Sequence[Any]

    def next(self, index: int, last: Any) -> Any:
        return self.steps[index - 1] if index <= len(self.steps) else None


class _Vault:
    """A vault that issues one known value and records every issue and revocation."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.issued: list[str] = []
        self.revoked: list[str] = []

    def issue(self, ref: Any, ttl: timedelta) -> Any:
        from brain.ops.secrets import Lease

        self.issued.append(ref.path)
        return Lease(
            lease_id=f"lease-{len(self.issued)}",
            ref=ref,
            secret=SECRET,
            issued_at=self.now,
            expires_at=self.now + ttl,
        )

    def revoke(self, lease_id: str) -> None:
        self.revoked.append(lease_id)


class _Quiet:
    """A ledger that writes nothing: this check opens no session row."""

    async def opened(self, *, run_id: str, trace_id: str, at: datetime) -> None:
        return None

    async def closed(self, *, run_id: str, at: datetime, recording: Any) -> str | None:
        return None


async def typing_run(
    h: Harness, page: _Page, vault: _Vault, bound: str, *, then: Sequence[Any] = ()
) -> tuple[Any, _Objects]:
    """One sealed typing step through the driver to the product's own runner, and what it stored.

    The envelope opens the login surface and types the bound credential into its one field; `then`
    are instructions sent after, for a check that wants the run to go on (open the page again). The
    page, the vault and the origin the binding is for are the caller's, so each check chooses what
    is wrong with them.
    """
    from brain.browsing.credentials import Binding, Bindings
    from brain.browsing.driver import Instruction, RunDeps, Substitution, run_envelope
    from brain.browsing.envelope import compile_envelope
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
    from brain.browsing.targets import Control, Surface, Target, TargetRegistry, Verb
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier
    from brain.ops.halt import NOTHING_HALTED
    from brain.ops.secrets import SecretRef, VaultRole

    target = Target(
        name=f"acceptance_{h.run}_login",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="login",
                origin=ORIGIN,
                path="/login",
                verbs=frozenset({Verb.OPEN, Verb.TYPE}),
                capability=ACT_ON_SURFACE_CAPABILITY,
                controls=(Control(Verb.TYPE, "textbox", "Password", placeholder=PLACEHOLDER),),
            ),
        ),
    )
    asker = "acceptance_credentials_asker"
    reach = EntitlementSet(
        principal_id=asker,
        grants=(
            Grant(capability=BROWSE_SURFACE, scope=Scope.unrestricted()),
            Grant(capability=ACT_ON_SURFACE_CAPABILITY, scope=Scope.unrestricted()),
        ),
    )
    envelope = compile_envelope(
        plan(
            PlanRequest(
                goal=Goal(text="Sign in for the check", asked_by=asker),
                target=target.name,
                surfaces=("login",),
            ),
            TargetRegistry(targets=(target,)),
        ),
        target,
        run_id=f"acceptance_{h.run}_login",
        reach=reach,
        ceiling=AutonomyTier.AUTONOMOUS,
    )
    from brain.browsing.approval import EnvelopeApproval

    approval = EnvelopeApproval(
        run_id=envelope.run_id,
        envelope_digest=envelope.digest(),
        approved_by="acceptance_credentials_approver",
        approved_at=h.now,
    )
    ref = SecretRef(path=f"browser/creds/acceptance_{h.run}", role=VaultRole.BROWSER_RUNNER)
    steps = [
        Instruction(surface="login", verb=Verb.OPEN),
        Instruction(surface="login", verb=Verb.TYPE, ref=FIELD, placeholder=PLACEHOLDER),
        *then,
    ]

    runner = InProcessRunner(page)  # type: ignore[arg-type]
    objects = _Objects()

    async def connect() -> _Link:
        return _Link(runner)

    result = await run_envelope(
        envelope,
        target,
        approval=approval,
        deps=RunDeps(
            connect=connect,
            ledger=_Quiet(),
            actor=_Script(steps),
            clock=lambda: h.now,
            halts=lambda: NOTHING_HALTED,
            backend=objects,
            substitution=Substitution(
                bindings=Bindings(bindings=(Binding(PLACEHOLDER, ref, bound),)),
                vault=vault,
            ),
        ),
        trace_id=h.trace_id,
    )
    return result, objects


@check(
    leaves=("M19.4.4", "M19.1.4"),
    sentence=(
        "A credential named by a placeholder is typed into the page it is bound to and no other, "
        "its lease is revoked, and neither the stored transcript nor the run's result holds the "
        "value, even when the page shows it back; and what a run observes of a page is a tree."
    ),
)
async def a_credential_reaches_the_page_and_is_kept_nowhere(h: Harness) -> None:
    from brain.browsing.observation import vision_gaps
    from brain.browsing.wire import WireError, decode

    async def run(page: _Page, vault: _Vault, bound: str) -> tuple[Any, _Objects]:
        return await typing_run(h, page, vault, bound)

    def holds_value(objects: _Objects, result: Any) -> bool:
        """Whether the value, plain or as a line holds it, is in a stored line or the result.

        The stored transcript is a file of JSON rows each holding one line, so a line is read out of
        its row before it is searched: searching the file's bytes would look for a value that has
        been escaped twice and report a clean transcript when the scrub had done nothing.
        """
        written = (SECRET, json.dumps(SECRET)[1:-1])
        lines = [line for _, line in _entries(objects)]
        returned = repr(result)
        return any(one in line for line in lines for one in written) or any(
            one in returned for one in written
        )

    # The value reaches the page, once, and goes no further.
    page, vault = _Page(), _Vault(h.now)
    result, objects = await run(page, vault, ORIGIN)
    if page.acted != [("type", FIELD, SECRET)]:
        raise CheckFailedError(A_VALUE_DID_NOT_REACH_THE_PAGE)
    if not vault.issued or len(vault.revoked) != len(vault.issued):
        raise CheckFailedError(A_LEASE_WAS_LEFT)
    if not objects.kept or holds_value(objects, result) or result.leaked:
        raise CheckFailedError(A_VALUE_WAS_KEPT)

    # A page that shows the value back is an incident, and the transcript is still scrubbed.
    echo_page, echo_vault = _Page(shows_back=True), _Vault(h.now)
    echoed, echo_objects = await run(echo_page, echo_vault, ORIGIN)
    if not echoed.leaked:
        raise CheckFailedError(A_SHOWN_VALUE_WAS_NOT_AN_INCIDENT)
    if holds_value(echo_objects, echoed):
        raise CheckFailedError(A_VALUE_WAS_KEPT)

    # A binding for another origin issues nothing and types nothing.
    other_page, other_vault = _Page(), _Vault(h.now)
    await run(other_page, other_vault, ELSEWHERE)
    if other_vault.issued or other_page.acted:
        raise CheckFailedError(A_VALUE_WENT_TO_THE_WRONG_ORIGIN)

    # What a run observes of a page is a tree.
    if vision_gaps():
        raise CheckFailedError(AN_OBSERVATION_HELD_A_PICTURE)
    seen = 0
    for _, text in _entries(objects):
        if '"kind":"snapshot"' not in text.replace(" ", ""):
            continue
        # `decode` accepts a snapshot with exactly the sequence, the origin and the nodes and
        # refuses any other field, so a line that is read at all is a tree; a second comparison
        # here would be a second copy of that rule (`wire.A_TOLERANT_READER_IS_A_SECOND_PROTOCOL`).
        try:
            decode(text.encode("utf-8"))
        except WireError:
            raise CheckFailedError(AN_OBSERVATION_HELD_A_PICTURE) from None
        seen += 1
    if not seen:
        raise CheckFailedError(AN_OBSERVATION_HELD_A_PICTURE)


def _entries(objects: _Objects) -> list[tuple[str, str]]:
    """The lines of every transcript the run stored, as `(direction, line)`."""
    found: list[tuple[str, str]] = []
    for body in objects.kept.values():
        for row in body.decode("utf-8", errors="replace").splitlines():
            try:
                parsed = json.loads(row)
            except ValueError:
                continue
            if isinstance(parsed, dict) and "line" in parsed:
                found.append((str(parsed.get("direction", "")), str(parsed["line"])))
    return found
