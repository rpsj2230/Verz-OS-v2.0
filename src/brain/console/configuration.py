"""The Settings screen's decisions: each installation value, where it came from, who may change it.

`brain.install.INSTALLATION` declares what belongs to a client rather than to the product, and until
this module an administrator could see only four of its five groups, on This install, as bare
values with no word about whether a value was chosen, left at its default or read from a file on
the server. The identity group was not shown at all. So the question every support call opens
with, "what is this install configured as", was answered by a shell on the server.

**Every declared setting is on the screen, identity included, and none of them is a secret.**
`brain.console.installation.NAMEABLE_SURFACES` leaves identity out because reading a required
setting through `value_of` raises on a half-configured install. That argument is about the read and
not about the value, so this module reads identity through `resolved`, which reports a required
setting nobody supplied as missing rather than raising. None of the declared values is a
credential: provider keys, the vault token and the relay password live in the vault, and
`THE_SCREEN_SHOWS_NO_CREDENTIAL` is held by a test over the declaration's names. What could still
carry one is a URL's user information or query, so every value shaped like a URL is shown
without them. See `A_URL_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL`.

**Where a value came from is said on every row**, in `brain.install.value_of`'s own order: saved by
a person, set in the environment file, or the product's default. The order is not repeated here:
`resolved` asks the two sources the same way `value_of` does and a test holds the two to the same
answer for every setting.

**Every setting that is safe to change while the install runs is changed here, and the rest say
why not on their own row** (since 2026-09-28; until then only branding was, and the owner opened
Install, Settings to find nothing he could change). Safe means a wrong value is visible and
recoverable from this same screen: the company's name and branding, the languages, the currency
and the time zone, and where answers are made. Each is checked by the setting's own rule before
it is saved (`setting_problem`), confirmed in the console, saved by the wizard's writer inside the
audit attribution, and held by this process at once. Not safe, and read only here with the reason
drawn on the row (`READ_ONLY_BECAUSE`): sign-in (an issuer, realm, client or redirect changed from
a browser signs nobody in, including the person who changed it, with no browser left to change it
back), the staff list and Lark (each has its own screen, which checks the source can be read or
keeps the credential first), the model server's address (every document's text is posted there),
and where files and embeddings are kept (every stored key, vector and width still names the old
place). See `WHAT_IS_CHANGED_HERE_AND_WHAT_IS_NOT`.

**The screen is grouped by what a setting is for, not by who hands it over on install day.**
`brain.install.Belongs` is the second and stays the declaration's; `Section` is the first, in
the owner's words (Company and branding; Language, money and time; Models; Knowledge and search;
Sign-in; Staff list; Files and storage; Lark), and a test holds every setting to exactly one.

**When a change takes effect is said per row, and it is decided by where the value lives.** A value
in the environment file is read when a process starts, so a change to it needs a restart, always.
A branding value saved here is resolved on every request by this process at once, and by every
other application process on its next start, which is
`brain.ops.install_settings.A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER` stated on the row
rather than in a docstring.

**Each setting names the modules that read it**, and a test holds every name to the module's own
source. A setting nothing reads is configuration that changes nothing when somebody changes it,
which is how `INSTALL_SENDER_ADDRESS`, `INSTALL_OIDC_REALM` and `INSTALL_VECTOR_STORE` sat declared
and unread until 2026-09-17. See `A_SETTING_NOTHING_READS_CHANGES_NOTHING`.

**Where a setting is chosen and not in effect, the screen says so.** A brokered directory the
realm will not broker is a finding, with `brain.identity.brokering`'s reason. A local profile on a
release whose inference server serves no model that answers is said in the profile sentence,
which until 2026-09-21 told the reader questions were "answered by the inference server alone".

Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from brain.install import BY_NAME, INSTALLATION, Belongs, Setting, saved_values
from brain.knowledge.search import vector_store_refusal
from brain.locale import CURRENCY_PATTERN, SHIPPED_TAGS, LocaleError, accent_set, rules_for
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, MODEL_PROFILES, local_only
from brain.models.default_ladder import LOCAL_COMPLETION_MODEL
from brain.ops.inference import SERVED_MODELS
from brain.ops.realm_import import brokered
from brain.settings import process_environment

# ------------------------------------------------------------------- written-down reasons

#: Why nothing on this screen is a credential.
THE_SCREEN_SHOWS_NO_CREDENTIAL: Final = (
    "No installation setting is a key, a token or a password: those are kept in the vault and "
    "this screen never reads the vault. An address is shown without a user name, a password, a "
    "query or a fragment, which are the parts of a URL that can carry one."
)

#: Why a URL loses its user information and query on the way to the screen.
A_URL_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL: Final = (
    "An endpoint written with a user name and password before its host, or with ?token= on the "
    "end, works, and a "
    "screen echoing the setting whole would display the secret to everybody who may open it. "
    "The scheme, host, port and path are what an administrator needs to recognise the value."
)

#: What this screen changes and what it does not. Drawn at the foot of the screen.
WHAT_IS_CHANGED_HERE_AND_WHAT_IS_NOT: Final = (
    "Settings that are safe to change while the install runs are changed here: each is checked "
    "before it is saved and the change is recorded with who made it. Sign-in, the staff list, "
    "Lark, the model server's address and where files and embeddings are kept are not, because a "
    "wrong value there locks everybody out or loses track of the company's data; each row says "
    "where it is changed instead."
)

#: Why each setting names its readers.
A_SETTING_NOTHING_READS_CHANGES_NOTHING: Final = (
    "A declared setting that no module reads is a field an administrator can change with nothing "
    "happening, which reads as a fault in whatever they expected it to change. Every setting "
    "names the modules that read it, and a test opens each module and finds the name."
)

#: Said on a row whose value comes from the environment file or the default.
AN_ENVIRONMENT_VALUE_CHANGES_ON_RESTART: Final = (
    "Read from the environment file when the application starts. Changing it there takes effect "
    "after the application restarts."
)

#: Said on a row whose value a person saved, for a setting read on every request.
A_SAVED_VALUE_APPLIES_AT_ONCE_HERE_AND_ON_RESTART_ELSEWHERE: Final = (
    "Saved in the database. This process uses it from the next page it serves; any other "
    "application process uses it after it restarts."
)

#: Said on every row this screen changes: where a saved value reaches, and how soon. The worker
#: reloads the saved values before every schedule tick (`install_settings.refresh_changed`).
A_VALUE_SAVED_HERE_APPLIES_HERE_AT_ONCE_IN_THE_WORKER_WITHIN_A_MINUTE: Final = (
    "Saved here, a change applies from the next page on this server, in the background worker "
    "within a minute, and in any other server process after it restarts."
)

#: Added to the profile sentence when the local profile is chosen and nothing local can answer.
LOCAL_PROFILE_HAS_NO_MODEL_THAT_ANSWERS: Final = (
    "The inference server this release ships serves no model that writes an answer, so "
    "questions reach no model until one is served there or the profile is hosted."
)

#: Said on a required identity setting nobody supplied.
A_REQUIRED_SETTING_NOBODY_SUPPLIED: Final = (
    "Not set, and it has no safe default. Sign-in cannot work until the installer or the "
    "environment file sets it, followed by a restart."
)

# ------------------------------------------------------------------------------ the figures

#: The longest branding value accepted, the setup wizard's own ceiling on one answer.
MAX_BRANDING_CHARS: Final = 200

#: The declared code meaning no currency, which the screen never offers as a choice: an install
#: that has chosen none shows an amount with no code (see `console/src/pages/spendQuery.ts`).
UNSET_CURRENCY: Final = BY_NAME["INSTALL_CURRENCY"].default


class Section(enum.StrEnum):
    """What a setting is for, which is how the screen groups it. See the module docstring."""

    COMPANY = "company"
    LOCALE = "locale"
    MODELS = "models"
    KNOWLEDGE = "knowledge"
    SIGN_IN = "sign_in"
    STAFF = "staff"
    FILES = "files"
    LARK = "lark"


#: The sections in the order the screen draws them: what an owner changes first, first.
SECTION_ORDER: Final[tuple[Section, ...]] = tuple(Section)

#: What each section is called on the screen.
SECTION_TITLES: Final[Mapping[Section, str]] = MappingProxyType(
    {
        Section.COMPANY: "Company and branding",
        Section.LOCALE: "Language, money and time",
        Section.MODELS: "Models",
        Section.KNOWLEDGE: "Knowledge and search",
        Section.SIGN_IN: "Sign-in",
        Section.STAFF: "Staff list",
        Section.FILES: "Files and storage",
        Section.LARK: "Lark",
    }
)

#: The section each setting is drawn in. A test holds every declared setting to exactly one.
SECTION_OF: Final[Mapping[str, Section]] = MappingProxyType(
    {
        "INSTALL_COMPANY_NAME": Section.COMPANY,
        "INSTALL_PRODUCT_NAME": Section.COMPANY,
        "INSTALL_LOGO_URL": Section.COMPANY,
        "INSTALL_ACCENT_COLOUR": Section.COMPANY,
        "INSTALL_SENDER_ADDRESS": Section.COMPANY,
        "INSTALL_LOCALES": Section.LOCALE,
        "INSTALL_CURRENCY": Section.LOCALE,
        "INSTALL_TIME_ZONE": Section.LOCALE,
        "INSTALL_MODEL_PROFILE": Section.MODELS,
        "INSTALL_MODEL_ENDPOINT": Section.MODELS,
        "INSTALL_EMBEDDING_DIMENSIONS": Section.KNOWLEDGE,
        "INSTALL_EMBEDDING_REVISION": Section.KNOWLEDGE,
        "INSTALL_VECTOR_STORE": Section.KNOWLEDGE,
        "INSTALL_OIDC_ISSUER": Section.SIGN_IN,
        "INSTALL_OIDC_REALM": Section.SIGN_IN,
        "INSTALL_OIDC_CLIENT_ID": Section.SIGN_IN,
        "INSTALL_OIDC_REDIRECT_URIS": Section.SIGN_IN,
        "INSTALL_BROKERED_DIRECTORY": Section.SIGN_IN,
        "INSTALL_BROKERED_CLIENT_ID": Section.SIGN_IN,
        "INSTALL_STAFF_SOURCE": Section.STAFF,
        "INSTALL_STAFF_SOURCE_LOCATION": Section.STAFF,
        "INSTALL_OBJECT_STORE_URL": Section.FILES,
        "INSTALL_OBJECT_STORE_PREFIX": Section.FILES,
        "INSTALL_OBJECT_STORE_BACKEND": Section.FILES,
        "INSTALL_LARK_USES": Section.LARK,
        "INSTALL_LARK_PLATFORM": Section.LARK,
        "INSTALL_LARK_BASE": Section.LARK,
    }
)

#: Each setting as a person calls it. The variable's name is drawn beside it, small, for support.
LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "INSTALL_COMPANY_NAME": "Company name",
        "INSTALL_PRODUCT_NAME": "What the company calls this system",
        "INSTALL_LOGO_URL": "Logo address",
        "INSTALL_ACCENT_COLOUR": "Accent colour",
        "INSTALL_SENDER_ADDRESS": "Address notifications come from",
        "INSTALL_LOCALES": "Languages offered",
        "INSTALL_CURRENCY": "Currency",
        "INSTALL_TIME_ZONE": "Time zone",
        "INSTALL_MODEL_PROFILE": "Where answers are made",
        "INSTALL_MODEL_ENDPOINT": "Model server address",
        "INSTALL_EMBEDDING_DIMENSIONS": "Search index width",
        "INSTALL_EMBEDDING_REVISION": "Search model version",
        "INSTALL_VECTOR_STORE": "Where the search index is kept",
        "INSTALL_OIDC_ISSUER": "Sign-in address",
        "INSTALL_OIDC_REALM": "Sign-in realm",
        "INSTALL_OIDC_CLIENT_ID": "Console's sign-in name",
        "INSTALL_OIDC_REDIRECT_URIS": "Addresses sign-in returns to",
        "INSTALL_BROKERED_DIRECTORY": "Company directory used for sign-in",
        "INSTALL_BROKERED_CLIENT_ID": "App registered with that directory",
        "INSTALL_STAFF_SOURCE": "Where the staff list comes from",
        "INSTALL_STAFF_SOURCE_LOCATION": "Where that staff list is",
        "INSTALL_OBJECT_STORE_URL": "File store address",
        "INSTALL_OBJECT_STORE_PREFIX": "Folder in the file store",
        "INSTALL_OBJECT_STORE_BACKEND": "Kind of file store",
        "INSTALL_LARK_USES": "What Lark is used for",
        "INSTALL_LARK_PLATFORM": "Lark or Feishu",
        "INSTALL_LARK_BASE": "Lark Base that is read",
    }
)

#: The settings this screen writes. See `WHAT_IS_CHANGED_HERE_AND_WHAT_IS_NOT`.
EDITABLE_SETTINGS: Final[frozenset[str]] = frozenset(
    {
        "INSTALL_COMPANY_NAME",
        "INSTALL_PRODUCT_NAME",
        "INSTALL_LOGO_URL",
        "INSTALL_ACCENT_COLOUR",
        "INSTALL_SENDER_ADDRESS",
        "INSTALL_LOCALES",
        "INSTALL_CURRENCY",
        "INSTALL_TIME_ZONE",
        "INSTALL_MODEL_PROFILE",
    }
)

_INSTALLER: Final = "Changed only with the installer, then a restart: "
_ENVIRONMENT_FILE: Final = "Set in the environment file, then a restart: "
_LARK: Final = (
    "Changed with Connect Lark on Connectors, which keeps the app's key in the vault before "
    "anything is switched on."
)
_STORE: Final = "every stored file still names the old place, so changing it loses track of them."

#: Why each setting this screen does not write is read only, in one line an owner can act on. A
#: test holds this and `EDITABLE_SETTINGS` to the declaration: every setting is one or the other.
READ_ONLY_BECAUSE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "INSTALL_OIDC_ISSUER": f"{_INSTALLER}a wrong value signs nobody in, including you.",
        "INSTALL_OIDC_REALM": (
            f"{_INSTALLER}the realm is created under this name, and another is a realm nobody "
            "signs in to."
        ),
        "INSTALL_OIDC_CLIENT_ID": (
            f"{_INSTALLER}the console signs in under this name, and another is refused."
        ),
        "INSTALL_OIDC_REDIRECT_URIS": (
            f"{_INSTALLER}sign-in returns only to these addresses, and a wrong one strands "
            "people after they sign in."
        ),
        "INSTALL_BROKERED_DIRECTORY": (
            f"{_INSTALLER}the sign-in service is set up from it, and the two must change together."
        ),
        "INSTALL_BROKERED_CLIENT_ID": (
            f"{_INSTALLER}the sign-in service is set up from it, and the two must change together."
        ),
        "INSTALL_STAFF_SOURCE": (
            "Changed on Staff sources, which checks the list can be read before it is used."
        ),
        "INSTALL_STAFF_SOURCE_LOCATION": (
            "Changed on Staff sources, which checks the list can be read before it is used."
        ),
        "INSTALL_MODEL_ENDPOINT": (
            f"{_ENVIRONMENT_FILE}every document's text is sent here, so it is set with the server "
            "and the private network that keeps that text inside the company."
        ),
        "INSTALL_EMBEDDING_DIMENSIONS": (
            f"{_ENVIRONMENT_FILE}it is fixed once the first document is stored, and changing it "
            "means indexing every document again."
        ),
        "INSTALL_EMBEDDING_REVISION": (
            f"{_ENVIRONMENT_FILE}it must name the version the model server holds, and a wrong one "
            "stops new documents being indexed."
        ),
        "INSTALL_VECTOR_STORE": (
            f"{_ENVIRONMENT_FILE}changing it points search at a store that holds none of the "
            "company's documents."
        ),
        "INSTALL_OBJECT_STORE_URL": f"{_ENVIRONMENT_FILE}{_STORE}",
        "INSTALL_OBJECT_STORE_PREFIX": f"{_ENVIRONMENT_FILE}{_STORE}",
        "INSTALL_OBJECT_STORE_BACKEND": f"{_ENVIRONMENT_FILE}{_STORE}",
        "INSTALL_LARK_USES": _LARK,
        "INSTALL_LARK_PLATFORM": _LARK,
        "INSTALL_LARK_BASE": _LARK,
    }
)

#: Every module that reads each setting, as a dotted path. Held to each module's source by a test,
#: in both directions: the name is in that module, and no setting names no reader.
READ_BY: Final[Mapping[str, tuple[str, ...]]] = {
    "INSTALL_COMPANY_NAME": ("brain.install", "brain.console_static"),
    "INSTALL_PRODUCT_NAME": ("brain.install", "brain.console_static"),
    "INSTALL_LOGO_URL": ("brain.console_static",),
    "INSTALL_ACCENT_COLOUR": ("brain.console_static",),
    "INSTALL_SENDER_ADDRESS": ("brain.notification_routes",),
    "INSTALL_OIDC_ISSUER": ("brain.identity.keycloak_tokens", "brain.console_static"),
    "INSTALL_OIDC_REALM": (
        "brain.ops.realm_import",
        "brain.ops.handover_run",
        "brain.settings_routes",
    ),
    "INSTALL_OIDC_CLIENT_ID": ("brain.console_static", "brain.ops.realm_import"),
    "INSTALL_OIDC_REDIRECT_URIS": ("brain.ops.realm_import",),
    "INSTALL_BROKERED_DIRECTORY": ("brain.adoption", "brain.ops.realm_import"),
    "INSTALL_BROKERED_CLIENT_ID": ("brain.ops.realm_import",),
    "INSTALL_STAFF_SOURCE": ("brain.identity.staff_source", "brain.ops.realm_import"),
    "INSTALL_STAFF_SOURCE_LOCATION": ("brain.identity.staff_source", "brain.ops.realm_import"),
    "INSTALL_MODEL_PROFILE": ("brain.ops.model_service", "brain.app"),
    "INSTALL_MODEL_ENDPOINT": ("brain.knowledge.embed_policy",),
    "INSTALL_EMBEDDING_DIMENSIONS": ("brain.knowledge.search",),
    "INSTALL_EMBEDDING_REVISION": ("brain.knowledge.embed_policy",),
    "INSTALL_OBJECT_STORE_URL": ("brain.ops.object_store",),
    "INSTALL_OBJECT_STORE_PREFIX": ("brain.ops.object_store", "brain.ops.handover_run"),
    "INSTALL_OBJECT_STORE_BACKEND": ("brain.ops.object_store",),
    "INSTALL_VECTOR_STORE": ("brain.knowledge.search",),
    "INSTALL_LOCALES": ("brain.locale",),
    "INSTALL_CURRENCY": ("brain.locale",),
    "INSTALL_TIME_ZONE": ("brain.locale",),
    "INSTALL_LARK_USES": ("brain.lark_connect_routes",),
    "INSTALL_LARK_PLATFORM": ("brain.lark_connect_routes",),
    "INSTALL_LARK_BASE": ("brain.lark_connect_routes",),
}

#: How a Keycloak issuer ends: the realm's name is its last path segment.
_REALM_IN_ISSUER: Final = re.compile(r"/realms/([^/]+)/?$")

#: Control characters, refused in a name that is drawn in a page header.
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")


class Source(enum.StrEnum):
    """Where a setting's current value came from, in `brain.install.value_of`'s order."""

    SAVED = "saved"
    ENVIRONMENT = "environment"
    DEFAULT = "default"
    #: A required setting neither source carries.
    MISSING = "missing"


@dataclass(frozen=True)
class Resolved:
    """One setting's value and where it came from. `value` is empty only when `MISSING`."""

    value: str
    source: Source


