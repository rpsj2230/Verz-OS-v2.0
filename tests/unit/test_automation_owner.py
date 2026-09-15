"""An automation runs as its owner, at the owner's reach as it is when the call arrives, and stops
when the owner goes.

Decisions over values, with no database: the credential, the owner's standing, the owner's reach
through the real `resolve` and `admit`, and adoption. `test_automation_owner_store.py` holds the
table and `test_automation_routes.py` holds the whole call.

Dates are 2019 and 2999, for the reason CLAUDE.md records about fixtures that go off: nothing
here is about the present, so no fixture here is allowed to cross it.

Task ids: none
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.channels import api_keys
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.admission import ASSURANCE_VERBS, CHANNEL_VERBS
from brain.ops.automation_owner import (
    AUTOMATION_ASSURANCE,
    AUTOMATION_CHANNEL,
    CREDENTIAL_PREFIX,
    AutomationRefusal,
    AutomationRefusedError,
    Registration,
    RegistrationError,
    Standing,
    adopt,
    automation_id_of,
    loggable,
    register,
    standing_of,
    verify,
)
from brain.ops.automation_owner import (
    awaiting_owner as awaiting_owner_awaited,
)
from brain.ops.automation_owner import (
    owner_of as owner_of_awaited,
)
from brain.ops.automation_owner import (
    owner_reach as owner_reach_awaited,
)

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
AUTOMATION = "nightly-price_check"
READ_PRICES = "read:price_list"


def person(pid: str, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
        primary_department="web",
        not_after=not_after,
    )


def grants(*capabilities: str) -> tuple[Grant, ...]:
    return tuple(
        Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in capabilities
    )


def ceiling(*capabilities: str, automation_id: str = AUTOMATION) -> EntitlementSet:
    return EntitlementSet(principal_id=automation_id, grants=grants(*capabilities))


def issued(
    owner: Principal | None = None, automation_id: str = AUTOMATION
) -> tuple[Registration, str]:
    made = register(
        automation_id=automation_id,
        owner=owner or person("u_owner"),
        declared_tools=frozenset({"local.read_price_list"}),
        ceiling=ceiling(READ_PRICES, automation_id=automation_id),
        now=NOW,
    )
    return made.registration, made.credential


def owner_of(registration: Registration, **given: Any) -> Principal:
    """`brain.ops.automation_owner.owner_of`, run to completion. It awaits its records."""
    return asyncio.run(owner_of_awaited(registration, **given))


def awaiting_owner(registrations: list[Registration], **given: Any) -> tuple[str, ...]:
    """`brain.ops.automation_owner.awaiting_owner`, run to completion."""
    return asyncio.run(awaiting_owner_awaited(registrations, **given))


def owner_reach(owner: Principal, **given: Any) -> EntitlementSet:
    """`brain.ops.automation_owner.owner_reach`, run to completion. It awaits the store."""
    return asyncio.run(owner_reach_awaited(owner, **given))


class Records:
    """A `PrincipalRecords`: the live principals, and nobody else."""

    def __init__(self, *live: Principal) -> None:
        self.live = {one.id: one for one in live}

    async def live_principal(self, principal_id: str) -> Principal | None:
        return self.live.get(principal_id)


# ------------------------------------------------------------------------ the credential


def test_a_credential_verifies_as_the_automation_it_was_issued_for() -> None:
    """The positive case every refusal below needs. Delete it and a `verify` that refuses
    everything passes this file."""
    registration, credential = issued()

    assert automation_id_of(credential) == AUTOMATION
    assert verify(credential, registration) is registration


def test_a_wrong_secret_is_refused() -> None:
    """Delete this and a credential is checked by its automation id alone, which is written in
    every log line about it."""
    registration, credential = issued()
    forged = credential[: -len("A")] + ("B" if credential.endswith("A") else "A")

    with pytest.raises(AutomationRefusedError) as refused:
        verify(forged, registration)
    assert refused.value.reason is AutomationRefusal.MISMATCHED_CREDENTIAL


def test_a_credential_for_one_automation_does_not_verify_against_another() -> None:
    """A registration looked up under one id and checked against a credential naming another is
    a caller that paired the wrong two. Delete this and a credential is proved against whichever
    registration the route happened to fetch."""
    mine, _ = issued(automation_id="mine")
    _, theirs = issued(automation_id="theirs")

    with pytest.raises(AutomationRefusedError) as refused:
        verify(theirs, mine)
    assert refused.value.reason is AutomationRefusal.UNKNOWN_AUTOMATION


@pytest.mark.parametrize(
    "presented",
    [
        "",
        "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.c2ln",
        "brn.handle123.AAAAAAAAAAAAAAAAAAAAAAAA",
        "bap.has.dot.AAAAAAAAAAAAAAAAAAAAAAAA",
        "bap.ok.short",
    ],
)
def test_something_that_is_not_an_automation_credential_is_refused_before_a_lookup(
    presented: str,
) -> None:
    """A person's token and an API key are not automation credentials, and neither is a string
    whose id would need a full stop. Delete this and a session token reaches the registration
    lookup with an id parsed out of its header segment."""
    registration, _ = issued()

    for attempt in (lambda: automation_id_of(presented), lambda: verify(presented, registration)):
        with pytest.raises(AutomationRefusedError) as refused:
            attempt()
        assert refused.value.reason is AutomationRefusal.MALFORMED


def test_the_secret_is_kept_as_a_digest_and_nowhere_as_itself() -> None:
    """Delete this and a registration field holding the plaintext is one debugging session
    away."""
    registration, credential = issued()
    secret = credential.rsplit(".", 1)[1]

    assert registration.credential_digest == hashlib.sha256(secret.encode()).hexdigest()
    assert secret not in repr(registration)


def test_what_is_logged_names_the_automation_and_never_the_secret() -> None:
    """Delete this and a refused credential is written to a log with that log's retention."""
    _, credential = issued()
    secret = credential.rsplit(".", 1)[1]

    assert loggable(credential) == f"{CREDENTIAL_PREFIX}.{AUTOMATION}"
    assert secret not in loggable(credential)
    assert loggable("not-one") == "<not an automation credential>"


