"""The vault's policy files and its credential slots, which are documents rather than code.

Both of these fail by absence, and absence is invisible in a diff. A role whose policy file
is missing does not get a narrower policy, it gets whatever token the operator happened to
use when they loaded the rest, which in practice during first setup is root. A connector
added to the code without a slot argued about first gets its scopes decided during the hour
somebody is trying to make it work, which is the one hour in which "just give it write" is
the fastest answer.

The third property here is the one worth keeping forever: **every slot is empty**. A
credential committed into this repository is not undone by deleting it in the next commit,
because git keeps the old one. That is the failure this file exists to make loud on the
commit that introduces it rather than on the day somebody reads the history.

Read as files rather than against a running vault, deliberately. There is no OpenBao in a
unit test and standing one up would test that OpenBao works. What can be tested without one
is that the repository declares a policy for every role the code can ask as, a slot for
every connector and provider the code knows about, and nothing in either that looks like a
secret.

Task ids: M31.3.2.2, M38.4.1.3, M27.8.7
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain.ops.credentials import SLOTS
from brain.ops.limits import SOURCE_CEILINGS
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.ops.secrets import VaultRole, policy_of

REPO = Path(__file__).resolve().parents[2]
POLICIES = REPO / "ops" / "openbao" / "policies"
SLOTS_DOC = REPO / "ops" / "openbao" / "credential-slots.md"

#: Sorted here rather than inside `parametrize`, so the element type survives. Pytest types
#: its argument values as `Iterable[object]`, which pushes `object` into a lambda written
#: there and makes the attribute access mypy's problem rather than the reader's.
PROVIDERS: list[ProviderSlot] = sorted(PROVIDER_SLOTS, key=lambda slot: slot.slug)


def _policy_file(role: VaultRole) -> Path:
    """Where a role's policy lives. `browser_runner` is `browser-runner.hcl`: the enum spells
    a Python identifier and a vault policy name is conventionally hyphenated."""
    return POLICIES / f"{policy_of(role)}.hcl"


def _granted_paths(text: str) -> dict[str, list[str]]:
    """Every `path "..." { capabilities = [...] }` block in a policy, as path to capabilities.

    Parsed out of the HCL rather than substring-matched, because the thing that must be
    asserted is what a rule grants, and a rule that has been commented out still contains
    every word it did before.
    """
    live = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    found: dict[str, list[str]] = {}
    for path, caps in re.findall(
        r'path\s+"([^"]+)"\s*\{[^}]*capabilities\s*=\s*\[([^\]]*)\]', live, re.S
    ):
        found[path] = re.findall(r'"([^"]+)"', caps)
    return found


def _slot_paths() -> set[str]:
    """Every vault path named in a table row of the credential-slots document.

    A slot is declared by appearing in the table with its scopes beside it. Prose mentioning
    a path does not declare a slot, which is why this reads table rows rather than the file.
    """
    slots: set[str] = set()
    for line in SLOTS_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        first = line.split("|")[1].strip()
        match = re.fullmatch(r"`([a-z][a-z0-9_/*+-]*)`", first)
        if match:
            slots.add(match.group(1))
    return slots


# ------------------------------------------------------ a policy per role (M31.3.2.2)
@pytest.mark.parametrize("role", sorted(VaultRole, key=str))
def test_every_role_the_code_can_ask_as_has_a_policy_of_its_own(role: VaultRole) -> None:
    """Parametrised from `VaultRole` rather than from the directory listing, so a fourth role
    added to the enum arrives here already failing.

    Deleting this makes a missing policy silent. The role still exists, callers still pass
    it, and the vault answers using whatever token loaded the others, which during first
    setup is root. The failure is not a refusal, it is a role that is quietly wider than the
    file it was supposed to be narrowed by.
    """
    where = _policy_file(role)
    assert where.exists(), f"{role.value} has no policy at {where.relative_to(REPO)}"
    assert _granted_paths(where.read_text(encoding="utf-8")), (
        f"{where.name} grants nothing; a policy with no live rule is not a narrower policy"
    )


def test_the_policy_name_a_role_is_judged_against_is_the_file_the_loader_loads() -> None:
    """The loader writes each file under its basename, and the Secrets vault screen judges a token
    against `policy_of(role)`. Asserted against the directory itself, not against `policy_of`, so
    the two cannot move together. Delete this and `browser_runner` can be checked against a policy
    named with an underscore that no vault holds, and every correctly minted token reads as wrong.
    """
    loaded = {one.stem for one in POLICIES.glob("*.hcl")}
    assert {policy_of(role) for role in VaultRole} <= loaded
    assert policy_of(VaultRole.BROWSER_RUNNER) == "browser-runner"


def test_the_three_policies_are_three_different_policies() -> None:
    """One file copied to three names passes the test above and grants every role the widest
    of the three. The point of a policy per role is that they differ, and the differences are
    the whole design: the worker may renew and the browser runner may not, the browser runner
    gets no database credential, the application reads no connector's stored secret.

    Compared as parsed rules rather than as file text, so a difference that is only a comment
    does not count as a difference.
    """
    granted = {
        role.value: _granted_paths(_policy_file(role).read_text(encoding="utf-8"))
        for role in VaultRole
    }
    pairs = [(a, b) for a in granted for b in granted if a < b]
    assert pairs
    for left, right in pairs:
        assert granted[left] != granted[right], f"the {left} and {right} policies are identical"


def test_the_browser_runner_is_given_no_database_credential() -> None:
    """The narrowest policy, and the reason it is narrowest: the browser runner executes
    content it did not write, on pages it does not control. A browser process holding a
    database credential is one page-level exploit away from being a database client.

    Deleting this lets `database/creds/...` be added to that policy during a debugging
    session and stay there, because nothing else in the repository would notice.
    """
    granted = _granted_paths(_policy_file(VaultRole.BROWSER_RUNNER).read_text(encoding="utf-8"))
    offenders = [path for path in granted if path.startswith("database/")]
    assert not offenders, f"the browser runner may reach {offenders}"


def test_the_worker_reaches_named_connectors_and_never_a_wildcard() -> None:
    """The worker runs on a schedule with nobody watching. A wildcard over the connector
    credentials would make the least-watched process in the system the one that can borrow
    any source's key, which is a way to read anything with no person in the loop.

    The application has the wildcard deliberately, because a person's question can reach any
    connector they are entitled to. The difference between the two is the property, so this
    asserts both halves: widening the worker to `+` would otherwise read as consistency.
    """
    worker = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    application = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    assert "connectors/creds/+" not in worker, "the worker may borrow any connector's key"
    assert any(p.startswith("connectors/creds/") for p in worker), "the worker reaches none"
    assert "connectors/creds/+" in application


def test_the_loader_reads_the_directory_rather_than_a_list_of_names() -> None:
    """A loader naming its three files loads three files. Adding a fourth policy then needs
    two edits, one of which is in a shell script nobody opens, and the policy that does not
    get loaded is the new one. The loader is `apply-release.sh` since 2026-09-29, which every
    release's deploy runs (needs-rupash 114); `load-policies.sh`, which needed a root token, is
    gone.

    Asserted on the script because there is no vault here to load into.
    """
    loader = (REPO / "ops" / "openbao" / "apply-release.sh").read_text(encoding="utf-8")
    assert 'for file in "$HERE"/policies/*.hcl; do' in loader.splitlines(), (
        "the loader no longer globs the policy directory"
    )
    assert not (REPO / "ops" / "openbao" / "load-policies.sh").exists()


# ------------------------------------------- a slot per connector and provider (M38.4.1.3)
def _keyless() -> frozenset[str]:
    """Sources that take no key, which have a ceiling and nothing to keep: domains, whose RDAP
    records are published."""
    from brain.connectors.declaration import CredentialShape, shipped

    return frozenset(
        name
        for name, one in shipped().items()
        if one.console is not None and one.console.credential_shape is CredentialShape.NONE
    )


@pytest.mark.parametrize(
    "connector", sorted(c.name for c in SOURCE_CEILINGS if c.name not in _keyless())
)
def test_every_connector_the_code_knows_about_has_a_credential_slot(connector: str) -> None:
    """Parametrised from `SOURCE_CEILINGS`, which is the closed list of sources this system
    has measured a ceiling for. A connector in that list with no slot in the document is a
    connector whose scopes have not been argued about.

    That argument is cheap now and expensive later. Deleting this test means the scopes get
    decided during the hour somebody is trying to make the connector work, and "read and
    write, we can narrow it later" is the fastest thing to type in that hour.

    Held to the key slot the installer defines and the document's key slot table since
    2026-10-05, rather than to the prose table of leased `connectors/creds/` paths nothing reads:
    the scopes are argued in the connector's own declaration now (`scopes`), and the key slot
    table is held to them row for row by the test below.
    """
    from brain.ops.connector_slots import SLOT_SCOPES

    assert connector in SLOT_SCOPES, f"{connector} has a measured rate limit and no credential slot"
    assert SLOT_SCOPES[connector].path in _slot_paths(), (
        f"{connector} has a measured rate limit and no row in the key slot table"
    )


@pytest.mark.parametrize("slot", PROVIDERS)
def test_every_model_provider_has_a_slot_at_the_path_the_code_reads(slot: ProviderSlot) -> None:
    """The provider keys are the one category that cannot be leased, so they are read
    straight out of the vault at a path built from the slug. The document and the code have
    to name the same path or the operator fills a slot nothing reads.

    Deleting this lets the two drift, and the symptom is an unauthenticated model call at
    startup rather than an error, because a provider SDK with no key does not always refuse
    at the moment it is configured.
    """
    assert slot.path in _slot_paths(), f"{slot.slug} has no slot in credential-slots.md"
    body = SLOTS_DOC.read_text(encoding="utf-8")
    row = next(line for line in body.splitlines() if f"`{slot.path}`" in line)
    assert slot.env_var in row, (
        f"the document names a different environment variable for {slot.slug} than the code "
        f"declares; the code says {slot.env_var}"
    )


def test_no_declared_slot_holds_a_value_in_this_repository() -> None:
    """The failure worth catching forever. A credential committed here is not undone by the
    next commit deleting it, because git keeps the old one, so the only useful moment to
    catch it is the commit that adds it.

    Looks for the two shapes a filled slot takes: a `kv put` writing into a slot path, and a
    slot path followed by an assignment. Both are what somebody types when they are pasting a
    key in to test something and mean to take it out again.
    """
    slots = _slot_paths()
    assert slots, "no slots are declared at all; the document has stopped being a document"

    offenders: list[str] = []
    for path in sorted((REPO / "ops").rglob("*")):
        if not path.is_file():
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if re.search(r"\b(bao|vault)\s+kv\s+put\b", line):
                offenders.append(f"{path.relative_to(REPO)}:{number} writes a value into a slot")
                continue
            for slot in slots:
                stem = slot.rstrip("*+")
                if stem and stem in line and re.search(rf"{re.escape(stem)}\S*\s+\w+=\S", line):
                    offenders.append(f"{path.relative_to(REPO)}:{number} assigns into {slot}")
    assert not offenders, offenders


def test_the_document_says_which_scopes_were_refused_and_not_only_which_were_asked_for() -> None:
    """A table of granted scopes is a list of decisions with the reasoning thrown away. The
    column that matters six months later is the one saying what was deliberately not asked
    for, because that is the column somebody has to argue against rather than silently widen.

    Deleting this lets the refused column be dropped as redundant, and the next person adds a
    write scope without ever seeing that its absence was a decision.
    """
    header = next(
        line for line in SLOTS_DOC.read_text(encoding="utf-8").splitlines() if "| Slot |" in line
    )
    assert "NOT requested" in header, "the refused-scopes column is gone from the slot table"


# ------------------------------------------ the provider slots the application writes (M27.8.7)
def _matches(rule: str, path: str) -> bool:
    """Whether a policy path with `+` segments names `path`, as OpenBao reads `+`: one segment."""
    pattern = "/".join("[^/]+" if part == "+" else re.escape(part) for part in rule.split("/"))
    return re.fullmatch(pattern, path) is not None


def test_the_application_may_create_update_and_read_provider_keys_and_nothing_more_there() -> None:
    """Exactly two rules under the provider engine, with exactly these capabilities. Create and
    update so a key can be put in from the console and the wizard; read so start-up can load it;
    metadata read so a screen can say it is held. No delete, no list, no metadata write, which is a
    way to erase a key's history. `brain.ops.credentials` argues the grant.

    Delete this and the rule can widen to `providers/*` or gain `delete` in a debugging session,
    and nothing else in the repository reads the policy."""
    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    providers = {
        path: sorted(caps) for path, caps in granted.items() if path.startswith("providers")
    }
    assert providers == {
        "providers/data/+": ["create", "read", "update"],
        "providers/metadata/+": ["read"],
    }


def test_no_other_role_reaches_the_provider_engine() -> None:
    """The browser runner executes pages it did not write and uses no provider key at all, and
    holding write would be a way to swap the key every question is sent with. The worker's narrow
    read is `test_the_worker_reads_each_model_provider_key_by_name_and_nothing_else`'s. Delete this
    and a copy of the application's rule into another policy reads as consistency."""
    granted = _granted_paths(_policy_file(VaultRole.BROWSER_RUNNER).read_text(encoding="utf-8"))
    assert not [path for path in granted if path.startswith("providers")]


