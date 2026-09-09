"""Everything about one installation that belongs to the client rather than to the product.

The premise of this system is that a client hosts it themselves and owns what is inside it.
That premise survives exactly as long as the repository does not quietly learn who the first
client is, and repositories learn that the same way every time: a product name in a page
title, a publisher slug in a catalogue, a domain in a default, a bucket path in a compose
file. None of those is a mistake when it is written. Each one is written by somebody with one
deployment in front of them, and the second deployment is where they all surface at once.

**So the distinction here is not "configured" against "hardcoded".** A database password is
configured and is not client-specific in the sense that matters: every install has one and it
says nothing about who the client is. `PUBLISHER = "verz"` is a literal and is exactly
client-specific. The line runs between what belongs to the product and what belongs to the
installation, and only a declaration can draw it, because no amount of reading the code tells
you which side a string is on.

`INSTALLATION` is that declaration: every value that belongs to the client, what it means, its
neutral default, and whether the system may start without it.

**The defaults are deliberately nobody's.** A default of "Verz Company Brain" would make this
module a description of one deployment wearing the clothes of a template, which is the state
M41 exists to prevent. The defaults name the product, and this installation's values live in
a per-install environment file that is not in this repository.

**One reader, and that is the load-bearing rule.** `value_of` is the only place an
installation value is read from the environment, and `independence_gaps` fails when any other
module reads one. Two readers means two defaults, and the one that is wrong is the one nobody
looked at. The rule is narrow on purpose: this is not a ban on reading the environment, which
`ops.worker` and `ops.schema_check` legitimately do for operational settings. It is a ban on a
second module deciding what this client is called.

**What a refusal costs, and why some values still have none.** A value with no safe default
refuses at startup rather than defaulting, because `KEYCLOAK_ISSUER` guessed wrong is a
sign-in page that redirects to somebody else's identity provider, and an empty string is a
perfectly valid string. A value that has a safe neutral default takes it, because refusing to
start over an unset logo would make the safe configuration the one that fails.

Task ids: M41.1.2, M41.1.3, M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.3.1, M41.3.4
"""

from __future__ import annotations

import enum
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

#: Why a second reader is worse than a second literal.
ONE_READER_OR_TWO_DEFAULTS: Final = (
    "A client-specific value read in two places has two defaults, and the wrong one is the "
    "one nobody looked at. A literal at least shows up in a grep; a second reader with its "
    "own fallback agrees with the first on every machine where both are set, which is every "
    "machine except the new client's."
)

#: Why the defaults here are nobody's.
A_TEMPLATE_WHOSE_DEFAULTS_ARE_ONE_CLIENTS_IS_A_COPY_OF_THAT_CLIENT: Final = (
    "Defaulting the product name to the first client's makes this module a description of one "
    "deployment wearing the clothes of a template. The second install then starts branded as "
    "the first, which is a support call at best and a disclosure at worst, because the person "
    "who sees it has no reason to think the name is wrong."
)

#: Why an unset issuer stops the boot and an unset logo does not.
A_GUESSED_IDENTITY_PROVIDER_IS_WORSE_THAN_A_STOPPED_ONE: Final = (
    "An issuer guessed wrong is a sign-in page that redirects to somebody else's identity "
    "provider, and an empty string is a perfectly valid string, so the failure is a login "
    "screen that works and authenticates against nothing this install controls. There is no "
    "safe default for that, and refusing to start is the smallest failure available."
)


class Belongs(enum.StrEnum):
    """Which part of the installation a value describes.

    The groups are the ones M41 names, and they are not decoration: each is a separate
    surface a client hands over on install day, and each is asked for by a different person.
    Branding comes from marketing, the identity provider from whoever runs their directory,
    storage from whoever runs their infrastructure.
    """

    BRANDING = "branding"
    IDENTITY = "identity"
    MODELS = "models"
    STORAGE = "storage"
    #: Language, currency and time zone. Its own surface rather than part of branding,
    #: because the person who owns the brand is not the person who knows where the staff sit
    #: and what they read, and asking one of them for the other's answer is how an install
    #: ends up rendering every date in the zone the implementer happened to be in.
    LOCALE = "locale"