def test_an_automation_credential_cannot_be_mistaken_for_an_api_key() -> None:
    """Asserted against the API key module rather than against a literal. An API key speaks for
    a service account whose reach is rebuilt under its own id, and this credential runs as a
    person; a prefix the two shared is a string somebody reads as the wrong one."""
    assert len({CREDENTIAL_PREFIX, api_keys.PREFIX}) == 2, "the two credentials share a prefix"
    _, credential = issued()
    assert api_keys.KEY_RE.match(credential) is None


# ------------------------------------------------------------------------ the registration


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"automation_id": "has.dot"}, "credential can carry"),
        ({"owner_principal_id": "  "}, "needs an owner"),
        ({"owner_principal_id": AUTOMATION}, "cannot own itself"),
        ({"credential_digest": "not-hex"}, "SHA-256"),
        ({"declared_tools": frozenset()}, "declares no tool"),
        (
            {"ceiling": EntitlementSet(principal_id="u_owner", grants=grants(READ_PRICES))},
            "held under",
        ),
        (
            {
                "ceiling": EntitlementSet(
                    principal_id=AUTOMATION, grants=grants(READ_PRICES), not_after=NOW
                )
            },
            "expiry",
        ),
    ],
)
def test_a_registration_that_could_not_run_safely_is_refused(
    overrides: dict[str, object], reason: str
) -> None:
    """Each of these is a registration that would run as nobody, reach nothing or everything,
    carry a ceiling somebody could pass off as a person's reach, or stop on a date judged at the
    wrong instant. Delete this and the first one is written by a form nobody validated."""
    good, _ = issued()
    fields: dict[str, object] = {
        "automation_id": good.automation_id,
        "owner_principal_id": good.owner_principal_id,
        "credential_digest": good.credential_digest,
        "declared_tools": good.declared_tools,
        "ceiling": good.ceiling,
    }
    fields.update(overrides)

    with pytest.raises(RegistrationError, match=reason):
        Registration(**fields)  # type: ignore[arg-type]


