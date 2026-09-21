"""Turning the reviewed realm into one Keycloak will accept.

**The realm file did not import, and nothing knew.** `ops/keycloak/realm-export.json` is a
carefully argued document and seventeen tests hold it to its claims, and on 2026-09-06 a
throwaway Keycloak 26.0 refused it outright:

    ERROR: Failed to run import
    ERROR: Unrecognized field "_comment" (class org.keycloak.representations.idm.
    RealmRepresentation), not marked as ignorable (144 known properties: ...)

Keycloak deserialises the realm into strongly typed representations and rejects any field it
does not recognise. The file carries eleven `_comment` keys, which are the reason it is worth
reading, and every one of them outside a `config` map is fatal.

**Why the tests could not have caught it.** They parse the file as JSON and assert about its
contents, and it is perfectly valid JSON. What they could not know is what Keycloak's
deserialiser does with a key it has never heard of, and no amount of reading the file
produces that fact. It took an import to find, which is the same lesson `M1.1.1` recorded
when the first import found three silently discarded client scopes.

**Deleting the comments was the obvious fix and is the wrong one.** They are the argument for
every security decision in that file: why RS256 over HS256, why no password grant, why the
redirect URIs are exact paths. A realm nobody can read is a realm that gets edited by whoever
is fixing a login problem at the time, which is precisely what the comments exist to prevent.

So the reviewed file keeps its argument and the import gets a copy without it. `strip_comments`
is that copy, and it is deliberately not a text transform: an underscore-prefixed key can
appear inside a `config` map, where Keycloak stores free-form strings and accepts anything,
and a regex over the text would remove those too and quietly change what the mapper does.

**`config` is the one place an underscore key survives.** `ProtocolMapperRepresentation.config`
is a `Map<String, String>`, so Keycloak neither validates nor rejects its keys. That is why
the realm's two mapper comments live there and why they are left alone: removing them would
be removing configuration, not documentation, and the two are indistinguishable from outside.

---

**And the realm named one deployment's server, which broke every other client's sign-in.**
Until 2026-09-09 `redirectUris`, `webOrigins`, `backchannel.logout.url` and
`post.logout.redirect.uris` all carried the first deployment's host as a literal, and this
module only stripped comments. Keycloak matches `redirect_uri` exactly against the registered
list, so a second client importing that realm had an allowlist naming somebody else's server:
their console's authorisation request was refused before the login form, with
`Invalid parameter: redirect_uri`, and nothing near that page named the realm. It was invisible
to `brain.ops.independence` as well, which read `src`, `migrations`, the console and `docs`
and not `ops`, so the gate written to refuse exactly this value was green over it.

**So the origin is substituted here, and here is the only place it can be.** It has to be one
seam, because four fields have to agree; `importable_realm` is the seam every import already
passes through, both the `keycloak-realm` compose service and `ops/keycloak/setup.sh`. The
setup wizard was the other candidate and it is the wrong one: it writes the environment file
and never touches the realm, and the realm is imported by a container that starts before
anybody has opened the wizard. Keycloak's own `--import-realm` was the third, and it cannot
be told what this install is called.

**The value is `INSTALL_OIDC_REDIRECT_URIS` rather than a new setting**, because
`brain.install` already declares it, already requires it, already refuses to default it, and
its stated meaning is "the redirect URIs the realm will accept". A second setting naming the
same address would be `install.ONE_READER_OR_TWO_DEFAULTS` exactly: two values that agree on
every machine where both are set.

**Rejected: a default host in the file.** That is what was there, spelled differently. A
realm that imports with a plausible address configures somebody's identity provider with an
allowlist nobody chose, and the failure surfaces at a login page rather than at the import.
The placeholder is a reserved documentation domain that can never resolve, and this module
refuses to emit a realm still carrying it, so the failure is the import, loudly, naming the
setting to supply. See `A_DEFAULT_ADDRESS_IMPORTS_AND_A_MISSING_ONE_STOPS`.

---

**The console's client id and the brokered directory are the install's too, since 2026-09-21.**
The console already signed in as `INSTALL_OIDC_CLIENT_ID`, and the realm registered
`brain-console` whatever that said, so an install that set its own id had a console asking for a
client its realm did not have. The shipped client is renamed here, and a name another client of
the realm already holds is refused, because two clients under one id is a realm whose sign-in
depends on which one Keycloak finds first. `INSTALL_BROKERED_DIRECTORY` becomes an identity
provider entry here as well; `brain.identity.brokering` decides the entry and this module is the
reader that hands it the values. `--identity-provider` prints that entry alone, for a realm that
already exists: Keycloak imports a realm only when it has none of that name, and the wizard's
answer is saved after the first import has run.

Task ids: M41.1.5
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from brain.identity.brokering import Brokering, brokering
from brain.install import InstallError, value_of

#: The prefix that marks a key as documentation rather than configuration. One character,
#: chosen because Keycloak has no field starting with it and never will: its representations
#: are Java beans, and a leading underscore is not a legal Java identifier start for a
#: property name that Jackson would map.
COMMENT_PREFIX = "_"

#: The one key whose contents are a free-form map rather than a typed representation.
#:
#: Keycloak stores `config` as `Map<String, String>` and accepts any key in it, so a comment
#: there is configuration as far as the server is concerned and removing it changes what was
#: imported. Everything else in the file is a bean with a fixed set of properties.
FREE_FORM_KEY = "config"

#: Why the comments are stripped rather than deleted from the source.
A_REALM_NOBODY_CAN_READ_IS_A_REALM_THAT_GETS_CLICKED = (
    "The comments are the argument for every security decision in the realm: RS256 over "
    "HS256, no password grant, no implicit flow, exact redirect URIs rather than a wildcard. "
    "A configuration file that states none of its reasons is one that gets edited by "
    "whoever is fixing a login problem at the time, and each of those edits is one line and "
    "undoes a paragraph. So the reviewed file keeps the argument and the import gets a copy "
    "without it, rather than the argument being deleted to satisfy a deserialiser."
)


def strip_comments(node: Any, *, inside_free_form: bool = False) -> Any:
    """The realm with its documentation removed, ready for `--import-realm`.

    Recursive over the parsed structure rather than over the text, because the same key is
    documentation in one place and configuration in another. Inside a `config` map every key
    is a string Keycloak stores verbatim, so a comment there is data and is kept; everywhere
    else it is a field name Keycloak will refuse.

    `inside_free_form` is carried down rather than checked at each level, because a `config`
    map may itself hold nested structures and everything under one is equally free-form.
    """
    if isinstance(node, dict):
        return {
            key: strip_comments(value, inside_free_form=inside_free_form or key == FREE_FORM_KEY)
            for key, value in node.items()
            if inside_free_form or not key.startswith(COMMENT_PREFIX)
        }
    if isinstance(node, list):
        return [strip_comments(item, inside_free_form=inside_free_form) for item in node]
    return node


#: The setting the realm's addresses come from. Declared, required and defaultless in
#: `brain.install`, and this module is its consumer: before 2026-09-09 nothing read it at all,
#: which is why a required setting could be correct on a client's server while their realm
#: still named somebody else's.
ORIGIN_SETTING: Final = "INSTALL_OIDC_REDIRECT_URIS"

#: The setting the realm's name comes from. Declared with the default the reviewed file carries,
#: and read here so the realm Keycloak creates is the one the issuer names; until 2026-09-17
#: nothing read it, and a client who set it got a realm called `brain` regardless.
REALM_SETTING: Final = "INSTALL_OIDC_REALM"

#: The address in the reviewed realm, which is not an address.
#:
#: A reserved documentation domain under RFC 2606, so it can never be registered and never
#: resolves, and `brain.ops.independence.is_reserved` recognises it rather than reporting it.
#: Written as a whole origin rather than as a token like `${...}` so that the reviewed file
#: stays a set of parseable absolute URLs: `console/tests/auth-realm.test.ts` reads the paths
#: back out of it with `new URL`, and a token would make that file unreadable rather than
#: unconfigured.
PLACEHOLDER_ORIGIN: Final = "https://origin.not-configured.example"

#: Why a placeholder is not just another default.
A_DEFAULT_ADDRESS_IMPORTS_AND_A_MISSING_ONE_STOPS: Final = (
    "A realm carrying a plausible host imports cleanly and configures a client's identity "
    "provider with a redirect allowlist nobody chose, and the failure appears at their login "
    "page as an invalid redirect_uri, nowhere near the file that caused it. A placeholder "
    "this module refuses to emit fails at the import instead, with the name of the setting "
    "to supply, before Keycloak has been given anything."
)

#: Why one origin and not a list.
THE_REALM_TAKES_ONE_ORIGIN_BECAUSE_KEYCLOAK_TAKES_ONE_LOGOUT_URL: Final = (
    "backchannel.logout.url is a single string in Keycloak's client representation, so a "
    "realm built from two origins is a realm that is right for one of them and silently "
    "wrong for the other: sessions ended at the identity provider are never pushed to the "
    "second. Refusing is the smaller failure, and it is a failure at import rather than a "
    "logout that appears to work."
)


#: The console's client id and the name the reviewed realm registers it under, which is the
#: declared default of that setting; a test holds all three together.
CLIENT_ID_SETTING: Final = "INSTALL_OIDC_CLIENT_ID"
SHIPPED_CONSOLE_CLIENT: Final = "brain-console"

#: The four settings the brokered identity provider is built from. See `brain.identity.brokering`.
BROKER_SETTING: Final = "INSTALL_BROKERED_DIRECTORY"
BROKER_CLIENT_SETTING: Final = "INSTALL_BROKERED_CLIENT_ID"
STAFF_SOURCE_SETTING: Final = "INSTALL_STAFF_SOURCE"
STAFF_LOCATION_SETTING: Final = "INSTALL_STAFF_SOURCE_LOCATION"

#: Why a console client id another client already holds is refused.
ONE_CLIENT_ID_NAMES_ONE_CLIENT: Final = (
    "Keycloak looks a client up by its id, and a realm holding two clients under one id signs "
    "the console in against whichever it finds first, which may be a confidential service "
    "client with none of the console's flow settings. Refused at the import, naming the id."
)


class RealmError(Exception):
    """Raised when the realm cannot be made importable for this installation."""


def install_origin(redirect_uris: str) -> str:
    """The one origin this installation's console is served from.

    Derived from the configured redirect URIs rather than asked for separately, and taken as
    scheme plus authority rather than by stripping a known path, so it does not have to agree
    with `brain.setup_wizard.CALLBACK_PATH` about what the console's callback is called.

    See `THE_REALM_TAKES_ONE_ORIGIN_BECAUSE_KEYCLOAK_TAKES_ONE_LOGOUT_URL`.
    """
    origins: list[str] = []
    for entry in (one.strip() for one in redirect_uris.split(",")):
        if not entry:
            continue
        split = urlsplit(entry)
        if not split.scheme or not split.netloc:
            msg = (
                f"{ORIGIN_SETTING} contains {entry!r}, which is not an absolute URL, so this "
                "realm has no origin to register and no sign-in could complete"
            )
            raise RealmError(msg)
        origin = f"{split.scheme}://{split.netloc}"
        if origin not in origins:
            origins.append(origin)
    if not origins:
        msg = f"{ORIGIN_SETTING} names no redirect URI, so the console has nowhere to return to"
        raise RealmError(msg)
    if len(origins) > 1:
        msg = (
            f"{ORIGIN_SETTING} spans {len(origins)} origins ({', '.join(sorted(origins))}). "
            f"{THE_REALM_TAKES_ONE_ORIGIN_BECAUSE_KEYCLOAK_TAKES_ONE_LOGOUT_URL}"
        )
        raise RealmError(msg)
    return origins[0]


def substitute(node: Any, *, origin: str) -> Any:
    """The realm with every placeholder address replaced by this installation's own.

    Walked over the parsed structure and applied to every string, deliberately, rather than
    to the four fields that carry it today. The four are `redirectUris`, `webOrigins`,
    `backchannel.logout.url` and `post.logout.redirect.uris`, and the realm's own comment
    records that they have to change together or sign-in breaks in a way that looks like
    Keycloak being wrong. A walk makes "together" structural: a fifth address added to the
    file is substituted on the day it is written, by nobody.

    **Values only, never keys.** A key in this document is a field name Keycloak looks up by
    string, so rewriting one renames a setting rather than addressing it, and the rename is
    silent: Keycloak ignores a property it does not recognise. `unconfigured_addresses` looks
    at keys as well for exactly that reason, so a placeholder somewhere the substitution
    cannot reach is refused rather than shipped.
    """
    if isinstance(node, dict):
        return {key: substitute(value, origin=origin) for key, value in node.items()}
    if isinstance(node, list):
        return [substitute(item, origin=origin) for item in node]
    if isinstance(node, str):
        return node.replace(PLACEHOLDER_ORIGIN, origin)
    return node


def unconfigured_addresses(node: Any, *, path: str = "realm") -> list[str]:
    """Every place the realm still names the placeholder rather than this installation.

    Read after the substitution rather than trusted, for the reason `ops/keycloak/setup.sh`
    reads the realm back after importing it: the transform and the check are two different
    questions, and one of them is "did anything get missed".

    **Keys are read as well as values, which is what makes this a check rather than a
    restatement of `substitute`.** That function rewrites values and deliberately not keys,
    because a key is a field name Keycloak looks up. So the two are not duals: a placeholder
    that has ended up in a field name is somewhere the substitution cannot reach, and this is
    the only thing that would notice before the realm was written.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if PLACEHOLDER_ORIGIN in key:
                found.append(f"{path}.{key} (a field name)")
            found.extend(unconfigured_addresses(value, path=f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(unconfigured_addresses(item, path=f"{path}[{index}]"))
    elif isinstance(node, str) and PLACEHOLDER_ORIGIN in node:
        found.append(path)
    return found


def name_console_client(realm: dict[str, Any], client_id: str) -> None:
    """Rename the shipped console client to this installation's id, in place.

    See `ONE_CLIENT_ID_NAMES_ONE_CLIENT`. A realm with no shipped console client is refused
    too, because the console would then have no client to sign in as at all.
    """
    wanted = client_id.strip()
    if not wanted or any(ch.isspace() for ch in wanted):
        msg = f"{CLIENT_ID_SETTING} is {client_id!r}, which is not a client id"
        raise RealmError(msg)
    clients = realm.get("clients", [])
    console = [one for one in clients if one.get("clientId") == SHIPPED_CONSOLE_CLIENT]
    if len(console) != 1:
        msg = f"the realm registers {len(console)} {SHIPPED_CONSOLE_CLIENT!r} clients, not one"
        raise RealmError(msg)
    others = {one.get("clientId") for one in clients if one is not console[0]}
    if wanted in others:
        msg = f"{CLIENT_ID_SETTING} is {wanted!r}. {ONE_CLIENT_ID_NAMES_ONE_CLIENT}"
        raise RealmError(msg)
    console[0]["clientId"] = wanted


def brokered(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> Brokering:
    """The identity provider this installation's settings ask for, or why there is none.

    The reader of the four values, so the importer's container is handed every one of them
    (`tests/unit/test_realm_importer_settings.py` reads the names out of this file).
    """
    return brokering(
        directory=value_of(BROKER_SETTING, env, saved),
        client_id=value_of(BROKER_CLIENT_SETTING, env, saved),
        staff_source=value_of(STAFF_SOURCE_SETTING, env, saved),
        location=value_of(STAFF_LOCATION_SETTING, env, saved),
    )


def importable_realm(source: Path, env: Mapping[str, str] | None = None) -> str:
    """The reviewed realm as JSON Keycloak accepts, addressed to this installation.

    Returns text rather than writing, so a caller decides where it goes and a test can read
    it without a temporary directory.

    `env` defaults to the real environment for the reason `brain.install.value_of` takes the
    same parameter: a value read through a module-level import cannot be tested at more than
    one setting. The read goes through `value_of` and not through `os.environ`, which is what
    keeps `brain.ops.independence.second_readers` satisfied and, more to the point, means an
    unset value raises `InstallError` naming the setting instead of defaulting to anything.
    """
    origin = install_origin(value_of(ORIGIN_SETTING, env))
    realm = substitute(
        strip_comments(json.loads(source.read_text(encoding="utf-8"))), origin=origin
    )
    realm["realm"] = value_of(REALM_SETTING, env)
    remaining = unconfigured_addresses(realm)
    if remaining:
        msg = (
            f"{len(remaining)} address(es) in the realm still name the placeholder "
            f"({', '.join(remaining)}). {A_DEFAULT_ADDRESS_IMPORTS_AND_A_MISSING_ONE_STOPS}"
        )
        raise RealmError(msg)
    name_console_client(realm, value_of(CLIENT_ID_SETTING, env))
    broker = brokered(env)
    if broker.provider:
        realm.setdefault("identityProviders", []).append(broker.provider)
    return json.dumps(realm, indent=2)


#: The command that prints the brokered identity provider alone.
IDENTITY_PROVIDER_FLAG: Final = "--identity-provider"


def main(argv: list[str] | None = None) -> int:
    """Write the importable realm to standard output, for `ops/keycloak/setup.sh`.

    **This exists to delete a second implementation, not to add a command.** That script
    stripped the comments itself with `jq 'walk(del(._comment))'`, which is a text-shaped
    answer to a structural question: it removes the two `_comment` keys inside `config` maps
    as well, and those are configuration Keycloak stores verbatim, so the shell path quietly
    imported a different realm from the compose path. It also had nowhere to put the
    installation's own origin. One transform with tests answers both.

    `--identity-provider` prints only the brokered directory's entry, resolved with the values
    the setup wizard saved, for `kcadm.sh create identity-provider/instances` on a realm that
    already exists. It exits 1 with the reason when there is nothing to broker.
    """
    args = argv if argv is not None else sys.argv[1:]
    if args == [IDENTITY_PROVIDER_FLAG]:
        broker = brokered(saved=_saved_in_database())
        if not broker.provider:
            print(f"realm_import: {broker.problem or 'sign-in is not brokered'}", file=sys.stderr)
            return 1
        print(json.dumps(broker.provider, indent=2))
        return 0
    if len(args) != 1:
        print(
            "usage: python -m brain.ops.realm_import <realm-export.json> | --identity-provider",
            file=sys.stderr,
        )
        return 2
    try:
        print(importable_realm(Path(args[0])))
    except (RealmError, InstallError) as exc:
        print(f"realm_import: {exc}", file=sys.stderr)
        return 1
    return 0


def _saved_in_database() -> Mapping[str, str]:
    """The installation values the wizard saved, or none when this process has no database.

    Imported here rather than at the top, because the realm importer's own container has no
    database and must not need its driver to strip comments from a file.
    """
    import asyncio

    from brain.ops.install_settings import refresh
    from brain.session import make_app_engine, make_session_factory
    from brain.settings import Settings

    url = Settings().database_url
    if not url:
        return {}

    async def load() -> Mapping[str, str]:
        engine = make_app_engine(url)
        try:
            return await refresh(make_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(load())


def comment_keys(node: Any, *, path: str = "realm", inside_free_form: bool = False) -> list[str]:
    """Every documentation key Keycloak would refuse, with where it is.

    Used by the check that runs before an import rather than after a failure. The failure
    itself is legible enough once you have seen it once; what is expensive is seeing it for
    the first time in a deployment, because a realm that fails to import leaves Keycloak
    running with no realm in it and every sign-in fails with no obvious cause.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            free_form = inside_free_form or key == FREE_FORM_KEY
            if key.startswith(COMMENT_PREFIX) and not inside_free_form:
                found.append(f"{path}.{key}")
            else:
                found.extend(comment_keys(value, path=f"{path}.{key}", inside_free_form=free_form))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(
                comment_keys(item, path=f"{path}[{index}]", inside_free_form=inside_free_form)
            )
    return found


if __name__ == "__main__":
    raise SystemExit(main())