@dataclass(frozen=True)
class Setting:
    """One client-specific value: what it is called, what it means, and what happens without it.

    `meaning` is required and is not a comment. It is what the install runbook prints and what
    somebody setting this value on a client's server reads, and a setting nobody can explain
    is one they will guess at.
    """

    #: The environment variable, spelled as it is set.
    name: str
    #: Which surface this belongs to.
    belongs: Belongs
    #: What it is, in a sentence, for whoever has to supply it.
    meaning: str
    #: The neutral value used when nothing is set. Empty only for a required setting.
    default: str = ""
    #: True when there is no safe default and the system must refuse to start without it.
    required: bool = False

    def __post_init__(self) -> None:
        if not self.name.isupper() or not self.name.replace("_", "").isalnum():
            msg = f"{self.name!r} is not an environment variable name"
            raise ValueError(msg)
        if not self.meaning.strip():
            msg = (
                f"{self.name} has no meaning written down, and a setting nobody can explain "
                "is one somebody guesses at on a client's server"
            )
            raise ValueError(msg)
        if self.required and self.default:
            msg = (
                f"{self.name} is required and also carries a default, which means it can "
                "never refuse: the default answers first and the refusal is unreachable"
            )
            raise ValueError(msg)
        if not self.required and not self.default:
            msg = (
                f"{self.name} is optional with an empty default, so an unset value and a "
                "value set to nothing are the same thing and neither is reported"
            )
            raise ValueError(msg)


