"""The realm file, held to the claims its own header makes.

`ops/keycloak/realm-export.json` is a careful document. Its header argues for RS256 over
HS256, for a session lifespan that matches ours, for refresh-token revocation, against the
password grant, against the implicit flow, and for groups that carry roles and never
capabilities. Every one of those is a security decision and, until this file, nothing
compared any of them to the code they are supposed to agree with.

**A configuration file that argues well and is checked by nothing is a file that was right
on the day it was written.** The realm is edited by whoever is fixing a login problem at the
time, and the edits that matter here do not look dangerous: turning on the password grant to
get a script working, lengthening a session because people complain about logouts, adding a
client without pinning its algorithm. Each is one line and each undoes a paragraph.

**M1.1.1 is claimed now, and it was not before.** These tests were written first and the
leaf was left open, because the realm's own header said it had never been imported into a
running Keycloak and that one real import was the condition for calling it done. Passing a
test suite over a JSON file is not evidence that the file imports.

It has been imported since: 2026-09-06, Keycloak 26.0, an ephemeral container on a throwaway
server, with what the server stored read back and compared to what the file says. The header
of `ops/keycloak/realm-export.json` records the run and what it found.

The import earned its keep immediately. It logged three warnings that no amount of reading
would have produced, because they are a fact about how Keycloak treats a full import rather
than about the file's contents: `brain-console` referenced the `openid`, `profile` and
`email` client scopes, a full import replaces the client scope set with the one the file
declares, and the file declares only `brain-identity`. All three were silently discarded.
`test_every_client_scope_a_client_asks_for_is_defined_in_this_file` is that finding turned
into a check.

Still not claimed by anything: `ops/keycloak/setup.sh`. The import mounted this file and
started the server with `--import-realm`; it never went through kcadm, so the script's own
"has never been run" header is still accurate.

What these tests catch day to day is drift between this file and `brain.identity`, which
would otherwise be discovered as "random logouts" or as a token nobody should have accepted.

**And a token nobody could make strong, which every test here passed over.** On 2026-09-17 the
owner's staging install showed "Assurance: authenticated" to a signed-in administrator and
refused every `admin:` and `approve:` screen. `brain.identity.bearer.assurance_from` reads
`amr`, and this realm minted none: no amr mapper, and no reference value on any step of the
browser flow. The tests at the end of this file walk that join from the realm to the function
that reads it, the way the audience test walks the join to `validate_token`.

**And an Account Console that answered everybody 403.** Later the same day a person on that
install opened Keycloak's Account Console to set up a one-time code and was refused. The realm
declares its own client scope, and Keycloak's import attaches its built-in scopes to its own
clients only when a file declares none, so `account-console` minted tokens with no roles in them.
The last three tests walk that join from the realm to what the Account REST API reads.

Task ids: M1.1.1, M3.3.4
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.gate.admission import Assurance
from brain.identity.bearer import SECOND_FACTOR_METHODS, assurance_from
from brain.identity.oidc import VerifiedClaims
from brain.identity.roles import ROLE_COUNT, SCOPE_REQUIRED, Role
from brain.identity.sessions import SESSION_ABSOLUTE_MAX

REPO = Path(__file__).resolve().parents[2]
REALM_PATH = REPO / "ops" / "keycloak" / "realm-export.json"


def _realm() -> dict[str, Any]:
    # `json.loads` is typed as returning Any, and a cast here says the shape is a mapping
    # without claiming anything about its contents, which is exactly what the tests below
    # go on to check one key at a time.
    loaded: dict[str, Any] = json.loads(REALM_PATH.read_text(encoding="utf-8"))
    return loaded


def _clients() -> list[dict[str, Any]]:
    return list(_realm()["clients"])


def _group_names(groups: list[dict[str, Any]]) -> set[str]:
    """Every group name at every depth, flattened."""
    found: set[str] = set()
    for group in groups:
        found.add(group["name"])
        found |= _group_names(group.get("subGroups", []))
    return found


def _top_level_role_groups() -> dict[str, dict[str, Any]]:
    """The role groups under `/brain`, keyed by name."""
    brain = next(g for g in _realm()["groups"] if g["name"] == "brain")
    return {g["name"]: g for g in brain["subGroups"]}


# --------------------------------------------------------------- tokens and signatures
def test_the_realm_signs_with_rs256_and_every_client_is_pinned_to_it() -> None:
    """`brain.identity.oidc` refuses HS256 outright, because an HMAC-signed token is signed
    by anything holding the client secret, and the classic confusion attack presents the
    published RSA public key as that secret. Both ends agreeing means a misconfiguration
    fails at login rather than becoming an accepted token.

    Pinned per client as well as on the realm, because a client that names no algorithm
    inherits whatever the realm default becomes next. Delete this and a new client can be
    added unpinned, which is the state the confusion attack needs."""
    realm = _realm()

    assert realm["defaultSignatureAlgorithm"] == "RS256"
    for client in _clients():
        algorithm = client.get("attributes", {}).get("access.token.signed.response.alg")
        assert algorithm == "RS256", f"{client['clientId']} is not pinned to RS256: {algorithm}"


def test_a_stolen_refresh_token_is_detectable_rather_than_a_ten_hour_credential() -> None:
    """Replaying a revoked refresh token invalidates the chain, which is what makes theft
    visible. Without it a copied refresh token is a full-lifespan credential and nothing
    anywhere notices it was taken.

    `refreshTokenMaxReuse` is asserted at nought rather than merely present: any positive
    value permits the replay this setting exists to detect."""
    realm = _realm()

    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0


def test_the_realm_session_lifespan_matches_the_one_our_own_registry_enforces() -> None:
    """**Two clocks that disagree present as a bug rather than as a policy.** If the realm
    allowed longer than `SESSION_ABSOLUTE_MAX`, a refresh loop would keep a March sign-in
    alive in September on the Keycloak side while our registry refused it, and people would
    report random logouts rather than an expiry they could understand.

    Delete this and the realm can be lengthened to stop the complaints, which moves the
    disagreement rather than fixing it."""
    assert _realm()["ssoSessionMaxLifespan"] == int(SESSION_ABSOLUTE_MAX.total_seconds())


# --------------------------------------------------------------- flows that can be bypassed
@pytest.mark.parametrize("client", _clients(), ids=lambda c: str(c["clientId"]))
def test_no_client_offers_the_password_grant(client: dict[str, Any]) -> None:
    """The password grant skips the browser flow, and so skips the second factor and every
    conditional step configured in it. A flow whose checks can be avoided by asking a
    different endpoint is not a flow.

    Parametrised per client so a new one is covered the day it is added rather than the day
    somebody remembers to extend a loop."""
    assert client.get("directAccessGrantsEnabled") is False


@pytest.mark.parametrize("client", _clients(), ids=lambda c: str(c["clientId"]))
def test_no_client_offers_the_implicit_flow(client: dict[str, Any]) -> None:
    """The implicit flow puts the token in a URL fragment, which lands in browser history and
    in referrer headers. Neither is a place a credential can be withdrawn from."""
    assert client.get("implicitFlowEnabled") is False


@pytest.mark.parametrize("client", _clients(), ids=lambda c: str(c["clientId"]))
def test_every_public_client_requires_pkce_with_s256(client: dict[str, Any]) -> None:
    """A public client holds no secret, so the authorisation code is the whole credential
    between the redirect and the exchange. Without PKCE anything that can observe the code
    can spend it, and `plain` is not PKCE: the verifier travels in the clear beside the code
    it is meant to protect.

    Confidential clients are exempt rather than skipped silently, and the assertion says
    which is which, so a client that quietly becomes public is covered."""
    if not client.get("publicClient"):
        return
    method = client.get("attributes", {}).get("pkce.code.challenge.method")
    assert method == "S256", f"{client['clientId']} is public and its PKCE method is {method}"


# --------------------------------------------------------------- groups carry roles only
def test_every_platform_role_has_a_group_and_there_are_no_others() -> None:
    """The realm and `brain.identity.roles` have to name the same six things. A role with no
    group can never be granted through the directory, and a group naming no role assigns
    something the code has never heard of.

    Asserted in both directions. A one-way check passes while the realm accumulates groups
    nobody maps, and those are exactly the ones an administrator will assume mean
    something."""
    expected = {role.value.replace("_", "-") for role in Role}
    found = set(_top_level_role_groups())

    assert found == expected
    assert len(expected) == ROLE_COUNT


def test_exactly_the_roles_that_require_a_scope_have_scoped_subgroups() -> None:
    """A Department Admin with no scope is a Super Admin nobody appointed, and an Approver
    with no scope approves anything anyone asks. `SCOPE_REQUIRED` says which two those are,
    and the realm gives exactly those two a level of subgroups to carry the scope.

    Both directions again. A scoped role with no subgroups can only be granted unscoped,
    and an unscoped role that grows subgroups is offering a distinction the resolver will
    ignore, which is worse than refusing it because somebody will rely on it."""
    groups = _top_level_role_groups()
    scoped = {name for name, group in groups.items() if group.get("subGroups")}
    expected = {role.value.replace("_", "-") for role in SCOPE_REQUIRED}

    assert scoped == expected


def test_no_group_or_role_in_the_realm_names_a_capability() -> None:
    """**The claim the realm's own header makes most strongly, and the one nothing checked.**
    Groups carry roles and never capabilities. A capability named here would move the answer
    to "who can read the margin on this client" into a directory nobody in this company
    reviews, and `brain.core.entitlement` would no longer be the only place reach is decided.

    Capabilities are `verb:object` and roles are bare words, so the colon is the tell.
    Delete this and a helpful `read:price_list.cost` group appears in the directory, granted
    by whoever administers Keycloak rather than by anybody who reviewed a grant."""
    realm = _realm()
    names = _group_names(realm["groups"])
    names |= {r["name"] for r in realm.get("roles", {}).get("realm", [])}
    for client in _clients():
        names |= {r["name"] for r in client.get("defaultRoles", []) if isinstance(r, dict)}

    offenders = sorted(name for name in names if ":" in name)

    assert not offenders, f"these name capabilities rather than roles: {offenders}"


def test_every_client_scope_a_client_asks_for_is_defined_in_this_file() -> None:
    """**Written because the first real import found three that were not.**

    A full realm import replaces the client scope set with the one this file declares, so a
    client naming a scope the file does not define gets nothing. Keycloak does not refuse
    it: it logs `Referenced client scope 'profile' doesn't exist. Ignoring` and carries on,
    which means the client imports looking configured and is missing the claims somebody
    thought they had assigned.

    `brain-console` listed `openid`, `profile` and `email`. None was defined here and all
    three were discarded on import against Keycloak 26.0 on 2026-09-06. `openid` was wrong
    twice over: it is a scope value a client asks for in a request, never a client scope an
    administrator defines.

    Nothing was lost, because `brain.identity.oidc` reads exactly two claims, `groups` and
    `department`, and the `brain-identity` scope maps both. What was lost was a silent
    import, and an import that prints warnings is one where the next person cannot tell the
    harmless lines from the real ones.

    Delete this and a scope name can be added here that resolves to nothing on the server,
    which is invisible in the file and visible only in a log nobody keeps."""
    realm = _realm()
    defined = {s["name"] for s in realm.get("clientScopes", [])}

    dangling: dict[str, list[str]] = {}
    for client in _clients():
        asked = list(client.get("defaultClientScopes") or []) + list(
            client.get("optionalClientScopes") or []
        )
        missing = sorted(set(asked) - defined)
        if missing:
            dangling[str(client["clientId"])] = missing

    assert not dangling, f"these clients name client scopes this file does not define: {dangling}"


def test_the_scope_the_console_uses_maps_the_two_claims_the_code_reads() -> None:
    """The other half of the check above: the scope exists, and it carries what is consumed.

    `brain.identity.oidc` defaults `groups_claim` to "groups" and `department_claim` to
    "department". Those two claims are the whole interface between the identity provider and
    this system's permission model: groups become roles, department becomes scope. A scope
    that exists but maps neither would satisfy the dangling-reference test and still produce
    a token this system can do nothing with.

    Delete this and the mappers can be removed from the scope while every other test here
    stays green."""
    scopes = {s["name"]: s for s in _realm().get("clientScopes", [])}

    assert "brain-identity" in scopes
    mapped = {
        m.get("config", {}).get("claim.name")
        for m in scopes["brain-identity"].get("protocolMappers", [])
    }

    assert {"groups", "department"} <= mapped, f"brain-identity maps {mapped}"


def test_the_audience_the_api_demands_is_minted_into_the_console_s_own_tokens() -> None:
    """**The realm was broken here and every test passed.** `validate_token` refuses a token
    whose `aud` does not contain the expected audience, with `TokenRefusal.WRONG_AUDIENCE`.
    An `oidc-audience-mapper` is what puts it there, and where that mapper sits decides
    whether it ever runs.

    It sat in `brain-api`'s own `protocolMappers`. A dedicated mapper applies to tokens
    issued **for** that client, and `brain-api` has standardFlow, directAccess,
    serviceAccounts and implicit all disabled, because it is a resource server nobody signs
    in to. So no token was ever issued for it, the mapper could never fire, and the console's
    tokens would have carried no audience for the API at all. Every sign-in would have
    succeeded at Keycloak and then been refused by this system, which reads as "login is
    broken" and is nowhere near the file that caused it.

    The mapper's own `_comment` described exactly that failure as the thing it existed to
    prevent. It is this repository's most common defect in its purest form: correct,
    documented, and never invoked.

    The two checks either side of this one could not see it. One asserts every scope a client
    asks for is defined, and the mapper was not in a scope. The other asserts `brain-identity`
    maps groups and department, and would pass with no audience mapper anywhere in the file.
    Nothing joined the audience the code demands to the client that actually signs in.

    So this test walks the join: take the audience from the client that a person authenticates
    through, follow its default scopes, and require a mapper reached that way to mint it.
    Asserting the mapper is merely present somewhere would pass again on the day somebody
    moves it back.

    Delete this and the mapper can return to a client that mints no tokens, which is where it
    was written in the first place and looks like the obvious place for it."""
    realm = _realm()
    clients = {c["clientId"]: c for c in realm.get("clients", [])}
    scopes = {s["name"]: s for s in realm.get("clientScopes", [])}

    console = clients["brain-console"]
    assert console.get("standardFlowEnabled") is True, (
        "this test assumes the console is the client a person signs in through"
    )

    # Every mapper that can reach a token minted for the console: its own dedicated ones,
    # plus those on the scopes it carries by default. An optional scope is deliberately not
    # counted, because the console would have to ask for it and nothing here asks.
    reachable = list(console.get("protocolMappers") or [])
    for name in console.get("defaultClientScopes") or []:
        reachable.extend(scopes.get(name, {}).get("protocolMappers") or [])

    audiences = {
        m.get("config", {}).get("included.client.audience")
        for m in reachable
        if m.get("protocolMapper") == "oidc-audience-mapper"
        and m.get("config", {}).get("access.token.claim") == "true"
    }

    assert "brain-api" in audiences, (
        "no audience mapper reachable from brain-console mints aud=brain-api, so "
        f"validate_token refuses every token it issues; reachable audiences: {audiences}"
    )


def test_the_realm_is_the_one_the_application_expects() -> None:
    """A realm renamed is every issuer wrong at once, and the failure is a token rejected
    with no explanation of which end moved."""
    realm = _realm()

    assert realm["realm"] == "brain"
    assert realm["enabled"] is True


def test_brute_force_protection_is_on() -> None:
    """A sign-in page with no lockout is a password-guessing service. Cheap to leave off and
    unpleasant to discover, because nothing about it looks wrong until somebody is inside."""
    assert _realm()["bruteForceProtected"] is True


CALLBACK_PATH = "/auth/callback"
SIGNED_OUT_PATH = "/signed-out"


def test_the_console_can_actually_be_signed_in_to() -> None:
    """**The realm shipped with `.invalid` placeholders, so sign-in could not complete from
    any address, including localhost.** That was deliberate while nobody had given an address:
    Keycloak hands an authorisation code to any URI listed here, so a stale one is an open
    redirect, and a placeholder is safer than somebody else's hostname.

    An address exists now, so the placeholder is the thing that would be wrong. This asserts
    the client can be signed in to at all, which is the property the placeholders removed.

    Exact paths rather than a wildcard, because a wildcard readmits exactly the risk the
    placeholders were guarding against: `https://example.com/*` accepts a code at any path on
    that host, including one an attacker controls.

    Delete this and the realm can go back to a state where every sign-in fails at the last
    step, which reads to a user as "login is broken" and is nowhere near the file causing it."""
    console = {c["clientId"]: c for c in _realm()["clients"]}["brain-console"]
    uris = console["redirectUris"]

    assert uris, "the console has no redirect URI, so no sign-in can complete"
    for uri in uris:
        assert ".invalid" not in uri, f"{uri} is a placeholder, so sign-in cannot complete"
        assert not uri.rstrip("/").endswith("*"), (
            f"{uri} is a wildcard, and Keycloak will hand a code to any path under it"
        )
        assert uri.endswith(CALLBACK_PATH), (
            f"{uri} does not end in the path the console actually returns to"
        )

    origins = console["webOrigins"]
    assert origins, "no web origin, so the browser cannot call the API after signing in"
    for uri in uris:
        assert any(uri.startswith(origin) for origin in origins), (
            f"{uri} has no matching webOrigin, so its CORS preflight is refused"
        )


def test_every_registered_address_agrees_with_the_paths_the_console_uses() -> None:
    """The join between two files that must not drift. `console/src/auth/constants.ts` decides
    where the browser comes back to, and the realm decides where Keycloak is willing to send
    it. If they disagree the sign-in fails at the final redirect, after the person has already
    typed their password, which is the least debuggable place for it to fail.

    Read out of the TypeScript rather than repeated here, so this compares the two records
    instead of comparing the realm against a third copy of the same string.

    Delete this and either file can be edited alone."""
    import re

    source = (REPO / "console" / "src" / "auth" / "constants.ts").read_text(encoding="utf-8")
    callback = re.search(r'CALLBACK_PATH\s*=\s*"([^"]+)"', source)
    signed_out = re.search(r'SIGNED_OUT_PATH\s*=\s*"([^"]+)"', source)

    assert callback and signed_out, "the console no longer declares its own paths"
    assert callback.group(1) == CALLBACK_PATH
    assert signed_out.group(1) == SIGNED_OUT_PATH

    console = {c["clientId"]: c for c in _realm()["clients"]}["brain-console"]
    post_logout = console["attributes"]["post.logout.redirect.uris"]
    for entry in post_logout.split("##"):
        assert entry.endswith(SIGNED_OUT_PATH), (
            f"{entry} is not where the console goes after signing out"
        )


def test_every_required_action_names_the_provider_that_implements_it() -> None:
    """**The realm imported and every sign-in to it failed.** Keycloak reads `providerId` to
    find the factory for a required action and falls back to nothing when the key is absent, so
    an entry carrying only `alias` imports as a required action whose provider is null. The
    server then answers every authentication with "Unexpected error when handling authentication
    request to identity provider" and logs `Unable to find factory for Required Action 'null'`.
    Measured on a real install on 2026-09-16: the realm was healthy, the client was right, and
    nobody could sign in.

    The alias is checked against the provider deliberately: Keycloak's built-in actions use the
    same string for both, so a mismatch is a typo in one of them, and a required action nobody
    can build is indistinguishable from one nobody configured.

    Delete this and the key can go missing again, with every test about roles, groups and
    clients still green, because none of them asks whether the realm can authenticate."""
    actions = _realm()["requiredActions"]

    assert actions, "a realm with no required action asks nobody for a second factor"
    for action in actions:
        assert action.get("providerId"), action.get("alias")
        assert action["providerId"] == action["alias"], action


def test_the_realms_own_scope_mints_the_subject_every_token_is_read_for() -> None:
    """**A token with no `sub` names nobody, and `brain.identity.oidc` refuses it as a missing
    claim.** Keycloak 25 moved `sub` out of every access token into a built-in client scope
    called `basic`, so a realm whose clients name only their own scope is minted tokens
    carrying this system's claims and not the one every OIDC reader assumes. Measured on a real
    install on 2026-09-16: the realm imported, the signature and audience were right, and the
    finishing screen refused the token because there was no subject to bind.

    The mapper lives in this realm's own scope rather than the client naming Keycloak's
    built-in, and that is the whole point: a full import replaces the client scope set with the
    one this file declares, so a built-in named on a client is discarded exactly as `openid`,
    `profile` and `email` were on 2026-09-06, and the test above is what catches that. A claim
    minted here survives the import that a reference would not.

    Delete this and the mapper can be removed as looking redundant beside a built-in scope
    nobody imported, with every other realm test green and nobody able to sign in."""
    scope = next(one for one in _realm()["clientScopes"] if one["name"] == "brain-identity")
    mappers = {one["name"]: one for one in scope["protocolMappers"]}

    assert "subject" in mappers, sorted(mappers)
    assert mappers["subject"]["protocolMapper"] == "oidc-sub-mapper", mappers["subject"]
    assert mappers["subject"]["config"]["access.token.claim"] == "true", mappers["subject"]


# --------------------------------------------------------------- a second factor, in the token
#
# Keycloak 26.0.0 source, read rather than remembered: `AmrProtocolMapper` sets `amr` to
# `AmrUtils.getAuthenticationExecutionReferences`, which takes each step the person completed,
# reads that step's authenticator config, and keeps `default.reference.value` while
# `authTime + default.reference.maxAge >= now`, with an absent max age read as "0". No built-in
# client scope carries the mapper. So three things have to be true of this file at once, and
# on 2026-09-17 none of them was.

#: `Constants.AUTHENTICATION_EXECUTION_REFERENCE_VALUE` in Keycloak 26.0.0.
REFERENCE_VALUE = "default.reference.value"
#: `Constants.AUTHENTICATION_EXECUTION_REFERENCE_MAX_AGE` in Keycloak 26.0.0.
REFERENCE_MAX_AGE = "default.reference.maxAge"
#: What `AmrUtils.isAmrValid` reads an absent max age as.
MAX_AGE_WHEN_ABSENT = "0"
#: The provider ids of the two steps whose references decide assurance.
PASSWORD_FORM = "auth-username-password-form"
OTP_FORM = "auth-otp-form"
#: The flow Keycloak binds for browser sign-in when a realm names none.
DEFAULT_BROWSER_FLOW = "browser"


def _steps_a_browser_sign_in_can_reach() -> list[dict[str, Any]]:
    """Every step of the flow this realm binds for browser sign-in, subflows followed.

    A step marked DISABLED is left out, because Keycloak never runs it and a reference on it
    is never written. A flow alias this file does not declare raises here, which is the
    import's own behaviour: it looks every subflow up by alias and stops when one is missing.
    """
    realm = _realm()
    flows = {flow["alias"]: flow for flow in realm.get("authenticationFlows") or []}
    reached: list[dict[str, Any]] = []
    pending = [str(realm.get("browserFlow") or DEFAULT_BROWSER_FLOW)]
    followed: set[str] = set()
    while pending:
        alias = pending.pop()
        if alias in followed:
            continue
        followed.add(alias)
        for step in flows[alias]["authenticationExecutions"]:
            if step.get("requirement") == "DISABLED":
                continue
            if step.get("authenticatorFlow"):
                pending.append(step["flowAlias"])
            else:
                reached.append(step)
    return reached


def _method_reference(authenticator: str) -> dict[str, str]:
    """The authenticator config on the one reachable step `authenticator` names."""
    steps = [s for s in _steps_a_browser_sign_in_can_reach() if s["authenticator"] == authenticator]
    assert len(steps) == 1, f"a browser sign-in reaches {len(steps)} {authenticator} steps"
    alias = steps[0].get("authenticatorConfig")
    assert alias, f"the {authenticator} step names no authenticator config, so amr never names it"
    configs = {one["alias"]: one for one in _realm().get("authenticatorConfig") or []}
    assert alias in configs, f"the {authenticator} step names {alias!r}, which is not declared"
    config: dict[str, str] = configs[alias]["config"]
    return config


def _claims_naming(methods: list[str]) -> VerifiedClaims:
    """A token as `validate_token` hands it over, whose `amr` is exactly `methods`.

    The year 2999 because nothing here is about the present, and `assurance_from` reads no date.
    """
    issued = datetime(2999, 1, 1, tzinfo=UTC)
    return VerifiedClaims(
        issuer="https://id.example.test/realms/brain",
        subject="u_probe",
        audience=("brain-api",),
        issued_at=issued,
        expires_at=issued + timedelta(minutes=5),
        session_id="s_probe",
        key_id="k_probe",
        algorithm="RS256",
        verified_at=issued,
        claims={"sub": "u_probe", "amr": methods},
    )


def test_the_console_s_own_tokens_carry_the_methods_its_sign_in_used() -> None:
    """**Without this mapper no token this realm mints has an `amr` at all**, and
    `assurance_from` reads a token with no `amr` as AUTHENTICATED. That is the staging finding:
    a person who had set up OTP, signed in with it, and was refused every admin screen.

    Walked from the client a person signs in through, across its default scopes, for the reason
    the audience test above gives: a mapper merely present somewhere in this file would pass on
    the day it sits on a client that mints no tokens. `access.token.claim` is asserted as the
    string "true" because Keycloak 26.0's `includeInAccessToken` is `"true".equals(value)`, so an
    absent key is off, and the access token is the one the console sends.

    Delete this and the mapper can be removed or pointed at the ID token, with every reference
    below intact and every administrator refused again."""
    realm = _realm()
    clients = {c["clientId"]: c for c in realm["clients"]}
    scopes = {s["name"]: s for s in realm.get("clientScopes") or []}
    console = clients["brain-console"]
    assert console.get("standardFlowEnabled") is True, "the console is the client people sign in to"

    reachable = list(console.get("protocolMappers") or [])
    for name in console.get("defaultClientScopes") or []:
        reachable.extend(scopes.get(name, {}).get("protocolMappers") or [])

    minting = [
        m
        for m in reachable
        if m.get("protocolMapper") == "oidc-amr-mapper"
        and m.get("config", {}).get("access.token.claim") == "true"
    ]

    assert minting, "no amr mapper reachable from brain-console writes into its access tokens"


def test_passing_the_one_time_code_step_earns_a_second_factor_the_api_recognises() -> None:
    """**The positive half, and the one that was missing.** The OTP form on the flow this realm
    binds for browser sign-in names a method `brain.identity.bearer` counts, so a sign-in that
    passed it is STRONG. Tied to the code rather than to a literal: the reference is asserted
    to be a member of `SECOND_FACTOR_METHODS`, and a token carrying the realm's own two
    references is handed to `assurance_from`, so neither side can be edited alone.

    The walk starts at the realm's browser binding and skips DISABLED steps, so a reference on
    a flow nobody signs in through, or behind a disabled OTP subflow, fails here rather than
    importing as a realm where a second factor can never be presented.

    Delete this and the OTP step's reference can drift to a value the API has never heard of,
    which is exactly as silent as having none."""
    otp = _method_reference(OTP_FORM).get(REFERENCE_VALUE, "")
    password = _method_reference(PASSWORD_FORM).get(REFERENCE_VALUE, "")

    assert otp in SECOND_FACTOR_METHODS, f"the OTP step writes {otp!r}"
    assert assurance_from(_claims_naming([password, otp])) is Assurance.STRONG


def test_a_password_alone_earns_no_second_factor() -> None:
    """**The negative half, without which the test above is satisfied by a realm that calls
    everything a second factor.** The password form's reference is written, so a
    password-only token says what it is, and it is not a member of `SECOND_FACTOR_METHODS`,
    so that token stays AUTHENTICATED and cannot exercise an `admin:` or `approve:` capability.

    Written at all, rather than left off, because a password-only token and one from a realm
    whose amr mapper never ran would otherwise both carry an empty `amr`, and decoding a token is
    the one diagnostic an administrator has.

    Delete this and the password step can be given `mfa`, which promotes every sign-in in the
    company with no second factor presented, silently and in the permissive direction."""
    password = _method_reference(PASSWORD_FORM).get(REFERENCE_VALUE, "")

    assert password, "the password step writes no reference, so a password-only token says nothing"
    assert password not in SECOND_FACTOR_METHODS, f"the password step writes {password!r}"
    assert assurance_from(_claims_naming([password])) is Assurance.AUTHENTICATED


@pytest.mark.parametrize("authenticator", [PASSWORD_FORM, OTP_FORM])
def test_a_method_reference_counts_for_the_whole_session_it_was_earned_in(
    authenticator: str,
) -> None:
    """**A reference with no max age is gone before the first token.** Keycloak 26.0.0's
    `AmrUtils.isAmrValid` keeps it only while `authTime + maxAge >= now`, and reads an absent
    max age as 0, so the code exchange a second after the OTP form already mints a token
    without `otp`. Shorter than the session is the quieter version of the same fault: the
    administrator is STRONG until a refresh past the max age, then refused mid-task.

    Asserted as at least `SESSION_ABSOLUTE_MAX`, the policy the realm's own
    `ssoSessionMaxLifespan` is held to above, because the second factor is a claim about the
    session (`A_SECOND_FACTOR_IS_A_CLAIM_ABOUT_THIS_SESSION`) and the session cannot outlive it.

    Delete this and the max age can be dropped as looking optional, which it is in the admin
    console, with every other test here green and no strong token ever minted."""
    max_age = int(_method_reference(authenticator).get(REFERENCE_MAX_AGE, MAX_AGE_WHEN_ABSENT))

    assert max_age >= SESSION_ABSOLUTE_MAX.total_seconds(), (
        f"the {authenticator} reference lasts {max_age}s of a "
        f"{SESSION_ABSOLUTE_MAX.total_seconds():.0f}s session"
    )


def test_every_config_and_subflow_a_declared_flow_names_is_declared_in_this_file() -> None:
    """**A flow naming something this file does not declare stops the whole import.** Keycloak
    26.0.0's `DefaultExportImportManager` resolves every step's `authenticatorConfig` and
    `flowAlias` by alias as it imports the declared flows, and calls `getId()` on what it finds;
    only afterwards does `migrateFlows` build the built-in flows this file leaves out. So a
    built-in name cannot satisfy a reference here, and a missing one leaves Keycloak running
    with no realm, which every sign-in reports as nothing in particular.

    Both kinds of step are checked for shape too: a subflow step names a flow and no
    authenticator, and an authenticator step names an authenticator.

    Delete this and one renamed alias ships a realm that does not import, with the tests that
    read the file as JSON all green."""
    realm = _realm()
    flow_aliases = [flow["alias"] for flow in realm.get("authenticationFlows") or []]
    config_aliases = [one["alias"] for one in realm.get("authenticatorConfig") or []]
    assert len(set(flow_aliases)) == len(flow_aliases), f"a flow alias repeats: {flow_aliases}"
    assert len(set(config_aliases)) == len(config_aliases), f"a config repeats: {config_aliases}"

    dangling: list[str] = []
    for flow in realm.get("authenticationFlows") or []:
        for step in flow["authenticationExecutions"]:
            if step.get("authenticatorFlow"):
                assert not step.get("authenticator"), f"{flow['alias']}: {step}"
                if step.get("flowAlias") not in flow_aliases:
                    dangling.append(f"{flow['alias']} -> flow {step.get('flowAlias')!r}")
            else:
                assert step.get("authenticator"), f"{flow['alias']}: {step}"
                named = step.get("authenticatorConfig")
                if named is not None and named not in config_aliases:
                    dangling.append(f"{flow['alias']} -> config {named!r}")

    assert not dangling, f"these names are not declared in this file: {dangling}"


# --------------------------------------------------------------- the account console
#
# Keycloak 26.0.0 source, read rather than remembered. `AccountLoader.getAccountRestService`
# refuses a token whose `aud` lacks the `account` client (401), and `AccountRestService.account`
# then calls `auth.requireOneOf(MANAGE_ACCOUNT, VIEW_PROFILE)`, which `Auth.hasClientRole` answers
# from the token's `resource_access.account.roles` and nothing else (403).
# `RealmManager.importRealm` builds the built-in client scopes, `roles` among them, and attaches
# them to the clients that already exist only `if (rep.getClientScopes() == null)`; this realm
# declares one, so the `account-console` it builds carries only the audience mapper
# `setupAccountManagement` puts on the client itself. That is a 403 rather than a 401, which is
# what staging showed.

#: `Constants.ACCOUNT_MANAGEMENT_CLIENT_ID`: the Account REST API is this client, and it demands
#: this name in `aud` and in `resource_access`.
ACCOUNT_CLIENT = "account"
#: `Constants.ACCOUNT_CONSOLE_CLIENT_ID`: the client `AccountConsole` signs a person in as.
ACCOUNT_CONSOLE = "account-console"
#: Keycloak's own clients that this file declares. Every other declared client is the product's.
KEYCLOAKS_OWN_CLIENTS = frozenset({ACCOUNT_CLIENT, ACCOUNT_CONSOLE})
#: What `AccountRestService.account`, the first call the console makes, accepts one of.
ROLES_THE_ACCOUNT_API_ACCEPTS = frozenset({"manage-account", "view-profile"})
#: `ProtocolMapperUtils.USER_MODEL_CLIENT_ROLE_MAPPING_CLIENT_ID`.
CLIENT_ROLE_MAPPING_CLIENT_ID = "usermodel.clientRoleMapping.clientId"
#: Mappers that write a person's roles, or an audience worked out from those roles, into a token:
#: the three the built-in `roles` scope carries (`OIDCLoginProtocolFactory.addRolesClientScope`).
ROLE_WRITING_MAPPERS = frozenset(
    {
        "oidc-usermodel-client-role-mapper",
        "oidc-usermodel-realm-role-mapper",
        "oidc-audience-resolve-mapper",
    }
)


def _mappers_minting_for(client: dict[str, Any], realm: dict[str, Any]) -> list[dict[str, Any]]:
    """Every mapper that runs when Keycloak mints an access token for `client`, as imported.

    `TokenManager.getRequestedClientScopes` is the client's default scopes plus the client itself,
    so a client's own mappers count and run for its tokens alone. Its default scopes are the ones
    it names when it names any, default or optional (`RepresentationToModel.updateClientScopes`
    removes the rest). A client that names none is given the realm's default scopes when its
    protocol is set (`AbstractLoginProtocolFactory.addDefaultClientScopes`), which in this file
    means `defaultDefaultClientScopes`. Optional scopes are left out: a token carries one only when
    the sign-in asks for it by name. A mapper whose protocol is not the client's never runs
    (`DefaultClientSessionContext.loadProtocolMappers`).
    """
    scopes = {one["name"]: one for one in realm.get("clientScopes") or []}
    if (
        client.get("defaultClientScopes") is not None
        or client.get("optionalClientScopes") is not None
    ):
        named = client.get("defaultClientScopes") or []
    else:
        named = realm.get("defaultDefaultClientScopes") or []
    mappers = list(client.get("protocolMappers") or [])
    for name in named:
        mappers.extend(scopes.get(name, {}).get("protocolMappers") or [])
    protocol = client.get("protocol", "openid-connect")
    return [one for one in mappers if one.get("protocol") == protocol]


def _account_roles(realm: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        one["name"]: one
        for one in realm.get("roles", {}).get("client", {}).get(ACCOUNT_CLIENT) or []
    }


def _with_contained(names: set[str], realm: dict[str, Any]) -> set[str]:
    """`names` and every account role they contain, followed to the end, as Keycloak expands."""
    declared = _account_roles(realm)
    found: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        composites = declared.get(name, {}).get("composites", {})
        pending.extend(composites.get("client", {}).get(ACCOUNT_CLIENT) or [])
    return found


def _account_roles_everybody_holds(realm: dict[str, Any]) -> set[str]:
    """The account roles the realm's default role contains, as the import names that role.

    `RealmManager.importRealm` takes the name from `defaultRole` when the file has one. Otherwise
    it is `default-roles-<realm>`, stepped to `-1`, `-2` while a declared realm role already has
    it (`determineDefaultRoleName`), so the composites declared under the plain name then sit on an
    ordinary role nobody is given.
    """
    declared = {one["name"]: one for one in realm.get("roles", {}).get("realm") or []}
    name = (realm.get("defaultRole") or {}).get("name")
    if name is None:
        base = f"default-roles-{str(realm['realm']).lower()}"
        name, step = base, 0
        while name in declared:
            step += 1
            name = f"{base}-{step}"
    composites = declared.get(name, {}).get("composites", {})
    return _with_contained(set(composites.get("client", {}).get(ACCOUNT_CLIENT) or []), realm)


def test_the_account_console_s_tokens_carry_the_roles_and_audience_the_account_api_checks() -> None:
    """**The staging finding: the Account Console loaded and every call it made answered 403**, so
    nobody could set up a one-time code there and the admin screens stayed shut to them.

    Three joins, each walked from the realm rather than asserted as present somewhere:

    - a client roles mapper that runs for `account-console` writes `resource_access.account.roles`
      into the access token, as a list. `includeInAccessToken` is `"true".equals(value)`, and a
      mapper that is not `multivalued` writes one string, which `AbstractUserRoleMappingMapper`
      does not turn into roles;
    - an audience for `account` reaches the same token, from Keycloak's audience resolve mapper
      (on unless its access token flag is `"false"`) or an audience mapper naming it;
    - a role the API accepts is both held by everybody through the default role and inside what
      `account-console` may carry: `TokenManager.getAccess` keeps the expanded intersection of the
      two when `fullScopeAllowed` is false, and `RoleResolveUtil` feeds both mappers from it.

    Delete this and the mapper, its scope mapping or the default role can go, with the realm
    importing cleanly and the Account Console refusing everybody again."""
    realm = _realm()
    console = {c["clientId"]: c for c in realm["clients"]}.get(ACCOUNT_CONSOLE)
    if console is None:
        # Left to the import, which gives Keycloak's own clients Keycloak's own scopes only when
        # the file declares none (`AbstractLoginProtocolFactory.createDefaultClientScopes`).
        assert realm.get("clientScopes") is None, (
            f"{ACCOUNT_CONSOLE} is left to the import, which attaches no scope to it because "
            "this file declares clientScopes, so its tokens carry no account roles"
        )
        return
    minting = _mappers_minting_for(console, realm)

    claims: set[str] = set()
    for mapper in minting:
        config = mapper.get("config") or {}
        narrowed_to = config.get(CLIENT_ROLE_MAPPING_CLIENT_ID)
        if (
            mapper.get("protocolMapper") == "oidc-usermodel-client-role-mapper"
            and config.get("access.token.claim") == "true"
            and config.get("multivalued") == "true"
            and narrowed_to in (None, "", ACCOUNT_CLIENT)
        ):
            claims.add(str(config.get("claim.name")).replace("${client_id}", ACCOUNT_CLIENT))
    assert f"resource_access.{ACCOUNT_CLIENT}.roles" in claims, (
        f"no mapper running for {ACCOUNT_CONSOLE} writes the account roles as a list: {claims}"
    )

    audiences = [
        mapper
        for mapper in minting
        if (
            mapper.get("protocolMapper") == "oidc-audience-resolve-mapper"
            and (mapper.get("config") or {}).get("access.token.claim", "true") == "true"
        )
        or (
            mapper.get("protocolMapper") == "oidc-audience-mapper"
            and (mapper.get("config") or {}).get("included.client.audience") == ACCOUNT_CLIENT
            and (mapper.get("config") or {}).get("access.token.claim") == "true"
        )
    ]
    assert audiences, f"nothing running for {ACCOUNT_CONSOLE} puts {ACCOUNT_CLIENT} in aud"

    held = _account_roles_everybody_holds(realm)
    if console.get("fullScopeAllowed", not console.get("consentRequired", False)):
        allowed = set(_account_roles(realm))
    else:
        mapped: set[str] = set()
        for mapping in realm.get("clientScopeMappings", {}).get(ACCOUNT_CLIENT) or []:
            if mapping.get("client") == ACCOUNT_CONSOLE:
                mapped |= set(mapping.get("roles") or [])
        allowed = _with_contained(mapped, realm)
    carried = held & allowed

    assert carried & ROLES_THE_ACCOUNT_API_ACCEPTS, (
        f"everybody holds {sorted(held)}, {ACCOUNT_CONSOLE} may carry {sorted(allowed)}, and the "
        f"API accepts only {sorted(ROLES_THE_ACCOUNT_API_ACCEPTS)}"
    )


def test_no_client_of_the_product_s_own_reaches_a_mapper_that_writes_roles_into_its_tokens() -> (
    None
):
    """**The other half: the repair gave the Account Console roles and gave nobody else anything.**
    `brain.identity` reads groups and department and never a Keycloak role, so a role claim in a
    product token is a claim nothing asked for, and an audience worked out from roles is an `aud`
    this system's `validate_token` was never written to expect.

    Walked with the same function as the test above, realm default scopes included, so the likely
    wrong fix is covered: declaring a `roles` scope as a realm default so that the Account Console
    gets it would hand it to every product client that names no scope of its own. And the walk is
    shown to reach something, so an empty walk cannot pass: `brain-console` reaches its own
    subject mapper through it.

    Delete this and the account roles mapper can be moved onto `brain-identity`, where it would
    run for every console token, with every other test here green."""
    realm = _realm()
    product = [c for c in realm["clients"] if c["clientId"] not in KEYCLOAKS_OWN_CLIENTS]
    assert {"brain-console", "brain-api", "brain-sync"} <= {c["clientId"] for c in product}

    widened = {
        client["clientId"]: sorted(
            str(m.get("name"))
            for m in _mappers_minting_for(client, realm)
            if m.get("protocolMapper") in ROLE_WRITING_MAPPERS
        )
        for client in product
    }
    assert not any(widened.values()), f"product clients reach role mappers: {widened}"

    console = next(c for c in product if c["clientId"] == "brain-console")
    assert "oidc-sub-mapper" in {
        m.get("protocolMapper") for m in _mappers_minting_for(console, realm)
    }


def test_the_account_client_and_its_console_are_declared_together_with_every_role_they_name() -> (
    None
):
    """**A realm that gets any of this wrong does not import, and says so nowhere a person looks.**

    - `RealmManager.importRealm` builds `account` and `account-console` itself unless the file
      names `account`. Naming `account-console` alone adds it a second time, and the client table
      is unique on realm and clientId (`ClientEntity`). Naming `account` alone leaves no console.
    - `RepresentationToModel.addComposites` throws for an account role a composite names that is
      not declared, and `createClientScopeMappings` quietly creates a bare role for one a scope
      mapping names, so a misspelling there maps a role nobody holds.
    - The default role's composites are declared under the name `defaultRole` gives it, because
      without `defaultRole` the import steps the default role's name past the declared one.

    Delete this and one renamed client or role ships a realm that stops at import, or imports with
    the Account Console refusing everybody, and the tests that read the file as JSON stay green."""
    realm = _realm()
    ids = [c["clientId"] for c in realm["clients"]]
    assert (ACCOUNT_CLIENT in ids) == (ACCOUNT_CONSOLE in ids), ids
    assert len(set(ids)) == len(ids), f"a client is declared twice: {ids}"
    if ACCOUNT_CONSOLE not in ids:
        return

    declared = set(_account_roles(realm))
    named: list[str] = []
    for role in realm.get("roles", {}).get("realm") or []:
        named.extend(role.get("composites", {}).get("client", {}).get(ACCOUNT_CLIENT) or [])
    for role in _account_roles(realm).values():
        named.extend(role.get("composites", {}).get("client", {}).get(ACCOUNT_CLIENT) or [])
    for mapping in realm.get("clientScopeMappings", {}).get(ACCOUNT_CLIENT) or []:
        assert mapping.get("client") in ids, mapping
        named.extend(mapping.get("roles") or [])
    assert set(named) <= declared, f"account roles named and not declared: {set(named) - declared}"

    default_role = (realm.get("defaultRole") or {}).get("name")
    carrying = [
        role["name"]
        for role in realm.get("roles", {}).get("realm") or []
        if role.get("composites", {}).get("client", {}).get(ACCOUNT_CLIENT)
    ]
    assert carrying == [default_role], (
        f"the account roles everybody holds are declared on {carrying}, and the default role is "
        f"{default_role!r}"
    )