def resolved(
    name: str, env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> Resolved:
    """A setting's value and its source, never raising for a required setting nobody supplied.

    The same order `value_of` applies, asked of the same two sources, and held to `value_of` by a
    test. Not a second reader of the environment: `env` and `saved` default to the mappings
    `brain.settings.process_environment` and `brain.install.saved_values` hand every reader.
    """
    declared = BY_NAME[name]
    answered = (saved_values() if saved is None else saved).get(name, "").strip()
    if answered:
        return Resolved(answered, Source.SAVED)
    supplied = (process_environment() if env is None else env).get(name, "").strip()
    if supplied:
        return Resolved(supplied, Source.ENVIRONMENT)
    if declared.required:
        return Resolved("", Source.MISSING)
    return Resolved(declared.default, Source.DEFAULT)


def shown(value: str) -> str:
    """A value as the screen may show it: a URL without its user information, query or fragment.

    Each comma-separated part is judged on its own, because the redirect URIs are a list. A part
    that is not an absolute URL is shown as written. See
    `A_URL_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL`.
    """
    return ",".join(_shown_part(part) for part in value.split(","))


def _shown_part(part: str) -> str:
    try:
        parts = urlsplit(part.strip())
        port = parts.port
    except ValueError:
        return "(an address that cannot be read)"
    if not parts.scheme or not parts.hostname:
        return part
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


@dataclass(frozen=True)
class Row:
    """One setting as the screen draws it."""

    name: str
    group: Belongs
    meaning: str
    value: str
    source: Source
    default: str
    required: bool
    editable: bool
    applies: str
    read_by: tuple[str, ...]
    #: What the setting is for, which is where the screen draws it.
    section: Section = Section.COMPANY
    #: The setting as a person calls it.
    label: str = ""
    #: Why this screen does not change it, in one line. Empty for a setting it changes.
    read_only_because: str = ""


def row_for(
    one: Setting, env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> Row:
    """One declared setting, resolved and shown."""
    found = resolved(one.name, env, saved)
    editable = one.name in EDITABLE_SETTINGS
    if found.source is Source.MISSING:
        applies = A_REQUIRED_SETTING_NOBODY_SUPPLIED
    elif editable:
        applies = A_VALUE_SAVED_HERE_APPLIES_HERE_AT_ONCE_IN_THE_WORKER_WITHIN_A_MINUTE
    elif found.source is Source.SAVED:
        applies = A_SAVED_VALUE_APPLIES_AT_ONCE_HERE_AND_ON_RESTART_ELSEWHERE
    else:
        applies = AN_ENVIRONMENT_VALUE_CHANGES_ON_RESTART
    return Row(
        name=one.name,
        group=one.belongs,
        meaning=one.meaning,
        value=shown(found.value),
        source=found.source,
        default=one.default,
        required=one.required,
        editable=editable,
        applies=applies,
        read_by=READ_BY.get(one.name, ()),
        section=SECTION_OF[one.name],
        label=LABELS[one.name],
        read_only_because="" if editable else READ_ONLY_BECAUSE[one.name],
    )


def rows(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> tuple[Row, ...]:
    """Every declared setting, in `SECTION_ORDER`, declaration order inside a section."""
    return tuple(
        row_for(one, env, saved)
        for section in SECTION_ORDER
        for one in INSTALLATION
        if SECTION_OF[one.name] is section
    )


def profile_told(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> str:
    """What the model profile means for where text goes, in `brain.models.assembly`'s own rule."""
    profile = resolved("INSTALL_MODEL_PROFILE", env, saved).value
    if local_only(profile):
        told = (
            f"The profile is {profile!r}, so no text leaves this install: every hosted provider "
            "is skipped whatever the Models screen switches, and questions go to the inference "
            "server alone."
        )
        return (
            told if local_model_answers() else f"{told} {LOCAL_PROFILE_HAS_NO_MODEL_THAT_ANSWERS}"
        )
    return (
        f"The profile is {profile!r}, so a hosted provider the Models screen switches on may be "
        "sent text."
    )


# -------------------------------------------------------------------------------- findings


def realm_of(issuer: str) -> str:
    """The realm an issuer names, or empty when it is not shaped like a Keycloak issuer."""
    matched = _REALM_IN_ISSUER.search(issuer.strip())
    return matched.group(1) if matched else ""


def findings(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """What is inconsistent about this install's configuration, in sentences an owner can act on.

    Two checks that no other module makes. The realm must be the one the issuer names, because the
    installer creates the realm under `INSTALL_OIDC_REALM` and the application verifies tokens
    against the issuer, so a difference is a realm nobody signs in to. The vector store must be one
    this release builds, because any other value names a store nothing writes to.
    """
    found: list[str] = []
    issuer = resolved("INSTALL_OIDC_ISSUER", env, saved)
    realm = resolved("INSTALL_OIDC_REALM", env, saved).value
    if issuer.source is not Source.MISSING:
        named = realm_of(issuer.value)
        if not named:
            found.append(
                "INSTALL_OIDC_ISSUER does not end in /realms/<realm>, so which realm it signs "
                "people in against cannot be checked against INSTALL_OIDC_REALM."
            )
        elif named != realm:
            found.append(
                f"INSTALL_OIDC_ISSUER names the realm {named!r} and INSTALL_OIDC_REALM is "
                f"{realm!r}. The installer creates the second and tokens are checked against "
                "the first, so one of them is wrong."
            )
    if refused := vector_store_refusal(env, saved):
        found.append(refused)
    if problem := brokered(env, saved).problem:
        found.append(problem)
    return tuple(found)


def local_model_answers() -> bool:
    """Whether the inference server this release declares serves the model a local rung asks for.

    The name the default ladder writes against the names `brain.ops.inference` declares, so this
    turns true on the day a completion model is added there and nobody has to remember this.
    """
    return LOCAL_COMPLETION_MODEL in {one.name for one in SERVED_MODELS}


# ---------------------------------------------------------------------------- the edits


def setting_problem(name: str, value: str) -> str:
    """What is wrong with a value somebody typed for a setting, or empty when it may be saved.

    Each setting is judged by its own rule, and one that is not changed on this screen is refused
    with the same sentence whatever it is. A sentence rather than a code, because this screen is
    English only today, like every other administration screen, and the sentence says what to
    type instead.
    """
    declared = BY_NAME.get(name)
    if declared is None or name not in EDITABLE_SETTINGS:
        return f"{name} is not changed on this screen."
    written = value.strip()
    if not written:
        return "Type a value. To go back to the default, type the default."
    if len(written) > MAX_BRANDING_CHARS:
        return f"Keep it to {MAX_BRANDING_CHARS} characters."
    if _CONTROL.search(written):
        return "Remove the line break or control character."
    if name == "INSTALL_LOGO_URL":
        return _logo_problem(written)
    if name == "INSTALL_ACCENT_COLOUR":
        try:
            accent_set(written)
        except LocaleError:
            return "Write the colour as # followed by six hexadecimal digits, like #2563eb."
        return ""
    if name == "INSTALL_SENDER_ADDRESS":
        return _address_problem(written)
    if name == "INSTALL_LOCALES":
        return _locales_problem(written)
    if name == "INSTALL_CURRENCY":
        return _currency_problem(written)
    if name == "INSTALL_TIME_ZONE":
        return _zone_problem(written)
    if name == "INSTALL_MODEL_PROFILE" and written not in MODEL_PROFILES:
        return (
            f"Choose {LOCAL_PROFILE}, to keep answers on this server, or {HOSTED_PROFILE}, to "
            "allow online providers."
        )
    return ""


def normalised(name: str, value: str) -> str:
    """The value as it is saved: trimmed, and a currency code in capitals, as ISO 4217 writes it."""
    written = value.strip()
    return written.upper() if name == "INSTALL_CURRENCY" else written


def _locales_problem(value: str) -> str:
    shipped = ", ".join(SHIPPED_TAGS)
    tags = [one.strip() for one in value.split(",") if one.strip()]
    try:
        for one in tags:
            rules_for(one)
    except LocaleError:
        tags = []
    if not tags:
        return f"Use language tags this product ships, separated by commas: {shipped}."
    return ""


def _currency_problem(value: str) -> str:
    code = value.strip().upper()
    if not CURRENCY_PATTERN.match(code) or code == UNSET_CURRENCY:
        return "Type the currency's three-letter code, like SGD, USD or EUR."
    return ""


def _zone_problem(value: str) -> str:
    try:
        ZoneInfo(value.strip())
    except (KeyError, ValueError, OSError):
        # `zoneinfo`'s three ways of saying the same thing, as `brain.locale.time_zone` reads them.
        return "Type a time zone name, like Asia/Singapore or Europe/London."
    return ""


def _logo_problem(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "Give the logo's full address, beginning with https and a host."
    if parts.scheme != "https" or not parts.hostname:
        return "Give the logo's full address, starting https://, or a path on this install."
    if parts.username or parts.password or parts.query:
        return "Give the logo's address without a user name, password or query."
    return ""


def _address_problem(value: str) -> str:
    from brain.identity.staff_source import StaffRecord

    try:
        StaffRecord(work_address=value, display_name=value)
    except ValueError:
        return "Give one email address, like no-reply@example.com."
    return ""
