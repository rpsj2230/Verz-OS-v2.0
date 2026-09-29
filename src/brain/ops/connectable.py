"""Which sources the console can connect, what each asks for, and why the others cannot be.

Until this module nothing in the repository declared which sources are connectable, and two
modules said so as the reason for having no list: `brain.setup_wizard._slug_list` and
`brain.console.connector_trust.AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE`.
Both were right that a list invented in a rendering layer would disagree with the connectors the
first time one was added. **Since 2026-09-28 the list is not written here at all: each connector
declares its own console form, or the sentence saying why it has none, as `CONNECTOR` in its own
module, and `CONNECTABLE` and `NOT_FROM_THE_CONSOLE` are read off
`brain.connectors.declaration.shipped` when this module is imported, which is at start-up.** So
the two lists are total over the shipped connectors by construction, and a connector joins the
Connectors screen by declaring itself, with no edit here.

**A source is connectable from the console when its manifest is built from settings a person can
type and a credential in the shape its vendor issues it**, and since 2026-09-30 (M11.7.7) that is
every shipped source but the two Connect Lark switches on. Xero is pinned to one organisation,
HubSpot to one account and Freshdesk to one helpdesk and the one department that reads it; Google
Drive to one folder, the department it belongs to and the person answerable for it, with a service
account's key file; the Laravel database to one schema's views, each with the visibility rule
written by whoever read its definition, with a read-only user's name and password. Each connection
class already refuses a setting that narrows nothing. Lark's Base and Wiki are connected on Connect
Lark, which says so, and the screen shows that sentence rather than leaving them out.

**Validation is the connector's own refusal, and never a second opinion about it.** The settings
are checked for being given and for fitting, and then the manifest is built from them: a selector
of `*`, one with a space inside, or anything else `brain.connectors.contract.ConnectorScope`
refuses is refused because the connection class refused it, and the person is told in this
source's words what to type instead. A second grammar here would be a second place for "narrows
nothing" to be subtly wrong, which is exactly the argument `XeroConnection.__post_init__` makes. A
source asking for two settings says which one it refused
(`brain.connectors.declaration.SettingRefusedError`), and only that one is marked.

**The manifest's credential names the slot the key is kept in and the role that will read it**,
`brain.ops.credentials.connector_key_slot` and `brain.ops.secrets.VaultRole.WORKER`. The binding is
read-only, as both builders already declare it; nothing here can widen it.

Rejected: a `ConnectorRegistry` built from these at start. The registry is a runtime record of what
somebody installed; this is the product's list of what could be, and a registry holding every
connectable source would read on the screen as every source connected.

Task ids: M42.6.5, M11.1.6, M11.9.6, M11.7.7
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import CredentialShape, Setting, SettingRefusedError, shipped
from brain.connectors.manifest import ConnectorManifest
from brain.ops.connect_steps import GuideStep
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
    #: The screens that take an administrator from nothing to this form, the form last.
    guide: tuple[GuideStep, ...] = ()
    #: How the credential is asked for and kept (M11.7.7).
    credential_shape: CredentialShape = CredentialShape.KEY


@dataclass(frozen=True)
class NotConnectable:
    """A source this build has a connector for and the console cannot connect yet, and why."""

    name: str
    label: str
    why: str
    #: The screens that prepare it at the vendor and hand it to the server, where they are known.
    guide: tuple[GuideStep, ...] = ()


@dataclass(frozen=True)
class SettingProblem:
    """One thing wrong with a setting: its name, a stable code, and what to do about it."""

    field: str
    code: str
    message: str


class NotConnectableError(Exception):
    """The source named is not one the console can connect. The route refuses it in one way."""


# ------------------------------------------------------------------------ the sources
#: Every source the console can connect, by name, read off the shipped declarations at start-up.
CONNECTABLE: Final[Mapping[str, Connectable]] = MappingProxyType(
    {
        name: Connectable(
            name=name,
            label=one.label,
            settings=one.console.settings,
            credential_label=one.console.credential_label,
            credential_hint=one.console.credential_hint,
            build=one.console.build,
            guide=one.guide,
            credential_shape=one.console.credential_shape,
        )
        for name, one in shipped().items()
        if one.console is not None
    }
)

#: Every source this build has a connector for and the console cannot connect, and why.
NOT_FROM_THE_CONSOLE: Final[Mapping[str, NotConnectable]] = MappingProxyType(
    {
        name: NotConnectable(
            name=name, label=one.label, why=one.not_from_the_console, guide=one.guide
        )
        for name, one in shipped().items()
        if one.console is None
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
    except SettingRefusedError as refusal:
        # A connector asking for more than one setting names the one it refused, so the person is
        # told that setting's sentence and not asked to retype one that was right.
        named = [one for one in kind.settings if one.name == refusal.setting]
        return tuple(
            SettingProblem(field=one.name, code="refused", message=one.refused)
            for one in (named or kind.settings)
        )
    except ConnectorContractError:
        # The connector's message is written for somebody reading the source and can quote what
        # was typed; the person is told this source's sentence instead. A refusal naming no
        # setting marks every one, which is exact for a source with a single setting.
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
