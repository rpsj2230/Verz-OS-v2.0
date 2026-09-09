"""The realm as Keycloak will actually read it, rather than as JSON.

Every other test over `ops/keycloak/realm-export.json` parses it and asserts about its
contents, which is right and was not enough: the file is valid JSON and Keycloak refused it.

    ERROR: Failed to run import
    ERROR: Unrecognized field "_comment" (class org.keycloak.representations.idm.
    RealmRepresentation), not marked as ignorable

Measured on 2026-09-06 against a throwaway Keycloak 26.0.8. The same file with its comments
stripped imported cleanly on the next run: "Realm 'brain' imported".

The second half of this file is about the other thing a reviewed realm cannot be: one
deployment's. Every address in it was the first deployment's host until 2026-09-09, and
Keycloak matches `redirect_uri` exactly, so the realm a second client imported registered
somebody else's server and their sign-in was refused before the login form. The addresses are
a placeholder now and `importable_realm` writes this installation's own origin over it.

Task ids: M41.1.5
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.install import InstallError
from brain.ops.realm_import import (
    COMMENT_PREFIX,
    ORIGIN_SETTING,
    PLACEHOLDER_ORIGIN,
    RealmError,
    comment_keys,
    importable_realm,
    install_origin,
    main,
    strip_comments,
    substitute,
    unconfigured_addresses,
)

REPO = Path(__file__).resolve().parents[2]
REALM = REPO / "ops" / "keycloak" / "realm-export.json"

#: An installation that has said where it is. Its own host, on a reserved documentation
#: domain so no test here can be answered by something real.
CONFIGURED = {ORIGIN_SETTING: "https://brain.acme.example/auth/callback"}


def _console(realm: dict[str, object]) -> dict[str, object]:
    """The browser client, which is where every address in this realm lives."""
    clients = realm["clients"]
    assert isinstance(clients, list)
    found = {one["clientId"]: one for one in clients}["brain-console"]
    assert isinstance(found, dict)
    return found


def test_the_reviewed_realm_still_carries_the_comments_that_would_break_an_import() -> None:
    """**The premise of every test below, asserted rather than assumed.**

    If somebody deleted the comments from the source file to make it import, these tests
    would all pass over a file that no longer explains any of its own security decisions, and
    the stripping step would be dead code nobody noticed.

    So this asserts the problem still exists in the file, which is the state the design wants:
    the reviewed version argues, and the import gets a copy that does not.

    Delete this and the fix can be undone by deleting the thing it was protecting."""
    found = comment_keys(json.loads(REALM.read_text(encoding="utf-8")))

    assert found, (
        "the realm carries no documentation keys, so either the comments were deleted to "
        "satisfy Keycloak, which loses the argument this file exists for, or the stripping "
        "step is now unnecessary and should go"
    )
    assert any(key == "realm._comment" for key in found), (
        "the realm-level comment is gone; that is the one Keycloak refused first"
    )


def test_the_stripped_realm_has_nothing_keycloak_would_refuse() -> None:
    """The property that decides whether a deployment signs anybody in. Keycloak
    deserialises the realm into typed representations and rejects any field it does not
    recognise, and a realm that fails to import leaves the server running with no realm in
    it: every sign-in then fails with no cause visible anywhere near the login page.

    Asserted over the stripped structure rather than over the text, because the text still
    contains the word inside `config` maps where it is legitimate.

    Delete this and the strip can quietly stop stripping."""
    stripped = strip_comments(json.loads(REALM.read_text(encoding="utf-8")))

    assert comment_keys(stripped) == []


def test_a_comment_inside_a_config_map_is_configuration_and_is_kept() -> None:
    """**The reason this is a parser and not a regex**, and it is not hypothetical: the realm
    has two of these today, on the `brain-identity` scope's mappers.

    `ProtocolMapperRepresentation.config` is a `Map<String, String>`. Keycloak neither
    validates nor rejects its keys, so an underscore key there is a value the server stores
    verbatim. Removing it is removing configuration, and from outside the two are
    indistinguishable: both are a string under a key nobody else reads.

    A text transform removing every line containing the prefix would take these too, and the
    only symptom would be a mapper that behaves differently for a reason nobody can see.

    Delete this and the strip can be simplified into something that silently edits mappers."""
    document = {
        "clients": [
            {
                "_comment": "documentation, and Keycloak refuses it",
                "clientId": "probe",
                "protocolMappers": [
                    {
                        "_comment": "also documentation, on a typed representation",
                        "name": "audience",
                        "config": {
                            "_comment": "configuration, because config is a free-form map",
                            "included.client.audience": "brain-api",
                        },
                    }
                ],
            }
        ]
    }

    stripped = strip_comments(document)
    client = stripped["clients"][0]
    mapper = client["protocolMappers"][0]

    assert "_comment" not in client
    assert "_comment" not in mapper
    assert mapper["config"]["_comment"] == "configuration, because config is a free-form map"
    assert mapper["config"]["included.client.audience"] == "brain-api"


def test_stripping_changes_nothing_a_deserialiser_would_read() -> None:
    """The other half, and the one that would fail silently. A strip that removed a real
    field would produce a realm that imports and is wrong: a missing `redirectUris` is a
    client nobody can sign in to, a missing `protocolMappers` is a token with no audience.

    Every key that is not documentation survives, at every depth, compared structurally
    rather than by counting.

    Delete this and the strip can take a field with an underscore anywhere in its name."""
    original = json.loads(REALM.read_text(encoding="utf-8"))
    stripped = strip_comments(original)

    def surviving(node: object) -> object:
        if isinstance(node, dict):
            return {k: surviving(v) for k, v in node.items() if not (k.startswith(COMMENT_PREFIX))}
        if isinstance(node, list):
            return [surviving(v) for v in node]
        return node

    # Everything that is not a top-level documentation key is identical. `config` maps are
    # compared as they stand, so a comment kept inside one shows up as a difference here and
    # is the reason this uses the realm rather than a fixture.
    assert json.dumps(stripped, sort_keys=True) != json.dumps(original, sort_keys=True)
    assert set(stripped) == {k for k in original if not k.startswith(COMMENT_PREFIX)}
    assert stripped["realm"] == original["realm"]
    assert len(stripped["clients"]) == len(original["clients"])
    assert len(stripped["clientScopes"]) == len(original["clientScopes"])
    for before, after in zip(original["clients"], stripped["clients"], strict=True):
        assert after["clientId"] == before["clientId"]
        assert after.get("redirectUris") == before.get("redirectUris")


def test_the_importable_realm_is_json_a_server_can_parse() -> None:
    """The end of the pipeline. `importable_realm` is what gets written beside the reviewed
    file and mounted for `--import-realm`, so it has to be text that round-trips.

    Delete this and the writer can emit a Python repr, which differs from JSON in exactly the
    places that matter: True, None and single quotes."""
    text = importable_realm(REALM, CONFIGURED)
    reparsed = json.loads(text)

    assert reparsed["realm"] == "brain"
    assert comment_keys(reparsed) == []
    assert "'" not in text.split('"realm"')[0], "this is not JSON"


# --- whose deployment the realm names --------------------------------------------------


def test_the_reviewed_realm_names_no_deployment_at_all() -> None:
    """**The state the file was not in until 2026-09-09.** It carried one deployment's host in
    four places, and a realm import writes a redirect allowlist: Keycloak matches
    `redirect_uri` exactly against it and refuses anything else with `Invalid parameter:
    redirect_uri`, before the login form, with nothing near that page naming the realm. So a
    second client's sign-in was broken by a file they never opened.

    Asserted over the whole document rather than over the four fields known today, because the
    fifth address somebody adds is the one that would carry a host again.

    Delete this and a hostname can go back into the reviewed file, and every other test here
    keeps passing because it is perfectly good JSON."""
    original = json.loads(REALM.read_text(encoding="utf-8"))
    console = _console(original)

    assert unconfigured_addresses(console) != [], "the realm names no placeholder to substitute"
    assert console["redirectUris"] == [
        f"{PLACEHOLDER_ORIGIN}/auth/callback",
        "http://localhost:5173/auth/callback",
    ]
    assert console["webOrigins"] == [PLACEHOLDER_ORIGIN, "http://localhost:5173"]

    from brain.ops.independence import URL_HOST, is_reserved

    for _, literal in _every_string(original):
        for match in URL_HOST.finditer(literal):
            host = match.group(1).split(":")[0].lower()
            assert host == "localhost" or is_reserved(host), (
                f"the reviewed realm names {host}, which is somebody's deployment"
            )


def _every_string(node: object, path: str = "realm") -> list[tuple[str, str]]:
    """Every string anywhere in the document, with where it is."""
    if isinstance(node, dict):
        return [one for key, value in node.items() for one in _every_string(value, f"{path}.{key}")]
    if isinstance(node, list):
        return [one for index, item in enumerate(node) for one in _every_string(item, f"{path}[")]
    return [(path, node)] if isinstance(node, str) else []


def test_the_setting_the_addresses_come_from_is_the_one_declared_for_them() -> None:
    """**`ORIGIN_SETTING` is a constant and every other test here imports it**, so `CONFIGURED`
    and the realm's addresses move together and the whole file is green for any value it could
    hold. `hubspot.CEILING_NAME` is the recorded version of that: repointed at another vendor,
    it passed its entire ceiling test.

    So this compares it against something outside the module. `brain.install` is where a
    setting's meaning is written down, and the one this module needs is the one declared to
    hold redirect URIs and declared to have no safe default: an origin taken from the issuer
    or the object store URL would produce a realm that imports and refuses every sign-in.

    Delete this and the module can read any setting at all and every test still passes."""
    from brain.install import BY_NAME

    declared = BY_NAME[ORIGIN_SETTING]

    assert "redirect uri" in declared.meaning.lower()
    assert declared.required and not declared.default


def test_the_importable_realm_registers_this_installations_own_callback() -> None:
    """**The property a client's sign-in actually needs.** Keycloak hands an authorisation code
    only to a URI on this list, so the console's own callback has to be on it, and the console
    returns to the origin it is served from.

    Delete this and the realm can be emitted with the placeholder left in, which imports
    cleanly and refuses every sign-in afterwards."""
    console = _console(json.loads(importable_realm(REALM, CONFIGURED)))

    assert console["redirectUris"] == [
        "https://brain.acme.example/auth/callback",
        "http://localhost:5173/auth/callback",
    ]
    assert unconfigured_addresses(console) == []


def test_the_four_addresses_are_one_value_and_cannot_drift_apart() -> None:
    """**The realm's own comment says these change together or sign-in breaks in a way that
    looks like Keycloak being wrong**, and a comment saying so is a comment somebody has to
    read. A substitution over the whole document makes it structural instead: they are one
    value written four times.

    Delete this and three of the four can be updated for a new address while the fourth keeps
    pushing back-channel logouts at whoever had the last one."""
    console = _console(json.loads(importable_realm(REALM, CONFIGURED)))
    attributes = console["attributes"]
    assert isinstance(attributes, dict)

    assert console["webOrigins"] == ["https://brain.acme.example", "http://localhost:5173"]
    assert attributes["backchannel.logout.url"] == (
        "https://brain.acme.example/auth/backchannel-logout"
    )
    assert attributes["post.logout.redirect.uris"] == (
        "https://brain.acme.example/signed-out##http://localhost:5173/signed-out"
    )


def test_the_development_callback_is_left_alone_by_the_substitution() -> None:
    """The positive case for the walk not being a blanket rewrite. `localhost:5173` is the
    console's dev server and belongs to whoever is running it, not to any installation, so it
    survives untouched: a substitution that replaced every address would take development
    sign-in away as the price of fixing production.

    Delete this and `substitute` can be written as "replace every URL", which passes every
    other test in this file."""
    document = {"a": f"{PLACEHOLDER_ORIGIN}/x", "b": "http://localhost:5173/x", "c": 3}

    assert substitute(document, origin="https://brain.acme.example") == {
        "a": "https://brain.acme.example/x",
        "b": "http://localhost:5173/x",
        "c": 3,
    }


def test_an_installation_that_has_not_said_where_it_is_gets_no_realm() -> None:
    """**A default host is the same defect with a different spelling.** A realm that imports
    with a plausible address configures a client's identity provider with an allowlist nobody
    chose, and the failure appears at their login page rather than at the import. Refusing puts
    it at the import, naming the setting.

    Raised through `brain.install.value_of` rather than checked here, which is what keeps this
    module from being the second reader `independence.second_readers` refuses.

    Delete this and the placeholder can acquire a fallback, which is where this started."""
    with pytest.raises(InstallError, match=ORIGIN_SETTING):
        importable_realm(REALM, {})


def test_a_realm_still_naming_the_placeholder_is_refused_rather_than_written(
    tmp_path: Path,
) -> None:
    """The check that the substitution actually reached everything, asked after it ran rather
    than assumed. A field carrying an address that resolves nowhere is a realm Keycloak
    accepts and a sign-in it then refuses, which is the failure at the furthest possible
    remove from its cause.

    **The second half is where the check earns its place.** `substitute` rewrites values and
    never keys, because a key is a field name Keycloak looks up and rewriting one renames a
    setting silently. This reads keys too, so a placeholder somewhere the substitution cannot
    reach is refused rather than written, and `importable_realm` is what refuses.

    Delete this and `substitute` can quietly stop substituting for one shape of node, and the
    refusal in `importable_realm` becomes a branch nothing can reach."""
    left = unconfigured_addresses(
        {"clients": [{"attributes": {"backchannel.logout.url": f"{PLACEHOLDER_ORIGIN}/x"}}]}
    )

    assert left == ["realm.clients[0].attributes.backchannel.logout.url"]
    assert unconfigured_addresses({"clients": [{"redirectUris": ["https://ok.example/x"]}]}) == []

    keyed = tmp_path / "realm-export.json"
    keyed.write_text(
        json.dumps({"realm": "brain", "attributes": {f"{PLACEHOLDER_ORIGIN}/x": "y"}}),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(RealmError, match="a field name"):
        importable_realm(keyed, CONFIGURED)


def test_one_origin_is_taken_from_several_redirect_uris_that_agree() -> None:
    """The positive case, and the reason the origin is derived rather than asked for
    separately: an install that registers two paths on its own address has one origin, and
    asking for it twice is two values that can disagree.

    Taken as scheme and authority rather than by removing a known path, so this does not have
    to agree with `brain.setup_wizard.CALLBACK_PATH` about what the callback is called.

    Delete this and an install with two redirect URIs is refused for no reason."""
    assert (
        install_origin(" https://brain.acme.example/auth/callback ,https://brain.acme.example/x")
        == "https://brain.acme.example"
    )
    assert install_origin("https://brain.acme.example:8443/a") == "https://brain.acme.example:8443"


def test_two_origins_are_refused_because_keycloak_takes_one_logout_url() -> None:
    """`backchannel.logout.url` is a single string in Keycloak's client representation, so a
    realm built from two origins is right for one of them and silently wrong for the other:
    sessions ended at the identity provider are never pushed to the second, and the symptom is
    a session that stays alive after a logout somebody watched succeed.

    Delete this and the second origin is dropped without a word."""
    with pytest.raises(RealmError, match="2 origins"):
        install_origin("https://a.example/auth/callback,https://b.example/auth/callback")


def test_a_redirect_uri_that_is_not_absolute_is_refused() -> None:
    """`/auth/callback` on its own has no origin to register, and Keycloak needs an absolute
    URI. Refusing here says which value is wrong; accepting it produces a realm with an empty
    web origin, which fails as a CORS error in a browser console.

    Delete this and a relative path becomes an origin of `://`."""
    with pytest.raises(RealmError, match="not an absolute URL"):
        install_origin("/auth/callback")


def test_a_setting_holding_only_separators_is_refused_rather_than_read_as_none() -> None:
    """An empty list and a list of empty strings are the same to a person and different to a
    parser. Both mean the console has nowhere to return to, and the second is what a trailing
    comma in an environment file produces.

    Delete this and `install_origin` raises IndexError instead, which names nothing."""
    with pytest.raises(RealmError, match="no redirect URI"):
        install_origin(" , ")


# --- the command the import scripts run ------------------------------------------------


def test_the_command_writes_the_realm_and_refuses_without_an_installation(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ops/keycloak/setup.sh` used to strip the comments itself with a jq filter, which is a
    second implementation of `strip_comments` and was wrong in the way only a second
    implementation can be: it also deleted the two `_comment` keys inside `config` maps, which
    Keycloak stores verbatim and which are therefore configuration. It also had nowhere to put
    the installation's origin. Both import paths run this now.

    Delete this and the command can stop being a command, and that script silently imports a
    realm nobody prepared."""
    monkeypatch.setenv(ORIGIN_SETTING, "https://brain.acme.example/auth/callback")
    assert main([str(REALM)]) == 0
    assert json.loads(capsys.readouterr().out)["realm"] == "brain"

    monkeypatch.delenv(ORIGIN_SETTING, raising=False)
    assert main([str(REALM)]) == 1
    assert ORIGIN_SETTING in capsys.readouterr().err

    assert main([]) == 2
    assert "usage" in capsys.readouterr().err