def test_an_automation_cannot_be_registered_to_somebody_who_is_not_live() -> None:
    """Delete this and an automation can start out awaiting an owner, refusing every call with
    nothing on the screen of the person who made it saying why."""
    with pytest.raises(RegistrationError, match="not a live principal"):
        issued(owner=person("u_leaver", not_after=LONG_AGO))


# ------------------------------------------------------------------------ the owner


def test_an_automation_whose_owner_is_live_is_running() -> None:
    """The positive sibling of the three below. Delete it and a standing that is always
    awaiting passes them."""
    registration, _ = issued()

    assert standing_of(registration, person("u_owner"), NOW) is Standing.RUNNING
    assert owner_of(registration, principals=Records(person("u_owner")), now=NOW).id == "u_owner"


@pytest.mark.parametrize(
    "records",
    [Records(), Records(person("u_owner", not_after=LONG_AGO))],
    ids=["disabled_or_deleted", "engagement_ended"],
)
def test_an_automation_whose_owner_has_gone_stops_and_waits(records: Records) -> None:
    """Item 56: an automation whose owner has gone stops and asks for a new owner. A disabled or
    deleted owner is no live principal at all; an ended engagement is a principal whose
    `not_after` has passed. Delete this and a leaver's automation runs on at whatever reach
    their grants still describe."""
    registration, _ = issued()

    assert standing_of(registration, asyncio.run(records.live_principal("u_owner")), NOW) is (
        Standing.AWAITING_OWNER
    )
    with pytest.raises(AutomationRefusedError) as refused:
        owner_of(registration, principals=records, now=NOW)
    assert refused.value.reason is AutomationRefusal.OWNER_GONE


def test_standing_asked_of_somebody_other_than_the_owner_is_a_wiring_fault() -> None:
    """Delete this and one person's automation can be judged running on another's standing."""
    registration, _ = issued()

    with pytest.raises(RegistrationError, match="owned by"):
        standing_of(registration, person("u_someone_else"), NOW)


def test_the_automations_asking_for_an_owner_are_exactly_those_whose_owner_has_gone() -> None:
    """Delete this and the list somebody adopts from either misses a stopped automation or
    offers a running one to be taken."""
    stays, _ = issued(owner=person("u_stays"), automation_id="stays")
    left, _ = issued(owner=person("u_left"), automation_id="left")
    ended, _ = issued(owner=person("u_ended"), automation_id="ended")
    records = Records(person("u_stays"), person("u_ended", not_after=LONG_AGO))

    assert awaiting_owner([stays, left, ended], principals=records, now=NOW) == ("ended", "left")


# ------------------------------------------------------------------------ the owner's reach


class Versions:
    def __init__(self) -> None:
        self.version = 1

    async def grants_version(self, principal_id: str) -> int:
        return self.version


class Store:
    def __init__(self, held: tuple[Grant, ...]) -> None:
        self.held = held
        self.loads = 0

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        self.loads += 1
        return EntitlementSet(principal_id=principal_id, grants=self.held)


class Cache:
    """A real cache, so the test proves the grants version is what retires a cached reach."""

    def __init__(self) -> None:
        self.kept: dict[str, EntitlementSet] = {}

    async def get(self, key: str) -> EntitlementSet | None:
        return self.kept.get(key)

    async def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None:
        self.kept[key] = value