def test_the_worker_reads_each_model_provider_key_by_name_and_nothing_else() -> None:
    """M5.4.7: the worker probes providers, and a probe needs the provider's key, so it reads the
    four model slots, each named, with read alone. Never `providers/data/+`, which would also read
    the mail relay's password and every provider added from the console; never write, which would
    let a process nobody watches replace the key every question uses; never metadata or delete.
    The names are held to `PROVIDER_SLOTS`, so a slot added there and not here is a provider the
    prober silently never probes, and one here and not there is a read nothing needs.

    Delete this and the grant widens to the wildcard in a debugging session, and nothing else in
    the repository reads the policy."""
    from brain.ops.provider_keys import PROVIDER_SLOTS

    granted = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    providers = {
        path: sorted(caps) for path, caps in granted.items() if path.startswith("providers")
    }
    assert providers == {f"providers/data/{one.slug}": ["read"] for one in PROVIDER_SLOTS}
    assert "providers/data/mail_relay" not in providers
    for slot in PROVIDER_SLOTS:
        mount, _, rest = slot.path.partition("/")
        called = f"{mount}/data/{rest}"
        assert any(_matches(rule, called) for rule in providers), called


def test_every_slot_the_code_writes_is_a_path_the_application_policy_grants() -> None:
    """Held against the paths `OpenBaoVault` actually calls, built from each slot the store knows,
    rather than against the words in the policy. Delete this and a slot whose name has a second
    segment passes every unit test and is refused by the vault on the first install that uses it."""
    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    assert SLOTS
    for slot in SLOTS.values():
        mount, _, rest = slot.path.partition("/")
        for called, needed in (
            (f"{mount}/data/{rest}", "update"),
            (f"{mount}/metadata/{rest}", "read"),
        ):
            rules = [caps for rule, caps in granted.items() if _matches(rule, called)]
            assert rules, f"no rule in application.hcl names {called}"
            assert any(needed in caps for caps in rules), f"{called} is not granted {needed}"
    assert not _matches("providers/data/+", "providers/data/a/b")


