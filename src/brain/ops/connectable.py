"""Which sources the console can connect, what each asks for, and why the others cannot be.

Until this module nothing in the repository declared which sources are connectable, and two
modules said so as the reason for having no list: `brain.setup_wizard._slug_list` and
`brain.console.connector_trust.AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE`.
Both were right that a list invented in a rendering layer would disagree with the connectors the
first time one was added. **Since 2026-09-28 the list is not written here at all: each connector
declares its own console form, or the sentence saying why it has none, as `CONNECTOR` in its own
module, and `CONNECTABLE` and `NOT_FROM_THE_CONSOLE` are read off
`brain.ops.connector_catalogue.declarations`: the shipped connectors, and since M11.7.8 the ones a
second person reviewed on this install, recomputed whenever that reviewed set changes.** So the two
lists are total over the declarations by construction, and a connector joins the Connectors screen
by declaring itself, or by being approved, with no edit here.

**A source is connectable from the console when its manifest is built from settings a person can
type and a credential in the shape its vendor issues it**, and this install can read it (below).
Xero is pinned to one organisation, HubSpot to one account and Freshdesk to one helpdesk and the
one department that reads it. Google Drive's form names one folder, the department it belongs to
and the person answerable for it, with a service account's key file, and the Laravel database's
names its server, one schema's views, each with the visibility rule written by whoever read its
definition, with a read-only user's name and password. Both were declared before either could be
read; Laravel is offered since M11.6.1 because it now reads, by the rule below and nothing else,
and Drive is listed until it does. Each connection class already refuses a setting that narrows
nothing.
Lark's Base and Wiki are connected on Connect Lark, which says so, and the screen shows that
sentence rather than leaving them out.

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

**A source is offered only when this install reads it**
(`A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS`). A declared form is not enough: the
worker must read the source into its index on a schedule, or a question must read it live, and
either needs the source's call ceiling recorded, because nothing is read against a ceiling nobody
measured (`brain.ops.connector_sync.NO_VERIFIED_CEILING`). A connector with a form and no way to
be read is listed as not connectable yet, in `THIS_INSTALL_CANNOT_READ_IT_YET`'s words, and never
offered. Until 2026-09-30 the Google Drive and Laravel forms were offered with nothing behind
them, so a connection saved its settings and its key and read nothing, and HubSpot was offered
with no ceiling recorded, so its reading never ran; its documented ceiling is recorded now. And
**a source is offered only when Ask can answer from it** too
(`A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_ASK_ANSWERS_FROM`): HubSpot, once read, still reached no
question until its records were classified for the answer lane.

Rejected: a `ConnectorRegistry` built from these at start. The registry is a runtime record of what
somebody installed; this is the product's list of what could be, and a registry holding every
connectable source would read on the screen as every source connected.

**A source whose connector is custom code is offered only where the install runs a sandbox for
it (M11.1.5).** Its form and its reading are not enough: the code runs only through the sandbox
runner `brain.ops.custom_code_run.installed_runner` names, which no install has until the sandbox
service runs, and with none the source is listed as not connectable yet and never offered.

Task ids: M42.6.5, M11.1.6, M11.9.6, M11.7.7, M11.1.5, M11.8.6, M11.7.8
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import (
    DEFAULT_SETTING_CHARS,
    CodeReading,
    ConnectorDeclaration,
    CredentialShape,
    Setting,
    SettingRefusedError,
    WriteGrant,
)
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.oauth import OAuthConsent
from brain.knowledge.connector_rows import ANSWERED_BY_PASSAGES, CONNECTOR_ROW_ENTITIES
from brain.ops.connect_steps import GuideStep
from brain.ops.connector_catalogue import Derived
from brain.ops.credentials import (
    connector_key_slot,
    connector_oauth_slot,
    connector_person_oauth_slot,
)
from brain.ops.custom_code_run import installed_runner
from brain.ops.limits import connector_ceiling
from brain.ops.secrets import SecretRef, VaultRole
from brain.tools.run_skill import ScriptRunner

# ------------------------------------------------------------ written-down reasons

#: Why a declared form is not enough to be offered. See the module docstring.
A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS: Final = (
    "The Connectors screen offers a source only when this install can read it: the worker reads it "
    "into its index on a schedule or a question reads it live, and its call ceiling is recorded, "
    "since nothing is read against a ceiling nobody measured. A connector that declares a form "
    "and cannot be read is listed as not connectable yet, so nobody is shown a connection that "
    "saves its key and reads nothing."
)

#: Why being read is not enough either.
A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_ASK_ANSWERS_FROM: Final = (
    "A source read into the index and never asked about is a key kept for nothing. So the screen "
    "offers a source only when Ask can answer from it as well: its records are classified for the "
    "answer lane (brain.knowledge.connector_rows), or what it holds is read as passages for the "
    "question's model step. HubSpot was read and answerable by nothing until 2026-09-30."
)

#: What the screen says of a source whose form is declared and which this install cannot read.
THIS_INSTALL_CANNOT_READ_IT_YET: Final = (
    "Its connect form is ready, but this install cannot read it yet, so it is not offered: "
    "connecting it now would keep its key and read nothing."
)

#: Why a source's settings are judged by building its manifest.
A_SETTING_IS_REFUSED_BY_THE_CONNECTOR_THAT_WOULD_USE_IT: Final = (
    "Every identifier a source is connected with is checked by the connection class that pins it, "
    "which refuses a selector that narrows nothing or that the source would not recognise. Those "
    "rules are applied by building the manifest from what was typed, before anything is written, "
    "so what the screen refuses and what the connector would refuse are one rule."
)

#: The role a connected source's key is read under when something runs the connector.
READING_ROLE: Final = VaultRole.WORKER

#: The longest setting accepted unless the setting says otherwise, which is `ConnectorScope`'s own
#: ceiling on a selector. The declaration's own default, named here for the screens that read it.
MAX_SETTING_CHARS: Final = DEFAULT_SETTING_CHARS


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
    #: The writes it can be allowed to make, each with a key of its own (M11.7.3).
    writes: tuple[WriteGrant, ...] = ()
    #: How a person consents to it at its vendor, when it authorises by OAuth (M11.8.6).
    oauth: OAuthConsent | None = None


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
def reads(declaration: ConnectorDeclaration, *, runner: ScriptRunner | None = None) -> bool:
    """Whether this install can read the source: a reading or a live lookup, and a ceiling.

    See `A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS`. A source whose connector is custom
    code is read only in the sandbox `runner` is, so with none it is not read here
    (`brain.connectors.custom_code.A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ`).
    """
    if isinstance(declaration.reading, CodeReading) and runner is None:
        return False
    has_a_way = declaration.reading is not None or declaration.live is not None
    return has_a_way and connector_ceiling(declaration.name) is not None


def answers(declaration: ConnectorDeclaration) -> bool:
    """Whether Ask can answer from the source: classified for the answer lane, or read as passages.

    See `A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_ASK_ANSWERS_FROM`.
    """
    name = declaration.name
    return name in CONNECTOR_ROW_ENTITIES or name in ANSWERED_BY_PASSAGES


def offered(
    declarations: Mapping[str, ConnectorDeclaration],
    *,
    runner: ScriptRunner | None = None,
) -> tuple[dict[str, Connectable], dict[str, NotConnectable]]:
    """The sources the console offers, and the ones it lists with the reason it does not.

    A declaration with a form that this install cannot read is listed with
    `THIS_INSTALL_CANNOT_READ_IT_YET` and no steps, since its steps end in the form it is not
    offered. `runner` is the install's sandbox runner, which only a custom-code source needs.
    """
    forms = declared_forms(declarations)
    offers = {
        name: form
        for name, form in forms.items()
        if reads(declarations[name], runner=runner) and answers(declarations[name])
    }
    listed: dict[str, NotConnectable] = {}
    for name, one in declarations.items():
        if one.console is None:
            listed[name] = NotConnectable(
                name=name, label=one.label, why=one.not_from_the_console, guide=one.guide
            )
        elif name not in offers:
            listed[name] = NotConnectable(
                name=name, label=one.label, why=THIS_INSTALL_CANNOT_READ_IT_YET
            )
    return offers, listed


def declared_forms(declarations: Mapping[str, ConnectorDeclaration]) -> dict[str, Connectable]:
    """Every console form declared, offered or not: what a form asks for, apart from whether it is
    offered. A form's own tests read these, so a form can be proved before its reading exists."""
    return {
        name: Connectable(
            name=name,
            label=one.label,
            settings=one.console.settings,
            credential_label=one.console.credential_label,
            credential_hint=one.console.credential_hint,
            build=one.console.build,
            guide=one.guide,
            credential_shape=one.console.credential_shape,
            writes=one.writes,
            oauth=one.oauth,
        )
        for name, one in declarations.items()
        if one.console is not None
    }