def test_a_grant_revoked_from_the_owner_is_gone_from_the_automation_on_the_next_call() -> None:
    """Item 56: when the owner loses a permission, the automation loses it at the same moment.
    Revocation is the deletion of a grant, which bumps the grants version, and the reach is
    resolved per call through a cache keyed on that version. Delete this and the automation's
    reach can be served from a cache entry that predates the revocation."""
    versions, store, cache = Versions(), Store(grants(READ_PRICES)), Cache()
    owner = person("u_owner")

    before = owner_reach(owner, versions=versions, store=store, cache=cache, now=NOW)
    again = owner_reach(owner, versions=versions, store=store, cache=cache, now=NOW)
    store.held = ()
    versions.version = 2
    after = owner_reach(owner, versions=versions, store=store, cache=cache, now=NOW)

    assert before.holds(Capability(value=READ_PRICES), NOW)
    assert again.holds(Capability(value=READ_PRICES), NOW)
    assert store.loads == 2, "the second call before the revocation should have been a cache hit"
    assert not after.holds(Capability(value=READ_PRICES), NOW)


def test_an_owner_who_may_approve_does_not_lend_approval_to_an_automation() -> None:
    """The owner reads through the automation, and does not approve or administer through it.
    Asserted against `brain.gate.admission`'s own tables rather than restated, so the property is
    that the channel and assurance chosen admit reading and nothing a flow should hold. Delete
    this and a flow can approve a payment in its owner's name with nobody present."""
    owner = person("u_owner")
    store = Store(grants(READ_PRICES, "approve:invoice.amount", "admin:grant"))

    reach = owner_reach(owner, versions=Versions(), store=store, cache=Cache(), now=NOW)

    assert reach.principal_id == owner.id
    assert reach.holds(Capability(value=READ_PRICES), NOW)
    assert not reach.holds(Capability(value="approve:invoice.amount"), NOW)
    assert not reach.holds(Capability(value="admin:grant"), NOW)
    admitted = CHANNEL_VERBS[AUTOMATION_CHANNEL] & ASSURANCE_VERBS[AUTOMATION_ASSURANCE]
    assert admitted == frozenset({"read"})


def test_the_automation_channel_withholds_approve_and_admin_whatever_the_assurance() -> None:
    """The channel and the assurance are two ceilings, and each has to hold on its own. The
    assurance alone reduces an automation to reading today, so a channel that admitted approve
    and admin would change no answer until somebody raised the assurance, and then every
    automation could approve in its owner's name. Asserted against `brain.gate.admission`'s own
    table rather than against the constant. Delete this and the channel can be swapped for one
    that grants everything, with every other test here still green."""
    verbs = CHANNEL_VERBS[AUTOMATION_CHANNEL]

    assert "read" in verbs
    assert not verbs & {"approve", "admin"}


# ------------------------------------------------------------------------ adoption


def test_an_automation_awaiting_an_owner_is_adopted_and_keeps_its_credential_and_ceiling() -> None:
    """The one way out of waiting. Delete this and `adopt` can refuse everything while both
    refusals below pass."""
    registration, credential = issued()

    adopted = adopt(registration, current_owner=None, new_owner=person("u_heir"), now=NOW)

    assert adopted.owner_principal_id == "u_heir"
    assert adopted.credential_digest == registration.credential_digest
    assert adopted.ceiling == registration.ceiling
    assert verify(credential, adopted) is adopted


def test_an_automation_with_a_live_owner_is_not_adopted() -> None:
    """Delete this and anybody allowed to adopt can take a running automation from a person who
    is still here, which is a transfer neither of them saw."""
    registration, _ = issued()

    with pytest.raises(RegistrationError, match="still has a live owner"):
        adopt(registration, current_owner=person("u_owner"), new_owner=person("u_heir"), now=NOW)


def test_an_automation_is_not_adopted_by_somebody_who_is_not_live() -> None:
    """Delete this and an adoption by somebody already leaving schedules a second orphaning."""
    registration, _ = issued()

    with pytest.raises(RegistrationError, match="cannot adopt"):
        adopt(
            registration,
            current_owner=None,
            new_owner=person("u_heir", not_after=LONG_AGO),
            now=NOW,
        )