# ------------------------------------------ the webhook signing secrets the application writes
def test_the_application_may_write_signing_secrets_and_read_only_their_metadata() -> None:
    """Exactly two rules under the webhooks engine. Create and update so a subscriber's secret is
    written and replaced from the console; metadata read so the screen can say it is held. No read
    of a secret: the application never signs with one, so a read here would be a standing copy of
    every subscriber's secret in the process that answers questions. `brain.ops.webhook_admin`
    argues the grant.

    Delete this and the rule gains `read` in a debugging session, and nothing else reads the policy.
    """
    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    webhooks = {path: sorted(caps) for path, caps in granted.items() if path.startswith("webhooks")}
    assert webhooks == {
        "webhooks/data/+": ["create", "update"],
        "webhooks/metadata/+": ["read"],
    }


def test_every_path_a_signing_secret_is_written_to_is_one_the_application_policy_grants() -> None:
    """Held against the path `OpenBaoVault` calls for a subscriber id at the grammar's longest,
    rather than against the words in the policy. Delete this and a subscriber id that makes two
    path segments passes every unit test and is refused by the vault on the first install."""
    from brain.ops.webhook_admin import signing_secret_path

    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    mount, _, rest = signing_secret_path("a" + "0" * 62).partition("/")
    for called, needed in (
        (f"{mount}/data/{rest}", "update"),
        (f"{mount}/metadata/{rest}", "read"),
    ):
        rules = [caps for rule, caps in granted.items() if _matches(rule, called)]
        assert rules and any(needed in caps for caps in rules), called


