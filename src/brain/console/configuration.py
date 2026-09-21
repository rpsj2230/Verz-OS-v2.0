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

**Only branding is changed from this screen, and the reason differs per group.** Identity: an
issuer or redirect changed from a browser is a sign-in that fails for everybody including the
person who changed it, with no browser left to change it back, so it is set where the realm is.
Models: whether text may leave the install at all is the profile, chosen by the wizard, and each
hosted provider is the Models screen's switch; a second writer of either is the drift
`brain.install.ONE_READER_OR_TWO_DEFAULTS` names.
Storage: moving the object store's address moves where every file is read from while every key
still names the old one. Locale is outside the task this screen was built for and stays the
wizard's. See `ONLY_BRANDING_IS_CHANGED_HERE`.

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
from typing import Final
from urllib.parse import urlsplit, urlunsplit

from brain.install import BY_NAME, INSTALLATION, Belongs, Setting, saved_values
from brain.knowledge.search import vector_store_refusal
from brain.locale import LocaleError, accent_set
from brain.models.assembly import local_only
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

#: Why only branding is editable here.
ONLY_BRANDING_IS_CHANGED_HERE: Final = (
    "Branding is changed here because a wrong logo is visible and harmless. The identity provider "
    "is not, because a wrong issuer signs nobody in, including whoever changed it. The model "
    "profile decides where text may go and each provider is switched on the Models screen. The "
    "storage location is not, because every stored file's key still names the old place."
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

#: The groups in the order the screen draws them.
GROUP_ORDER: Final[tuple[Belongs, ...]] = (
    Belongs.BRANDING,
    Belongs.IDENTITY,
    Belongs.MODELS,
    Belongs.STORAGE,
    Belongs.LOCALE,
    Belongs.CONNECTORS,
)

#: What each group is called on the screen.
GROUP_TITLES: Final[Mapping[Belongs, str]] = {
    Belongs.BRANDING: "Branding",
    Belongs.IDENTITY: "Identity provider",
    Belongs.MODELS: "Models and providers",
    Belongs.STORAGE: "Storage locations",
    Belongs.LOCALE: "Language, currency and time zone",
    Belongs.CONNECTORS: "Connected applications",
}

#: Where a group that is not changed here is changed instead, in the console's own words.
CHANGED_ELSEWHERE: Final[Mapping[Belongs, str]] = {
    Belongs.IDENTITY: (
        "Set by the installer where the realm is created, or in the environment file, then a "
        "restart. A wrong issuer or redirect signs nobody in, including whoever changed it."
    ),
    Belongs.MODELS: (
        "Each hosted provider is switched on or off on the Models and health screen. The profile "
        "is chosen in the setup wizard or the environment file, then a restart, and so are the "
        "endpoint and the embedding figures."
    ),
    Belongs.STORAGE: (
        "Set in the environment file, then a restart. Moving the store does not move the files "
        "already in it, and every stored key still names the old place."
    ),
    Belongs.LOCALE: "Set in the setup wizard or the environment file, then a restart.",
    Belongs.CONNECTORS: (
        "Set by the Connect Lark flow on the Connectors screen, which keeps the app's credential "
        "in the vault first and switches each use on only after that."
    ),
}

#: The groups whose values this screen writes. See `ONLY_BRANDING_IS_CHANGED_HERE`.
EDITABLE_GROUPS: Final[frozenset[Belongs]] = frozenset({Belongs.BRANDING})

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


def row_for(
    one: Setting, env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> Row:
    """One declared setting, resolved and shown."""
    found = resolved(one.name, env, saved)
    if found.source is Source.MISSING:
        applies = A_REQUIRED_SETTING_NOBODY_SUPPLIED
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
        editable=one.belongs in EDITABLE_GROUPS,
        applies=applies,
        read_by=READ_BY.get(one.name, ()),
    )


def rows(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> tuple[Row, ...]:
    """Every declared setting, grouped in `GROUP_ORDER`, declaration order inside a group."""
    return tuple(
        row_for(one, env, saved)
        for group in GROUP_ORDER
        for one in INSTALLATION
        if one.belongs is group
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


def branding_problem(name: str, value: str) -> str:
    """What is wrong with a branding value somebody typed, or empty when it may be saved.

    A sentence rather than a code, because this screen is English only today, like every other
    administration screen, and the sentence says what to type instead.
    """
    declared = BY_NAME.get(name)
    if declared is None or declared.belongs not in EDITABLE_GROUPS:
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