#: Every value that belongs to the client rather than to the product.
#:
#: Adding one here is what makes it configurable; `independence_gaps` refuses a module that
#: reads it anywhere else, and the sweep refuses a literal that looks like one.
INSTALLATION: Final[tuple[Setting, ...]] = (
    # --- branding, M41.1.4
    Setting(
        name="INSTALL_COMPANY_NAME",
        belongs=Belongs.BRANDING,
        meaning="The client's own name, as it should appear to their staff on every screen.",
        default="Your Company",
    ),
    Setting(
        name="INSTALL_PRODUCT_NAME",
        belongs=Belongs.BRANDING,
        meaning=(
            "What the client calls this system internally. Separate from the company name "
            "because several clients rename it, and the page title is the two together."
        ),
        # "Brain" rather than "Company Brain", because the two are concatenated and the
        # unconfigured title came out as "Your Company Company Brain". Composing beats
        # repeating: an install that changes nothing reads "Your Company Brain", and one that
        # sets its own name reads "Acme Brain" or "Acme Knowledge Desk".
        default="Brain",
    ),
    Setting(
        name="INSTALL_LOGO_URL",
        belongs=Belongs.BRANDING,
        meaning="An absolute URL to the client's logo, served from somewhere they control.",
        default="/static/logo.svg",
    ),
    Setting(
        name="INSTALL_ACCENT_COLOUR",
        belongs=Belongs.BRANDING,
        meaning="One hex colour the console's accents are derived from.",
        default="#2563eb",
    ),
    Setting(
        name="INSTALL_SENDER_ADDRESS",
        belongs=Belongs.BRANDING,
        meaning=(
            "The address notifications come from. It has to be on a domain the client can "
            "make us a sender for, or every message they send is a deliverability problem."
        ),
        default="no-reply@localhost",
    ),
    # --- identity provider, M41.1.5
    Setting(
        name="INSTALL_OIDC_ISSUER",
        belongs=Belongs.IDENTITY,
        meaning=(
            "The issuer URL of the client's Keycloak realm. No default: see "
            "A_GUESSED_IDENTITY_PROVIDER_IS_WORSE_THAN_A_STOPPED_ONE."
        ),
        required=True,
    ),
    Setting(
        name="INSTALL_OIDC_REALM",
        belongs=Belongs.IDENTITY,
        meaning=(
            "The realm name inside that Keycloak. Part of the issuer, and asked for "
            "separately because the setup script needs it before the issuer exists."
        ),
        default="brain",
    ),
    Setting(
        name="INSTALL_OIDC_CLIENT_ID",
        belongs=Belongs.IDENTITY,
        meaning="The client id the console authenticates as. Registered in the realm above.",
        default="brain-console",
    ),
    Setting(
        name="INSTALL_OIDC_REDIRECT_URIS",
        belongs=Belongs.IDENTITY,
        meaning=(
            "Comma-separated redirect URIs the realm will accept. Wrong here is a sign-in "
            "that completes and then bounces to a page the client does not own."
        ),
        required=True,
    ),
    Setting(
        name="INSTALL_BROKERED_DIRECTORY",
        belongs=Belongs.IDENTITY,
        meaning=(
            "Which directory Keycloak brokers sign-in to: google, microsoft, lark, ldap or "
            "none. `none` means the realm holds the passwords itself."
        ),
        default="none",
    ),
    Setting(
        name="INSTALL_STAFF_SOURCE",
        belongs=Belongs.IDENTITY,
        meaning=(
            "Where this company keeps the list of who works here: spreadsheet, google_sheet, "
            "google_workspace, microsoft_entra, lark, ldap, or none. A separate question from "
            "the brokered directory above, because a roster is a list read on a schedule and "
            "a sign-in source is a live protocol, and a spreadsheet can only be the first. "
            "The default is none, meaning no list is read and people are created in the "
            "console: there is no default source because a default would make whichever "
            "company was set up first the shape every later one inherits."
        ),
        default="none",
    ),
    Setting(
        name="INSTALL_STAFF_SOURCE_LOCATION",
        belongs=Belongs.IDENTITY,
        meaning=(
            "Where that staff list is: the sheet's identifier, the directory tenant, or the "
            "directory address including the base a search starts from. `unset` is the value "
            "meaning nobody has said, so a source that was chosen and pointed nowhere refuses "
            "rather than reading a company with nobody in it."
        ),
        default="unset",
    ),
    # --- models and providers, M41.1.6
    Setting(
        name="INSTALL_MODEL_PROFILE",
        belongs=Belongs.MODELS,
        meaning=(
            "Which models this install may reach: `local` for the inference server alone, "
            "`hosted` to allow an external provider. `local` is the default because a client "
            "who has not chosen to send text off their own hardware has not chosen it."
        ),
        default="local",
    ),
    Setting(
        name="INSTALL_MODEL_ENDPOINT",
        belongs=Belongs.MODELS,
        meaning="Where the inference server answers. Inside the client's own network by default.",
        default="http://inference-server:8080",
    ),
    # --- storage, M41.1.7
    Setting(
        name="INSTALL_OBJECT_STORE_URL",
        belongs=Belongs.STORAGE,
        meaning=(
            "The S3-compatible endpoint holding assets, recordings and exports. The client's "
            "own SeaweedFS, or their S3 or R2 if they would rather."
        ),
        default="http://seaweedfs:8333",
    ),
    Setting(
        name="INSTALL_OBJECT_STORE_PREFIX",
        belongs=Belongs.STORAGE,
        meaning=(
            "The bucket or path prefix under that endpoint. Separate from the URL so two "
            "installs can share an endpoint without sharing a namespace."
        ),
        default="brain",
    ),
    Setting(
        name="INSTALL_VECTOR_STORE",
        belongs=Belongs.STORAGE,
        meaning=(
            "Where embeddings live. `postgres` means the pgvector column in the client's own "
            "database, which is the only option built today and is named so the second one "
            "is a value rather than a migration."
        ),
        default="postgres",
    ),
    # --- locale, M35.1.1
    Setting(
        name="INSTALL_LOCALES",
        belongs=Belongs.LOCALE,
        meaning=(
            "Comma-separated language tags this install offers, most preferred first. The "
            "first is what somebody with no stated preference reads. Only tags this product "
            "ships a complete catalogue for are accepted: see brain.locale.SHIPPED."
        ),
        # Every shipped catalogue, rather than English alone. Offering a language nobody
        # uses is visible and harmless; withholding one a colleague needs is invisible,
        # because nothing on the screen says the switcher could have had it.
        default="en,zh-Hans",
    ),
    Setting(
        name="INSTALL_CURRENCY",
        belongs=Belongs.LOCALE,
        meaning=(
            "The ISO 4217 code money figures are rendered in. XXX is the code meaning no "
            "currency, so an install that has not chosen one shows something visibly unset "
            "rather than a figure that reads correctly in the wrong currency."
        ),
        default="XXX",
    ),
    Setting(
        name="INSTALL_TIME_ZONE",
        belongs=Belongs.LOCALE,
        meaning=(
            "The IANA zone a timestamp is rendered in for a reader with no zone of their "
            "own. UTC by default because it is nobody's local time, so a wrong rendering is "
            "visibly wrong rather than out by an hour on some days of the year."
        ),
        default="UTC",
    ),
)

#: The declaration, indexed. Built once because `value_of` is on the read path of every page.
BY_NAME: Final[dict[str, Setting]] = {one.name: one for one in INSTALLATION}