def test_the_static_path_rule_admits_the_signing_engine_and_still_refuses_every_leased_path() -> (
    None
):
    """The second prefix is admitted exactly: `webhooks/` and nothing that merely starts the same
    way, and every path the leasing design says is minted is still refused. Delete this and the
    prefix is widened to `webhooks`, or to everything, with `test_provider_keys` green."""
    import pytest

    from brain.ops.openbao import SIGNING_PREFIX, assert_static_path
    from brain.ops.secrets import SecretsUnavailableError

    assert SIGNING_PREFIX == "webhooks/"
    assert_static_path("webhooks/billing_bridge")
    for refused in ("webhooksx/a", "webhook/a", "connectors/creds/xero", "secret/data/webhooks/a"):
        with pytest.raises(SecretsUnavailableError):
            assert_static_path(refused)


# ---------------------------------------- the connected sources' keys the application writes
def test_the_application_may_write_connector_keys_and_read_only_their_metadata() -> None:
    """Exactly two rules under the connector key engine. Create and update so connecting a source
    from the console writes its key; metadata read so the screen can say it is held. No read of a
    key: this process runs no connector, so a read here would be a standing copy of every source's
    key in the process that talks to a model. No delete: a disconnect leaves the key and says so.
    `brain.ops.openbao.A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT` argues it.
    The same two for a consented source's refresh token (M11.8.6), kept by the console's consent
    route, one segment deeper, and for a person's own refresh token, one segment deeper again.

    Delete this and the rule gains `read` or `delete` in a debugging session, and nothing else reads
    the policy."""
    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    keys = {
        path: sorted(caps) for path, caps in granted.items() if path.startswith("connector_keys")
    }
    assert keys == {
        "connector_keys/data/+": ["create", "update"],
        "connector_keys/metadata/+": ["read"],
        "connector_keys/data/oauth_refresh/+": ["create", "update"],
        "connector_keys/metadata/oauth_refresh/+": ["read"],
        "connector_keys/data/oauth_refresh/+/+": ["create", "update"],
        "connector_keys/metadata/oauth_refresh/+/+": ["read"],
    }