#: Every console form this install declares, offered or not. See `declared_forms`.
DECLARED_FORMS: Final[Mapping[str, Connectable]] = Derived(declared_forms)

#: Every source the console can connect, by name, read off `brain.ops.connector_catalogue`'s
#: declarations: the shipped ones, and the ones reviewed on this install (M11.7.8).
CONNECTABLE: Final[Mapping[str, Connectable]] = Derived(
    lambda found: offered(found, runner=installed_runner())[0]
)

#: Every source this install has a connector for and the console cannot connect, and why.
NOT_FROM_THE_CONSOLE: Final[Mapping[str, NotConnectable]] = Derived(
    lambda found: offered(found, runner=installed_runner())[1]
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


def refresh_reference(name: str) -> SecretRef:
    """Where the refresh token a person's consent to a source bought is kept, read by the worker's
    role like the source's key (M11.8.6). See `brain.ops.credentials.connector_oauth_slot`."""
    return SecretRef(path=connector_oauth_slot(name).path, role=READING_ROLE)


def person_refresh_reference(name: str, principal_id: str) -> SecretRef:
    """Where the refresh token one person's own consent to a source bought is kept (M11.8.6).

    Read only by `brain.ops.connector_sync_run.PersonalKeys`, for that person's own question. See
    `brain.ops.credentials.connector_person_oauth_slot`.
    """
    return SecretRef(path=connector_person_oauth_slot(name, principal_id).path, role=READING_ROLE)


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
        elif len(value) > one.max_chars:
            found.append(
                SettingProblem(
                    field=one.name,
                    code="too_long",
                    message=(
                        f"That is longer than {one.max_chars} characters, which is longer "
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
