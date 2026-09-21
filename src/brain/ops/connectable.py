"""Which sources the console can connect, what each asks for, and why the others cannot be.

Until this module nothing in the repository declared which sources are connectable, and two
modules said so as the reason for having no list: `brain.setup_wizard._slug_list` and
`brain.console.connector_trust.AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE`.
Both were right that a list invented in a rendering layer would disagree with the connectors the
first time one was added. So the list is written once, calling the manifest builders it names, and
**it is total over them**: every module in `brain.connectors` that builds a manifest is named here
exactly once, either as a source that can be connected or with the reason it cannot be yet, and
`tests/unit/test_connectable.py` reads that package to hold it. A connector added without a
decision here fails that test rather than being silently absent from the screen.

**It lives in `brain.ops` and not beside the builders in `brain.connectors`, and that is forced.**
`brain.connectors.write_verification.connectors` and `tests/invariants/test_cassettes.py` both treat
a module in that package that builds a manifest as a connector to one source, owed a read-back entry
and a cassette run. This is a list of connectors, not one, and putting it there would either make
it one or add a third exemption list to keep in step with the other two.

**A source is connectable from the console when its manifest is built from identifiers a person
can type and one key they can paste**, and today that is two of the seven. Xero is pinned to one
organisation and HubSpot to one account, and each connection class already refuses an identifier
that narrows nothing. The other five need something this screen has no way to collect: a visibility
rule written by somebody who has read the source's own permission model, a declaration of which
department a space or a folder belongs to, or a key file rather than a key. Each says which, in
`NOT_FROM_THE_CONSOLE`, and the screen shows the sentence rather than leaving the source out.

**Validation is the connector's own refusal, and never a second opinion about it.** The settings
are checked for being given and for fitting, and then the manifest is built from them: a selector
of `*`, one with a space inside, or anything else `brain.connectors.contract.ConnectorScope`
refuses is refused because the connection class refused it, and the person is told in this
source's words what to type instead. A second grammar here would be a second place for "narrows
nothing" to be subtly wrong, which is exactly the argument `XeroConnection.__post_init__` makes.

**The manifest's credential names the slot the key is kept in and the role that will read it**,
`brain.ops.credentials.connector_key_slot` and `brain.ops.secrets.VaultRole.WORKER`. The binding is
read-only, as both builders already declare it; nothing here can widen it.

Rejected: a `ConnectorRegistry` built from these at start. The registry is a runtime record of what
somebody installed; this is the product's list of what could be, and a registry holding every
connectable source would read on the screen as every source connected.

Task ids: M42.6.5
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.connectors.contract import ConnectorContractError
from brain.connectors.hubspot import CONNECTOR_NAME as HUBSPOT
from brain.connectors.hubspot import HubSpotConnection, hubspot_manifest
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.xero import CONNECTOR_NAME as XERO
from brain.connectors.xero import XeroConnection, xero_manifest
from brain.ops.credentials import connector_key_slot
from brain.ops.secrets import SecretRef, VaultRole

# ------------------------------------------------------------ written-down reasons

#: Why a source's settings are judged by building its manifest.
A_SETTING_IS_REFUSED_BY_THE_CONNECTOR_THAT_WOULD_USE_IT: Final = (
    "Every identifier a source is connected with is checked by the connection class that pins it, "
    "which refuses a selector that narrows nothing or that the source would not recognise. Those "
    "rules are applied by building the manifest from what was typed, before anything is written, "
    "so what the screen refuses and what the connector would refuse are one rule."
)

#: The role a connected source's key is read under when something runs the connector.
READING_ROLE: Final = VaultRole.WORKER

#: The longest setting accepted, which is `ConnectorScope`'s own ceiling on a selector.
MAX_SETTING_CHARS: Final = 200


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class Setting:
    """One identifier a source is connected with: its name, its label, and where to find it."""

    name: str
    label: str
    hint: str
    #: What a person is told when the connector refuses what was typed here.
    refused: str


@dataclass(frozen=True)
class Connectable:
    """A source that can be connected from the console, and everything the form asks for.

    `build` takes the settings, already given and fitting, and the reference to where the key is
    kept, and returns the manifest or raises the connector's own refusal.
    """

    name: str
    label: str
    settings: tuple[Setting, ...]
    credential_label: str
    credential_hint: str
    build: Callable[[Mapping[str, str], SecretRef], ConnectorManifest]


@dataclass(frozen=True)
class NotConnectable:
    """A source this build has a connector for and the console cannot connect yet, and why."""

    name: str
    label: str
    why: str


@dataclass(frozen=True)
class SettingProblem:
    """One thing wrong with a setting: its name, a stable code, and what to do about it."""

    field: str
    code: str
    message: str


class NotConnectableError(Exception):
    """The source named is not one the console can connect. The route refuses it in one way."""


# ------------------------------------------------------------------------ the sources


def _xero(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    return xero_manifest(XeroConnection(tenant_id=settings["tenant_id"]), ref=ref)


def _hubspot(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    return hubspot_manifest(HubSpotConnection(portal_id=settings["portal_id"]), ref=ref)


#: Every source the console can connect, by name. See the module docstring for what earns a place.
CONNECTABLE: Final[Mapping[str, Connectable]] = MappingProxyType(
    {
        XERO: Connectable(
            name=XERO,
            label="Xero",
            settings=(
                Setting(
                    name="tenant_id",
                    label="Organisation id",
                    hint=(
                        "The id of the one Xero organisation this connection reads, exactly as "
                        "Xero shows it. A connection reads one organisation and no other."
                    ),
                    refused=(
                        "Xero would not recognise that as one organisation. Paste the "
                        "organisation's id exactly as Xero shows it, with no spaces, and not a "
                        "word such as all."
                    ),
                ),
            ),
            credential_label="The key Xero issued for this connection",
            credential_hint=(
                "Ask Xero for accounting.transactions.read and accounting.contacts.read, and for "
                "no write scope: this system answers questions about invoices and never raises "
                "one. Paste it as one piece. It is kept in the vault and never shown again."
            ),
            build=_xero,
        ),
        HUBSPOT: Connectable(
            name=HUBSPOT,
            label="HubSpot",
            settings=(
                Setting(
                    name="portal_id",
                    label="Account id",
                    hint=(
                        "The HubSpot account id this connection reads, as HubSpot shows it in the "
                        "account's settings. A connection reads one account and no other."
                    ),
                    refused=(
                        "HubSpot would not recognise that as one account. Paste the account id "
                        "exactly as HubSpot shows it, with no spaces, and not a word such as all."
                    ),
                ),
            ),
            credential_label="The access token of a private app",
            credential_hint=(
                "Give the private app crm.objects.contacts.read and crm.objects.deals.read, and "
                "no write scope or anything touching settings. Paste its token as one piece. It "
                "is kept in the vault and never shown again."
            ),
            build=_hubspot,
        ),
    }
)

#: Every source this build has a connector for and the console cannot connect, and why.
NOT_FROM_THE_CONSOLE: Final[Mapping[str, NotConnectable]] = MappingProxyType(
    {
        "freshdesk": NotConnectable(
            name="freshdesk",
            label="Freshdesk",
            why=(
                "Its tickets are kept under a visibility rule saying which people may see which "
                "helpdesk groups, written by somebody who has read how this company's groups map "
                "to its departments. This screen has no way to write that rule yet, so it is "
                "connected at the server."
            ),
        ),
        "google_drive": NotConnectable(
            name="google_drive",
            label="Google Drive",
            why=(
                "It is connected to one folder, with the department whose knowledge the folder "
                "is and the person answerable for what it contributes, and its key is a service "
                "account key file rather than one unbroken key. This screen takes neither yet, so "
                "it is connected at the server."
            ),
        ),
        "laravel": NotConnectable(
            name="laravel",
            label="Laravel database views",
            why=(
                "It reads database views, each kept under a visibility rule written by whoever "
                "read the view's definition. This screen has no way to write those rules yet, so "
                "it is connected at the server."
            ),
        ),
        "lark_base": NotConnectable(
            name="lark_base",
            label="Lark Base",
            why=(
                "It is connected through Connect Lark on this screen, which creates the Lark app, "
                "tests it and switches knowledge from one Base on. It is not listed here because "
                "its records are read live and never synced into this system."
            ),
        ),
        "lark_wiki": NotConnectable(
            name="lark_wiki",
            label="Lark Wiki",
            why=(
                "It is connected through Connect Lark on this screen, which creates the Lark app, "
                "tests it and switches knowledge from the shared wiki spaces on. It is not listed "
                "here because its pages are read live and never synced into this system."
            ),
        ),
    }
)


# ------------------------------------------------------------------------ the decisions


def connectable(name: str) -> Connectable:
    """The source named, or `NotConnectableError`. A source not listed is refused, not guessed."""
    found = CONNECTABLE.get(name)
    if found is None:
        msg = f"{name!r} is not a source the console can connect"
        raise NotConnectableError(msg)
    return found


def key_reference(name: str) -> SecretRef:
    """Where a connected source's key is kept, and the role that will read it."""
    return SecretRef(path=connector_key_slot(name).path, role=READING_ROLE)