def test_the_worker_reads_no_connector_key_itself_and_may_mint_only_the_run_token() -> None:
    """M31.3.2.3: the worker's own token, renewed for as long as the worker runs, reads nothing
    under the connector key engine, and may mint a child against the `connector-run` role, and
    against the `channel-send` role for a message its schedule sends (M38.3.3.4), and no other:
    never `connector-person`, so nothing it runs reads a person's own refresh token. Its one rule
    under the engine deletes a person's own slot's metadata, which erasure needs and reads nothing.
    Delete this and the direct read comes back in a debugging session, which makes the worker's
    token a standing read of every source's key again, and nothing else reads the policy."""
    granted = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    # Its one rule there removes a person's own refresh token on erasure, and reads nothing.
    keys = {
        path: sorted(caps) for path, caps in granted.items() if path.startswith("connector_keys")
    }
    assert keys == {"connector_keys/metadata/oauth_refresh/+/+": ["delete"]}
    minting = {path: sorted(caps) for path, caps in granted.items() if "token/create" in path}
    assert minting == {
        "auth/token/create/connector-run": ["create", "update"],
        "auth/token/create/channel-send": ["create", "update"],
        "auth/token/create/connector-rotate": ["create", "update"],
    }
    assert not [path for path in granted if path.startswith("auth/token/roles")]
    assert not [path for path in granted if path.startswith("providers/data/channel_")]


def test_the_send_token_policy_reads_each_channel_wires_secret_and_revokes_itself() -> None:
    """M38.3.3.4: the one policy that lets the worker read a channel's secret, carried only by a
    token minted per send. Each channel wire's slot by name and nothing else under the provider
    engine, which also holds the model keys and the mail relay's password; no renewal, no create,
    no metadata, no write. Held to `channel_wires()`, so a wire added without its slot here is a
    channel the worker cannot send on, and a slot here with no wire is a read nothing needs.

    Delete this and the policy widens to `providers/data/+` in a debugging session, and a send
    token reads every model key too."""
    from brain.channels.adapter import channel_wires
    from brain.ops.channel_lease import SEND_POLICY

    granted = _granted_paths((POLICIES / f"{SEND_POLICY}.hcl").read_text(encoding="utf-8"))
    assert {path: sorted(caps) for path, caps in granted.items()} == {
        **{f"providers/data/channel_{one.value}": ["read"] for one in channel_wires()},
        "auth/token/revoke-self": ["update"],
    }


def test_the_application_may_mint_only_the_run_token_a_question_borrows_a_key_with() -> None:
    """M11.9.2 and needs-rupash 99: a question borrows a connected source's key for one read, so
    the application may mint a child against the `connector-run` role and no other, and still reads
    nothing under the connector key engine with its own token. The key is read with the run token,
    which carries the `connector-run` policy alone and is revoked when the read ends
    (`brain.ops.live_read_run`).

    Delete this and the mint can widen to `auth/token/create` with no role, which mints a token of
    any policy this one holds, or the application's own token can gain a read of every key."""
    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    minting = {path: sorted(caps) for path, caps in granted.items() if "token/create" in path}
    assert minting == {
        "auth/token/create/connector-run": ["create", "update"],
        "auth/token/create/connector-rotate": ["create", "update"],
        "auth/token/create/connector-person": ["create", "update"],
    }
    assert not [path for path in granted if path.startswith("auth/token/roles")]
    assert "read" not in granted["connector_keys/data/+"]
    assert "read" not in granted["connector_keys/data/oauth_refresh/+"]
    assert "read" not in granted["connector_keys/data/oauth_refresh/+/+"]


def test_the_run_token_policy_reads_a_source_key_and_revokes_itself_and_nothing_more() -> None:
    """The one policy that reads a source's key, carried only by a token minted per attempt. No
    renewal, so a stuck run loses its authority at the TTL; no create, so a run token mints nothing;
    no metadata and no write. Delete this and the policy widens to the worker's old reach and the
    lease is a lease in name only."""
    from brain.ops.connector_lease import RUN_POLICY

    granted = _granted_paths((POLICIES / f"{RUN_POLICY}.hcl").read_text(encoding="utf-8"))
    assert {path: sorted(caps) for path, caps in granted.items()} == {
        "connector_keys/data/+": ["read"],
        "connector_keys/data/oauth_refresh/+": ["read"],
        "auth/token/revoke-self": ["update"],
    }


def test_the_browser_runner_never_reaches_the_connector_key_engine() -> None:
    """The worker reads a source's key because it reads the source, and the browser runner never
    reads a source. A copy of the worker's rule into its policy reads as consistency and is a way
    for a page an agent drives to reach every source's key. Delete this and nothing notices the
    copy."""
    granted = _granted_paths(_policy_file(VaultRole.BROWSER_RUNNER).read_text(encoding="utf-8"))
    assert not [path for path in granted if path.startswith("connector_keys")]


