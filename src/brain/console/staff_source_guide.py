"""How to connect each kind of staff source, step by step, in the Staff sources screen's words.

The owner asked for the staff source to be connected from the console, with "full steps from backend
to see how to add", and for other companies to be able to choose their own source. This module is
those steps and the fields each source asks for, as data. It is product text, the same on every
install: it names each vendor's console and the permissions to grant there, and never a company, a
tenant, an application or a value. Anything a company fills in arrives through the fields below and
goes to configuration (the location, saved as `INSTALL_STAFF_SOURCE_LOCATION`) or to the vault (the
credential), never into this file.

**A guide says whether its source can be connected on this version, and it asks the registry rather
than keeping a list.** A source can be connected when `brain.ops.staff_sync_run.READERS` has a
reader for it, because a connection nothing reads at night is a form that saves a secret for nobody.
So Lark, Microsoft Entra and a Google Sheet are connectable today, and LDAP becomes connectable on
the day a reader for it is registered, with nothing here changing. See
`A_SOURCE_NOTHING_READS_AT_NIGHT_IS_NOT_OFFERED_AS_CONNECTABLE`.

**The credential is assembled from its fields in one place, and the order is the reader's.** Lark
and Microsoft keep `<identifier>:<secret>`, which is `brain.ops.staff_sync_run.client_credential`'s
form; a Google Sheet keeps its API key alone. `credential_fields` names which fields make it up, so
the screen, the test and the save cannot disagree about what is kept.

Rejected: writing the steps in the console. The setup wizard and this screen both show them, and a
second copy in a browser is the copy that goes stale when a vendor renames a menu.

Rejected: the wizard's sign-in pop-up for the scheduled sources. A nightly run has nobody signed in,
so what it reads with is the application's own credential, and that is what these steps produce.

Task ids: M27.7.2, M1.8.6
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from brain.connectors.staff_directories import LARK_PLATFORMS, LARK_SCOPES
from brain.identity.staff_adapters import (
    ADDRESS_COLUMNS,
    DEPARTED_COLUMNS,
    DEPARTMENT_COLUMNS,
    GOOGLE_SHEET,
    GOOGLE_WORKSPACE,
    LARK,
    LDAP,
    MICROSOFT_ENTRA,
    NAME_COLUMNS,
)
from brain.identity.staff_source import SELECTABLE_BY_NAME
from brain.ops.staff_sync_run import CLIENT_CREDENTIAL_SEPARATOR, READERS

#: Why a source with no nightly reader is shown with its steps and without a connect button.
A_SOURCE_NOTHING_READS_AT_NIGHT_IS_NOT_OFFERED_AS_CONNECTABLE: Final = (
    "Connecting a source keeps its credential for the nightly staff sync and points the sync at "
    "it. A source the sync has no reader for would be saved, tested by nothing and read by "
    "nobody, and the first sign would be a run every night saying so. So the guide is still "
    "shown, because somebody choosing a source wants to know what it will take, and the connect "
    "button is not, with the reason in words."
)

#: The key every guide uses for where its list is. Saved as `INSTALL_STAFF_SOURCE_LOCATION`.
LOCATION: Final = "location"


@dataclass(frozen=True)
class GuideField:
    """One box the person fills in. `secret` fields are sent once and never shown back."""

    key: str
    label: str
    help: str
    secret: bool = False
    example: str = ""


@dataclass(frozen=True)
class Guide:
    """Everything the screen shows for one kind of staff source."""

    source: str
    title: str
    #: Where the steps happen, as the vendor's own address or console name.
    where: str
    steps: tuple[str, ...]
    fields: tuple[GuideField, ...]
    #: The fields the kept credential is made of, in the order the reader splits them.
    credential_fields: tuple[str, ...]
    #: Said when this version cannot connect the source, whatever the registry says.
    held_back: str = ""

    def __post_init__(self) -> None:
        keys = [one.key for one in self.fields]
        if len(set(keys)) != len(keys):
            msg = f"{self.source!r} asks for the same field twice, so one answer would be lost"
            raise ValueError(msg)
        if self.source not in SELECTABLE_BY_NAME:
            msg = f"{self.source!r} is not a staff source an install can choose"
            raise ValueError(msg)
        secrets = {one.key for one in self.fields if one.secret}
        if not set(self.credential_fields) <= set(keys):
            msg = f"{self.source!r} builds its credential from a field it does not ask for"
            raise ValueError(msg)
        if secrets - set(self.credential_fields):
            # A secret field outside the credential would be sent to the save and kept nowhere,
            # or kept somewhere this module does not name. Neither is acceptable for a secret.
            msg = f"{self.source!r} asks for a secret that is not part of what the vault keeps"
            raise ValueError(msg)
        if LOCATION in self.credential_fields:
            msg = f"{self.source!r} would keep its location in the vault, where nobody can read it"
            raise ValueError(msg)

    @property
    def connectable(self) -> bool:
        """Whether this version can connect the source: a nightly reader exists for it."""
        return not self.held_back and self.source in READERS

    @property
    def unavailable(self) -> str:
        """Why this version cannot connect the source, in words, or the empty string."""
        if self.connectable:
            return ""
        if self.held_back:
            return self.held_back
        return (
            "This version has no nightly reader for this source yet, so it cannot be connected "
            "here. The steps are shown so you know what it will take."
        )

    def credential_from(self, values: Mapping[str, str]) -> str:
        """The value the vault keeps, assembled from the fields in the reader's order."""
        return CLIENT_CREDENTIAL_SEPARATOR.join(
            values.get(one, "").strip() for one in self.credential_fields
        )