def blank_sentence(setting: Setting) -> str:
    """What a person is told when this setting is left blank. Served beside the form as well, so a
    console can say it before the confirmation opens without a second copy of the words."""
    return f"Give the {setting.label.lower()}."


def given(kind: Connectable, settings: Mapping[str, str]) -> dict[str, str]:
    """The settings this source takes, each with its outer whitespace removed, and no others.

    Outer whitespace goes for `brain.ops.credentials.problems_with`'s reason: a paste usually
    carries a line break at the end. Inner whitespace stays and is the connector's to refuse.
    """
    return {one.name: settings.get(one.name, "").strip() for one in kind.settings}


def settings_problems(kind: Connectable, settings: Mapping[str, str]) -> tuple[SettingProblem, ...]:
    """Everything wrong with the settings, all at once, and then the connector's own refusal.

    A setting this source does not take, one not given, and one too long are each told by field.
    Only when none of those is found is the manifest built, because a connection class handed a
    blank would refuse it in its own words and the person would be told the wrong thing to fix.
    See `A_SETTING_IS_REFUSED_BY_THE_CONNECTOR_THAT_WOULD_USE_IT`.
    """
    asked = {one.name for one in kind.settings}
    found = [
        SettingProblem(
            field=extra,
            code="not_asked",
            message=f"{kind.label} does not take a setting by that name. Leave it out.",
        )
        for extra in sorted(set(settings) - asked)
    ]
    for one in kind.settings:
        value = settings.get(one.name, "").strip()
        if not value:
            found.append(SettingProblem(field=one.name, code="blank", message=blank_sentence(one)))
        elif len(value) > MAX_SETTING_CHARS:
            found.append(
                SettingProblem(
                    field=one.name,
                    code="too_long",
                    message=(
                        f"That is longer than {MAX_SETTING_CHARS} characters, which is longer "
                        f"than any {one.label.lower()}. Check what was copied."
                    ),
                )
            )
    if found:
        return tuple(found)
    try:
        kind.build(given(kind, settings), key_reference(kind.name))
    except ConnectorContractError:
        # The connector's message is written for somebody reading the source and can quote what
        # was typed; the person is told this source's sentence instead. Which setting it was is
        # known for a source with one setting, which is every source listed today.
        return tuple(
            SettingProblem(field=one.name, code="refused", message=one.refused)
            for one in kind.settings
        )
    return ()


def manifest_for(name: str, settings: Mapping[str, str]) -> ConnectorManifest:
    """The manifest a stored connection declares today, or the refusal that says it cannot be built.

    Raises `NotConnectableError` for a source no longer listed, and the connector's own
    `ConnectorContractError` for settings it now refuses. The console shows a connection whose
    manifest cannot be built and says why, rather than leaving it off the list.
    """
    kind = connectable(name)
    return kind.build(given(kind, settings), key_reference(name))