def test_every_path_a_connector_key_is_written_to_is_one_the_application_policy_grants() -> None:
    """Held against the paths `OpenBaoVault` calls for a source name at the grammar's longest,
    rather than against the words in the policy. Delete this and a source name that makes two path
    segments passes every unit test and is refused by the vault on the first install."""
    from brain.ops.credentials import connector_key_slot

    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    mount, _, rest = connector_key_slot("a" + "0" * 62).path.partition("/")
    for called, needed in (
        (f"{mount}/data/{rest}", "update"),
        (f"{mount}/metadata/{rest}", "read"),
    ):
        rules = [caps for rule, caps in granted.items() if _matches(rule, called)]
        assert rules and any(needed in caps for caps in rules), called
    assert not any(
        "read" in caps for rule, caps in granted.items() if _matches(rule, f"{mount}/data/{rest}")
    )


def test_the_static_path_rule_admits_the_connector_key_engine_and_still_refuses_every_lease() -> (
    None
):
    """The third prefix is admitted exactly: `connector_keys/` and nothing that merely starts the
    same way, and in particular not `connectors/`, which is where the leased path lives. Delete this
    and the prefix is widened to `connector`, which admits `connectors/creds/xero`."""
    import pytest

    from brain.ops.openbao import CONNECTOR_KEY_PREFIX, assert_static_path
    from brain.ops.secrets import SecretsUnavailableError

    assert CONNECTOR_KEY_PREFIX == "connector_keys/"
    assert_static_path("connector_keys/xero")
    for refused in (
        "connectors/creds/xero",
        "connector_keysx/xero",
        "connector_key/xero",
        "database/creds/brain_app",
    ):
        with pytest.raises(SecretsUnavailableError):
            assert_static_path(refused)


def test_the_application_and_the_worker_may_look_up_and_renew_their_own_token_and_no_other() -> (
    None
):
    """Explicit rather than left to the vault's default policy, which a token minted with
    `-no-default-policy` does not carry, and self only: renewing another token takes the token.
    Delete this and a policy edit can drop the renewal grant, so the token the installer minted
    lapses a month after the install with every renewal run failing as refused, or widen it to
    `auth/token/renew`, which renews any token whoever holds this one is handed."""
    for role in (VaultRole.APPLICATION, VaultRole.WORKER):
        granted = _granted_paths(_policy_file(role).read_text(encoding="utf-8"))
        # The worker's run-token mint is `test_the_worker_reads_no_connector_key_itself...`'s.
        own = {
            path: sorted(caps)
            for path, caps in granted.items()
            if path.startswith("auth/") and "token/create" not in path
        }
        assert own == {
            "auth/token/lookup-self": ["read"],
            "auth/token/renew-self": ["update"],
        }, role
    browser = _granted_paths(_policy_file(VaultRole.BROWSER_RUNNER).read_text(encoding="utf-8"))
    assert not [path for path in browser if path.startswith("auth/")]


def test_the_key_slot_table_is_the_catalogue_the_installer_defines() -> None:
    """Every `connector_keys/` row of the document is a slot `brain.ops.connector_slots` defines,
    with the same scopes, and every slot has a row. Delete this and the document drifts from the
    code again, which is how it came to name `connectors/creds/` for keys kept elsewhere."""
    from brain.ops.connector_slots import SLOT_SCOPES

    rows = {
        cells[1].strip("` "): (cells[3].strip(), cells[4].strip())
        for cells in (
            line.split("|")
            for line in SLOTS_DOC.read_text(encoding="utf-8").splitlines()
            if line.startswith("| `connector_keys/")
        )
    }
    assert rows == {
        one.path: ("; ".join(one.request), "; ".join(one.refuse)) for one in SLOT_SCOPES.values()
    }


# ------------------------------------------ the template signing key, created once (M13.8.10)
def test_the_application_may_create_and_read_the_template_key_and_never_replace_it() -> None:
    """One exact rule under the template signing engine: create, so the application mints the key
    into an empty slot, and read, so it signs and verifies with it. No update, which is what the
    vault asks for whenever a kv version 2 slot already holds a version, so nothing this token does
    can replace the key; no delete, patch or metadata, so its history cannot be erased from here
    either; and no wildcard, so no second slot beside it is writable. See
    `brain.ops.template_key.THE_TEMPLATE_KEY_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER`.

    Delete this and `update` can be added in a debugging session, and the key every signed
    version is verified with becomes one a request can replace."""
    from brain.ops.template_key import TEMPLATE_KEY_SLOT

    granted = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    template = {
        path: sorted(caps) for path, caps in granted.items() if path.startswith("template_signing")
    }
    mount, _, rest = TEMPLATE_KEY_SLOT.partition("/")
    assert template == {f"{mount}/data/{rest}": ["create", "read"]}