def _columns(names: tuple[str, ...]) -> str:
    return " or ".join(f'"{one.title()}"' for one in names[:2])


#: The five sources a company connects from the console, in the order the screen offers them.
GUIDES: Final[tuple[Guide, ...]] = (
    Guide(
        source=LARK,
        title="Lark (or Feishu)",
        where="open.larksuite.com/app (Feishu: open.feishu.cn/app)",
        steps=(
            "Sign in to open.larksuite.com/app with a Lark account that administers your "
            "company. For Feishu, use open.feishu.cn/app instead.",
            'Click "Create Custom App", give it a name such as "Company Brain staff sync" and '
            "create it. If you already made one for this, open that one instead.",
            'In the app, open "Permissions & Scopes". Search for and add each of these scopes: '
            + ", ".join(LARK_SCOPES.split())
            + ". The first and last read people and departments; the other two are what let "
            "the sync read each person's work email and which department they are in.",
            'On the same page, set the data range (it may be called "Range of contact data '
            'accessible") to "All members", so the app can see everybody who should be listed.',
            'Open "Version Management & Release", create a version and release it. If your '
            "company asks for approval, a Lark administrator approves it in the Lark admin "
            "console. Scopes and the data range only take effect once a version is released.",
            'Open "Credentials & Basic Info" and copy the App ID and the App Secret.',
            "Paste them below, choose larksuite.com for Lark or feishu.cn for Feishu, and press "
            '"Test connection". Nothing is saved by a test.',
        ),
        fields=(
            GuideField(
                key=LOCATION,
                label="Platform",
                help=f"Type one of: {', '.join(LARK_PLATFORMS)}.",
                example="larksuite.com",
            ),
            GuideField(
                key="app_id",
                label="App ID",
                help='From "Credentials & Basic Info". It starts with cli_.',
                example="cli_a1b2c3d4e5f6",
            ),
            GuideField(
                key="app_secret",
                label="App Secret",
                help='From "Credentials & Basic Info". Kept in the vault and never shown again.',
                secret=True,
            ),
        ),
        credential_fields=("app_id", "app_secret"),
    ),
    Guide(
        source=MICROSOFT_ENTRA,
        title="Microsoft Entra ID (Microsoft 365)",
        where="entra.microsoft.com",
        steps=(
            "Sign in to entra.microsoft.com as an administrator of your organisation.",
            'Go to "Applications", then "App registrations", then "New registration". Name it '
            'something such as "Company Brain staff sync", choose "Accounts in this '
            'organizational directory only", and register it. No redirect address is needed.',
            'Open "API permissions", "Add a permission", "Microsoft Graph", "Application '
            'permissions", and add User.Read.All. Then press "Grant admin consent for" your '
            "organisation. Application, not delegated: the nightly sync runs with nobody "
            "signed in.",
            'Open "Certificates & secrets", "New client secret", choose how long it lasts and '
            'add it. Copy the secret\'s "Value" straight away (not the "Secret ID"): Microsoft '
            "shows it only once.",
            'Open "Overview" and copy the "Application (client) ID" and the "Directory (tenant) '
            'ID".',
            'Paste the three below and press "Test connection". Nothing is saved by a test. '
            "Before the secret expires, make a new one and replace it on this screen.",
        ),
        fields=(
            GuideField(
                key=LOCATION,
                label="Directory (tenant) ID",
                help="From the app's Overview page, or your tenant's primary domain.",
                example="00000000-0000-0000-0000-000000000000",
            ),
            GuideField(
                key="client_id",
                label="Application (client) ID",
                help="From the app's Overview page.",
                example="00000000-0000-0000-0000-000000000000",
            ),
            GuideField(
                key="client_secret",
                label="Client secret value",
                help="The secret's Value. Kept in the vault and never shown again.",
                secret=True,
            ),
        ),
        credential_fields=("client_id", "client_secret"),
    ),
    Guide(
        source=GOOGLE_WORKSPACE,
        title="Google Workspace",
        where="console.cloud.google.com and admin.google.com",
        steps=(
            "In console.cloud.google.com, in a project that belongs to your company, enable the "
            "Admin SDK API.",
            "Create a service account in that project and a JSON key for it.",
            "In admin.google.com, under Security, API controls, Domain-wide delegation, add the "
            "service account's client ID with the scope "
            "https://www.googleapis.com/auth/admin.directory.user.readonly.",
            "Note the address of a Workspace administrator the service account will act as, and "
            "your primary domain.",
        ),
        fields=(),
        credential_fields=(),
        held_back=(
            "Google Workspace cannot be connected for the nightly sync on this version: reading "
            "it with nobody signed in needs the service account's key to sign each request on "
            "this server, which this version does not do yet. Until it does, keep your staff "
            "list in a Google Sheet (export it from the admin console) and connect that, or read "
            "it once during setup by signing in."
        ),
    ),
    Guide(
        source=GOOGLE_SHEET,
        title="Google Sheet",
        where="sheets.google.com and console.cloud.google.com",
        steps=(
            "Put your staff list in a Google Sheet with a header row. The sync reads a column "
            f"named {_columns(ADDRESS_COLUMNS)} for each person's work address, "
            f"{_columns(NAME_COLUMNS)} for their name, {_columns(DEPARTMENT_COLUMNS)} for their "
            f"department, and {_columns(DEPARTED_COLUMNS)} to mark somebody who has gone.",
            'Press "Share", and under "General access" choose "Anyone with the link" as a '
            '"Viewer". The sheet is read with an API key, which can only read a sheet shared '
            "this way; anyone with its link can open it, so share nothing else in it.",
            "Copy the sheet's ID: the long part of its address between /d/ and /edit.",
            "In console.cloud.google.com, in a project that belongs to your company, open "
            '"APIs & Services", enable the "Google Sheets API", then under "Credentials" choose '
            '"Create credentials", "API key". Restrict the key to the Google Sheets API.',
            'Paste the sheet ID and the API key below and press "Test connection". Nothing is '
            "saved by a test.",
        ),
        fields=(
            GuideField(
                key=LOCATION,
                label="Sheet ID",
                help="The part of the sheet's address between /d/ and /edit.",
                example="1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            ),
            GuideField(
                key="api_key",
                label="API key",
                help="Restricted to the Google Sheets API. Kept in the vault, never shown again.",
                secret=True,
            ),
        ),
        credential_fields=("api_key",),
    ),
    Guide(
        source=LDAP,
        title="LDAP or Active Directory",
        where="your directory server",
        steps=(
            "Create a service account in your directory that may read users and groups and "
            "nothing else, with a password that does not expire without warning.",
            "Use its user principal name (such as staff-sync@example.com) as the bind user. A "
            "distinguished name with spaces in it cannot be kept as a credential.",
            "Note your directory's address with the base the search starts from, such as "
            "ldaps://dc1.example.com:636/dc=example,dc=com. Use ldaps so the password is never "
            "sent in the clear.",
            "Allow this server to reach the directory on that port.",
            'Fill in the three boxes below and press "Test connection". Nothing is saved by a '
            "test.",
        ),
        fields=(
            GuideField(
                key=LOCATION,
                label="Directory address and base",
                help="ldaps://, the host and port, then the base to search from.",
                example="ldaps://dc1.example.com:636/dc=example,dc=com",
            ),
            GuideField(
                key="bind_user",
                label="Bind user",
                help="The service account's user principal name.",
                example="staff-sync@example.com",
            ),
            GuideField(
                key="bind_password",
                label="Bind password",
                help="Kept in the vault and never shown again.",
                secret=True,
            ),
        ),
        credential_fields=("bind_user", "bind_password"),
    ),
)

#: The same, by source name.
GUIDE_BY_SOURCE: Final[Mapping[str, Guide]] = {one.source: one for one in GUIDES}


def guide_for(source: str) -> Guide | None:
    """The guide for one source, or None for a source this screen does not connect."""
    return GUIDE_BY_SOURCE.get(source)


def field_problems(guide: Guide, values: Mapping[str, str]) -> tuple[str, ...]:
    """What is missing or unexpected in what the person filled in, in words. Never a value.

    An unexpected key is refused rather than ignored, for `NoEchoRoute`'s reason one layer up: a
    box the screen did not draw is a value nobody meant to send, and on a form holding a secret
    the one that is silently dropped is the one somebody pasted in the wrong place.
    """
    asked = {one.key: one for one in guide.fields}
    found = [
        f'"{asked[key].label}" is empty.'
        for key in (one.key for one in guide.fields)
        if not values.get(key, "").strip()
    ]
    if set(values) - set(asked):
        # Not named: a refusal never repeats what the person sent, which is `NoEchoRoute`'s rule.
        found.append("The form carried a box this source does not ask for.")
    return tuple(found)