#: The prefix every installation setting shares, so the reader check can recognise one.
INSTALL_PREFIX: Final = "INSTALL_"


class InstallError(Exception):
    """Raised when this installation has not said who it is."""


def value_of(name: str, env: Mapping[str, str] | None = None) -> str:
    """The one place an installation value is read. See `ONE_READER_OR_TWO_DEFAULTS`.

    `env` is a parameter defaulting to the real environment for the reason
    `brain.ops.admission` takes `now` rather than reading a clock: a value read through a
    module-level import cannot be tested at more than one setting.
    """
    declared = BY_NAME.get(name)
    if declared is None:
        msg = (
            f"{name!r} is not a declared installation setting. Add it to INSTALLATION with a "
            "meaning and a default, or it is not configurable and the next client inherits it"
        )
        raise InstallError(msg)

    supplied = (os.environ if env is None else env).get(name, "").strip()
    if supplied:
        return supplied
    if declared.required:
        msg = f"{name} is not set and has no safe default. {declared.meaning}"
        raise InstallError(msg)
    return declared.default


def installed_name(env: Mapping[str, str] | None = None) -> str:
    """What this installation is called, on a page title and in the API schema.

    The company and the product together, because several clients rename the product and the
    two are asked for separately. One function rather than two `value_of` calls at each site,
    so the order and the separator are decided once: a title that reads
    "Company Brain - Acme" on one page and "Acme Company Brain" on another looks like two
    systems to the person using it.
    """
    return f"{value_of('INSTALL_COMPANY_NAME', env)} {value_of('INSTALL_PRODUCT_NAME', env)}"


def belonging_to(group: Belongs, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Every value for one surface, resolved.

    Grouped because these are handed over by different people on install day: branding by
    whoever owns the brand, identity by whoever runs the directory, storage by whoever runs
    the infrastructure. A single flat map would make the runbook one long list nobody owns.

    A required value that is unset raises rather than being omitted, because a branding map
    missing a key and a branding map with an empty one are the same to a template.
    """
    return {one.name: value_of(one.name, env) for one in INSTALLATION if one.belongs is group}


def missing(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The required settings this environment has not supplied, all of them.

    All rather than the first, matching `brain.ops.worker.preflight`: an install missing two
    values has two problems, and fixing one produces a configuration that still refuses.
    """
    source = os.environ if env is None else env
    return tuple(
        one.name for one in INSTALLATION if one.required and not source.get(one.name, "").strip()
    )


#: The heading the generated block sits under in `.env.example`, and the marker that finds it.
#:
#: A marker rather than "everything after the last blank line", because the file is edited by
#: hand around this block and a positional rule breaks the first time somebody adds a comment.
ENV_BLOCK_START = "# --- this installation ----------------------------------------------------"
ENV_BLOCK_END = "# --- end of this installation ---------------------------------------------"


def env_example() -> str:
    """The installation block for `.env.example`, generated from the declaration.

    **A hand-kept list of environment variables is wrong the first time somebody adds one, and
    it is wrong by omitting the new one**, which is the direction nobody notices: the install
    team sets the fourteen that are written down and the fifteenth takes its default on a
    client's server. So the file carries a generated block and a test compares it against this,
    which makes the declaration the single source and the file its printout.

    Required settings are written with an empty value and a line saying there is no default, so
    an install team reading the file sees which ones stop the boot.
    """
    lines = [ENV_BLOCK_START]
    for group in Belongs:
        lines.append(f"# {group.value}:")
        for one in INSTALLATION:
            if one.belongs is not group:
                continue
            lines.append(f"# {one.meaning}")
            if one.required:
                lines.append("# No default. The system refuses to start without it.")
            lines.append(f"{one.name}={one.default}")
        lines.append("")
    lines.append(ENV_BLOCK_END)
    return "\n".join(lines) + "\n"


def runbook() -> str:
    """Every setting, grouped, with its meaning and default, for whoever installs this.

    Generated rather than written, because a hand-written list of environment variables is
    wrong the first time somebody adds one, and it is wrong in the direction of omitting the
    new one, which is the direction nobody notices.
    """
    lines: list[str] = []
    for group in Belongs:
        lines.append(f"# {group.value}")
        for one in INSTALLATION:
            if one.belongs is not group:
                continue
            state = "required, no default" if one.required else f"default: {one.default}"
            lines.append(f"{one.name}    ({state})")
            lines.append(f"    {one.meaning}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