def test_no_other_role_reaches_the_template_signing_engine() -> None:
    """The worker, a connector run and the browser runner neither sign nor verify a template, and
    any grant there would be a second writer of a key that must have none. Delete this and a copy
    of the application's rule into another policy reads as consistency."""
    for name in ("worker", "connector-run", "browser-runner"):
        granted = _granted_paths((POLICIES / f"{name}.hcl").read_text(encoding="utf-8"))
        assert not [path for path in granted if path.startswith("template_signing")], name


# ------------------------------------------------ a consented source's refresh token (M11.8.6)
def test_the_run_token_reads_a_refresh_token_and_can_write_nothing_it_reads() -> None:
    """The read direction of `A_ROTATED_GRANT_IS_WRITTEN_BACK_BY_A_ROLE_THAT_CANNOT_READ_IT`: the
    run token reads a consented source's refresh token where the code keeps it, and no rule of its
    policy that names that slot grants anything that writes. Held against the path `OpenBaoVault`
    calls for the longest source name, not against the policy's words.

    Delete this and `update` or `patch` can join the run policy's refresh line, and a read of a
    source could then replace its consent with whatever the source's answer said."""
    from brain.ops.connector_lease import RUN_POLICY
    from brain.ops.credentials import connector_oauth_slot

    granted = _granted_paths((POLICIES / f"{RUN_POLICY}.hcl").read_text(encoding="utf-8"))
    mount, _, rest = connector_oauth_slot("a" + "0" * 62).path.partition("/")
    data = f"{mount}/data/{rest}"
    rules = [caps for rule, caps in granted.items() if _matches(rule, data)]
    assert rules and any("read" in caps for caps in rules)
    writes = {"create", "update", "patch", "delete", "sudo"}
    assert not [caps for caps in rules if writes & set(caps)]


def test_the_rotate_token_patches_a_refresh_token_and_can_read_nothing() -> None:
    """The write direction: the one policy a rotated refresh token is written back under may patch
    the refresh token's slot, which kv version 2 does without a read, and revoke itself, and
    nothing else. It cannot read the token it replaces, create a slot, or reach the slot a source's
    key is kept at, held against the paths the code calls.

    Delete this and the rotate policy can widen to `connector_keys/data/+` or gain `read` in a
    debugging session, and a token minted to write one value back reads every source's key."""
    from brain.ops.connector_lease import ROTATE_POLICY
    from brain.ops.credentials import connector_key_slot, connector_oauth_slot

    granted = _granted_paths((POLICIES / f"{ROTATE_POLICY}.hcl").read_text(encoding="utf-8"))
    assert {path: sorted(caps) for path, caps in granted.items()} == {
        "connector_keys/data/oauth_refresh/+": ["patch"],
        "connector_keys/data/oauth_refresh/+/+": ["patch"],
        "auth/token/revoke-self": ["update"],
    }
    mount, _, rest = connector_oauth_slot("a" + "0" * 62).path.partition("/")
    refresh = [caps for rule, caps in granted.items() if _matches(rule, f"{mount}/data/{rest}")]
    assert refresh == [["patch"]]
    key_mount, _, key_rest = connector_key_slot("a" + "0" * 62).path.partition("/")
    assert not [rule for rule in granted if _matches(rule, f"{key_mount}/data/{key_rest}")]


def test_the_release_defines_the_rotate_role_with_its_one_policy() -> None:
    """The role a rotation token is minted against is defined by every release's
    `apply-release.sh`, giving `connector-rotate` and nothing else, and the committed script is the
    one the module renders. Delete this and the role can be left out of `TOKEN_ROLES`, so every
    install refuses the mint and every rotating vendor's consent is lost on its first renewal."""
    from brain.deployment.vault_setup import APPLY_SCRIPT, TOKEN_ROLES, render_apply
    from brain.ops.connector_lease import ROTATE_POLICY, ROTATE_TOKEN_ROLE

    assert (ROTATE_TOKEN_ROLE, ROTATE_POLICY) in {(role, policy) for role, policy, _ in TOKEN_ROLES}
    assert (POLICIES / f"{ROTATE_POLICY}.hcl").is_file()
    script = (REPO / APPLY_SCRIPT).read_text(encoding="utf-8")
    assert script == render_apply()
    assert f"write auth/token/roles/{ROTATE_TOKEN_ROLE} allowed_policies={ROTATE_POLICY} " in script


# ------------------------------------------------- a person's own refresh token (M11.8.6)
def _person_slot_paths() -> tuple[str, str]:
    """The data and metadata paths `OpenBaoVault` calls for a person's slot at the longest name."""
    from brain.ops.credentials import connector_person_oauth_slot

    slot = connector_person_oauth_slot("a" + "0" * 62, "u_" + "x" * 126)
    mount, _, rest = slot.path.partition("/")
    return f"{mount}/data/{rest}", f"{mount}/metadata/{rest}"


def test_the_person_token_reads_a_persons_own_slot_and_nothing_a_source_keeps() -> None:
    """The one policy a person's own refresh token is read under reads a person's slot, where the
    code keeps it, and revokes itself, and nothing else: not a source's key, not a source's own
    refresh token, and no write, so a read made for a question cannot replace that person's consent.
    Held against the paths the code calls, not against the policy's words.

    Delete this and the person policy can widen to `connector_keys/data/+` in a debugging session,
    and a token minted to read one person's mailbox token reads every source's key."""
    from brain.ops.connector_lease import PERSON_POLICY
    from brain.ops.credentials import connector_key_slot, connector_oauth_slot

    granted = _granted_paths((POLICIES / f"{PERSON_POLICY}.hcl").read_text(encoding="utf-8"))
    assert {path: sorted(caps) for path, caps in granted.items()} == {
        "connector_keys/data/oauth_refresh/+/+": ["read"],
        "auth/token/revoke-self": ["update"],
    }
    data, _ = _person_slot_paths()
    assert [caps for rule, caps in granted.items() if _matches(rule, data)] == [["read"]]
    for slot in (connector_key_slot("a" + "0" * 62), connector_oauth_slot("a" + "0" * 62)):
        mount, _, rest = slot.path.partition("/")
        assert not [rule for rule in granted if _matches(rule, f"{mount}/data/{rest}")]


def test_nothing_running_with_nobody_present_can_read_a_persons_own_refresh_token() -> None:
    """The vault's half of `NOTHING_RUNNING_WITH_NOBODY_PRESENT_READS_A_PERSONS_CONSENT`: no rule of
    the run policy, which the worker's scheduled read is minted under, names a person's slot; the
    worker may not mint the person role; and its own policy reads nothing there. The sibling is the
    application, which may mint the person role, held by
    `test_the_application_may_mint_only_the_run_token_a_question_borrows_a_key_with`.

    Delete this and one more line on the run policy, or one more mint on the worker's, lets the
    scheduled read lease every person's mailbox token with nobody asking."""
    from brain.ops.connector_lease import PERSON_TOKEN_ROLE, RUN_POLICY

    data, metadata = _person_slot_paths()
    run = _granted_paths((POLICIES / f"{RUN_POLICY}.hcl").read_text(encoding="utf-8"))
    assert not [rule for rule in run if _matches(rule, data)]
    worker = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    assert f"auth/token/create/{PERSON_TOKEN_ROLE}" not in worker
    assert not [rule for rule in worker if _matches(rule, data)]
    assert [caps for rule, caps in worker.items() if _matches(rule, metadata)] == [["delete"]]
    application = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    assert f"auth/token/create/{PERSON_TOKEN_ROLE}" in application


def test_a_persons_own_token_is_kept_by_the_application_and_rotated_by_the_rotate_role() -> None:
    """The writes on a person's slot: the application creates and updates it when that person's
    consent is answered and reads only its metadata, which My workspace asks; the rotate role
    patches it and reads nothing. Held against the paths the code calls.

    Delete this and a person's consent cannot be kept on any install, or a rotated token cannot be
    written back, and every vendor that rotates its refresh tokens loses that person's consent on
    their first question."""
    from brain.ops.connector_lease import ROTATE_POLICY

    data, metadata = _person_slot_paths()
    application = _granted_paths(_policy_file(VaultRole.APPLICATION).read_text(encoding="utf-8"))
    assert [sorted(caps) for rule, caps in application.items() if _matches(rule, data)] == [
        ["create", "update"]
    ]
    assert [caps for rule, caps in application.items() if _matches(rule, metadata)] == [["read"]]
    rotate = _granted_paths((POLICIES / f"{ROTATE_POLICY}.hcl").read_text(encoding="utf-8"))
    assert [caps for rule, caps in rotate.items() if _matches(rule, data)] == [["patch"]]


def test_the_release_defines_the_person_role_with_its_one_policy() -> None:
    """The role a person's read token is minted against is defined by every release, giving
    `connector-person` and nothing else, and the committed script is the one the module renders.
    Delete this and the role can be left out of `TOKEN_ROLES`, so every install refuses the mint
    and no person's own account is ever read."""
    from brain.deployment.vault_setup import APPLY_SCRIPT, TOKEN_ROLES, render_apply
    from brain.ops.connector_lease import PERSON_POLICY, PERSON_TOKEN_ROLE

    assert (PERSON_TOKEN_ROLE, PERSON_POLICY) in {(role, policy) for role, policy, _ in TOKEN_ROLES}
    script = (REPO / APPLY_SCRIPT).read_text(encoding="utf-8")
    assert script == render_apply()
    assert f"write auth/token/roles/{PERSON_TOKEN_ROLE} allowed_policies={PERSON_POLICY} " in script
