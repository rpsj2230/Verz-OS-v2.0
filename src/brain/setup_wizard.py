"""The install wizard: the first thing a client sees, and the only screen with no reader yet.

Every other screen in this system is read by somebody who has already been authenticated,
placed in a department and given a reach. This one is read by a stranger. There is nobody to
authorise them, nothing to narrow them to, and no administrator to appeal to, because the
whole purpose of the screen is to appoint the first one. **A fresh server with an open wizard
is a server that belongs to whoever finds the address first**, and the window is however long
it takes the client to walk to their laptop. See
`A_SERVER_WITH_AN_OPEN_WIZARD_BELONGS_TO_WHOEVER_FINDS_IT`.

**The setup code closes that window, and nothing here mints it or keeps it.** The installer
mints one value on the client's own machine and writes it into that install's environment
file: `brain.deployment.installer.PLAN`'s mint step is `openssl rand -hex 32`, and the last
step of the plan is the only step permitted to print a credential. **The owner of this
repository therefore never creates a password on a client's behalf and never holds one**,
which is a different thing from a product that ships a default and asks them to change it.
What reaches this module is a digest on an `Enrolment` and whatever string a visitor typed.
`minting_gaps` reads this module's own source to prove there is no generator in it, the way
`brain.firstrun.credential_field_gaps` proves there is nowhere to put one. See
`THE_INSTALLER_MINTS_AND_THIS_MODULE_ONLY_EVER_COMPARES`.

**The code is presented on every request and there is no session.** A wizard that exchanged
the code for a cookie would be a wizard that minted a second credential, which is the one
thing this module may not do, so every entry point below takes the enrolment and the code the
visitor typed, and refuses uniformly. `reopening_gaps` reads the signatures to prove it.
That is what makes the first screen a gate rather than a suggestion:
until 2026-09-09 the draft of this module checked the code in `unlock` and in the final write
and nowhere between, so a stranger who never called `unlock` could walk every screen and read
the review. See `A_CODE_CHECKED_ONLY_AT_THE_ENDS_IS_A_CODE_CHECKED_AT_NEITHER`.

**What a wrong code does.** It refuses in the same words as an expired one and a spent one,
because telling them apart tells somebody whether the value they typed was ever right: that is
`brain.firstrun.A_REFUSAL_THAT_SAYS_WHY_IS_AN_ORACLE`, and this module reuses `claim` rather
than comparing anything itself. There is no attempt limit, and its absence is a decision
rather than an omission. See `AN_ATTEMPT_LIMIT_IS_A_WAY_TO_DESTROY_THE_ONLY_WAY_IN`.

**What a restart does, stated as narrowly as it is true.** Nothing here reprints the code and
nothing here reopens the window: the expiry is `Enrolment.expires_at`, decided once by
`brain.firstrun.open_enrolment` from the instant the installer issued it, and this module
never constructs an enrolment or extends one. What this module cannot promise is what happens
outside it, and two things are worth saying plainly rather than implying otherwise. Re-running
the installer does reprint the code, because the step that presents it changes nothing and so
carries no already-done test; that reaches somebody who already has a shell on the server and
could read the environment file anyway. And nothing in this repository yet turns
`BRAIN_SETUP_SECRET` into an enrolment, so whether a restart re-issues one is a decision that
has not been made anywhere. See `A_WINDOW_THIS_MODULE_CANNOT_REOPEN_IS_NOT_A_WINDOW_IT_OWNS`.

**Nothing is written until the end.** A wizard that commits each screen as it goes cannot be
corrected: the person who mistypes the company name on screen two discovers it on screen
seven, by which time it is in the branding, in the realm and in the first notification. So
every step accumulates into a `Draft` that is validated and not applied, and `apply_install`
is the single act that turns six screens into an installation. `review` is the screen before
it and shows every answer, with a supplied key shown as supplied rather than as itself.

**The draft's home is a file in the install directory, and the one thing it may not hold is a
credential.** A resumable install is a question about where the answers live between visits,
and every candidate is a disclosure of some sort: a cookie puts the company's answers on a
laptop, a log line puts them where operations can read them, a query string puts them in a
proxy's access log. A file beside the environment file the installer already wrote, created
0600, is the one place whose protection is already exactly the protection these answers need.
What makes it safe is not the mode: it is that the provider key is never in it. `snapshot`
drops every secret answer and `draft_from` refuses a document that carries one, so a resumed
install asks for the key again and cannot reach the review screen without it. See
`A_DRAFT_THAT_KEPT_THE_KEY_WOULD_BE_A_KEY_IN_A_FILE_NOBODY_ROTATES`.

**And the wizard becomes unreachable, not hidden.** Every entry point below takes the number
of administrators and refuses when it is not zero, and `reopening_gaps` reads this module's
own signatures to prove there is no parameter anywhere that could say otherwise. Hiding it
would leave an unauthenticated route to the widest role in the system behind a value somebody
printed once and probably still has. See `A_CLOSED_WIZARD_IS_UNREACHABLE_AND_NEVER_HIDDEN`.

**The logo is an address and not an upload, and M42.5.5 says upload.** The setting it feeds is
`INSTALL_LOGO_URL`, whose declared meaning is a URL served from somewhere the client controls,
and an upload would need the object store, an HTTP body and a write this module has no client
for. Collecting an address into a setting that is an address is the version that works; the
substitution is written here rather than left for somebody to discover from the screen.

Rejected: minting the setup code here. A function that produces a secret needs a test, and a
test that exercises it either contains a value or asserts nothing. That is
`brain.firstrun.THE_VALUE_IS_THE_INSTALLERS_AND_THE_RULE_IS_OURS` and this module is on the
same side of it: the installer's shell mints, this compares a digest.

Rejected: a table for the draft. It is the shape a reader reaches for, and on this screen the
database is the one thing that may not be assumed: the wizard is reachable while the first
migration is still running, and a resumable install that needs a schema cannot resume the
install that failed while building one. A file in the directory the installer owns has neither
dependency, and `brain.ops.checkpoints` makes the same split from the other end by deciding
where saved state lives without owning the client that writes it.

Rejected: carrying the draft in the browser and having it handed back each visit. It needs no
server state at all, which is genuinely attractive, and it fails the leaf: an install continued
from a different machine, or from a browser whose storage was cleared, starts again. It also
moves the answers onto a laptop, which is the disclosure the file was chosen to avoid.

Rejected: recording the instant the code was first offered on the draft and reading it back.
The draft this replaced did exactly that, in a field nothing ever read, under a paragraph
saying the window ran from it. Two records of one expiry is one record too many, and the one
that is wrong is the one nobody looked at: the expiry belongs to the enrolment, which is where
`brain.firstrun` put it and where `claim` reads it.

Rejected: error sentences of our own. `brain.locale.FormField` already requires a label key
and an error key per field, and `catalogue_gaps` already proves both exist in every shipped
language. Writing English strings here would have made the first screen of the product the one
screen nobody can read in their own language.

Scope: domain logic and one file. Nothing here opens a socket, reads a clock or renders
anything; the three functions that read or write the draft are handed the path, and the only
other file this touches is its own source, which `minting_gaps` reads to check itself.

Task ids: M42.5.3, M42.5.4, M42.5.5, M42.5.6, M42.5.8
Task ids: M42.5.10, M42.5.11, M42.5.12, M42.5.13
"""

from __future__ import annotations

import ast
import enum
import inspect
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import urlsplit

from brain.firstrun import Enrolment, claim, first_administrator, is_open
from brain.identity.roles import RoleGrant
from brain.identity.staff_source import StaffRecord
from brain.install import BY_NAME
from brain.locale import MESSAGES, FieldError, FormField, form_gaps
from brain.ops.provider_keys import PROVIDER_SLOTS

# ------------------------------------------------------------------ written-down reasons
#: Why the first screen asks for something before it asks for anything else.
A_SERVER_WITH_AN_OPEN_WIZARD_BELONGS_TO_WHOEVER_FINDS_IT: Final = (
    "An install wizard is the one screen in this system with no authenticated reader, and "
    "what it hands out is the widest role there is. Between the installer finishing and the "
    "client reaching their laptop there is a server on a public address whose next visitor "
    "becomes its administrator. The setup code is the whole of what stands in that gap, and "
    "it is required on the first screen rather than at the end, because a wizard that asks "
    "at the end has already let a stranger read the company's name, its staff source and its "
    "model configuration on the way there."
)

#: Why every entry point takes the code rather than only the first and the last.
A_CODE_CHECKED_ONLY_AT_THE_ENDS_IS_A_CODE_CHECKED_AT_NEITHER: Final = (
    "A gate on the first screen is a gate only if nothing behind it can be reached without "
    "passing through it, and in a module with no session there is nothing carrying the fact "
    "that somebody did. So the code travels with every request and is compared on every one. "
    "The alternative is exchanging it for a cookie, which means minting a second credential "
    "in the one module whose whole argument is that it mints nothing, and it would put that "
    "credential on the laptop the answers were deliberately kept off."
)

#: Why there is no generator in this module.
THE_INSTALLER_MINTS_AND_THIS_MODULE_ONLY_EVER_COMPARES: Final = (
    "The owner of this repository does not create a password on a client's behalf and does "
    "not hold one. The setup code is generated by the installer on the client's own machine, "
    "written into that install's environment file and printed to the terminal the installer "
    "was run from, which are the only two copies and both are theirs. What arrives here is a "
    "digest of something already gone. A module that could generate the value would be a "
    "module whose tests contain one, and a value in a test suite is a value in a repository "
    "that ships to every client."
)

#: Why there is no limit on how many times a code may be tried.
AN_ATTEMPT_LIMIT_IS_A_WAY_TO_DESTROY_THE_ONLY_WAY_IN: Final = (
    "A counter that sealed the enrolment after some number of wrong tries would hand anybody "
    "who can reach the page a reliable way to make the install unclaimable, which is a "
    "denial of service with a guaranteed hit rate. The value it protects carries 256 bits "
    "and is not guessed inside its own hour, so the counter would buy nothing against the "
    "attack it is named for. `brain.firstrun.claim` makes the same argument about why a "
    "wrong presentation does not spend the enrolment, and this is that argument one step out."
)

#: What this module can and cannot say about a restart.
A_WINDOW_THIS_MODULE_CANNOT_REOPEN_IS_NOT_A_WINDOW_IT_OWNS: Final = (
    "The expiry is on the enrolment, decided once by `open_enrolment` from the instant the "
    "installer issued it, and nothing here constructs an enrolment or extends one, which "
    "`minting_gaps` reads the source to prove. That is the whole of what this module can "
    "promise, and stating more would be stating somebody else's behaviour: whether a restart "
    "re-issues an enrolment is decided wherever `BRAIN_SETUP_SECRET` is read, and nothing in "
    "this repository reads it yet. A claim about a restart written here would be a claim "
    "about code that does not exist, which is the failure a module docstring makes hardest "
    "to notice."
)

#: Why each screen accumulates rather than commits.
A_WIZARD_THAT_COMMITS_EACH_SCREEN_CANNOT_BE_CORRECTED: Final = (
    "A step that writes as it goes is a step with no way back. The company name mistyped on "
    "screen two is discovered on screen seven, and by then it is in the branding, in the "
    "realm's client configuration and in the first message the system sends. Accumulating "
    "costs one screen, the review, and buys the property that until somebody presses the "
    "last button the install is exactly as it was before the wizard was opened."
)

#: Why the draft may be a file and may not hold a key.
A_DRAFT_THAT_KEPT_THE_KEY_WOULD_BE_A_KEY_IN_A_FILE_NOBODY_ROTATES: Final = (
    "The answers are a company name, a web address and the first administrator's own "
    "address, all of which that company is about to publish to its own staff. The provider "
    "key is not: it is a standing credential no engine reissues, valid until somebody revokes "
    "it in a dashboard, and a copy left in an install directory outlives the install that "
    "made it and appears in no inventory. So it is the one answer that does not survive a "
    "visit, and a resumed install asks for it again rather than remembering it."
)

#: Why the wizard closes rather than hides.
A_CLOSED_WIZARD_IS_UNREACHABLE_AND_NEVER_HIDDEN: Final = (
    "A hidden install path is an unauthenticated route to the widest role in the system, "
    "guarded by a value printed once to a terminal that has since been closed. Whoever finds "
    "the address later finds a working endpoint. So closure is a refusal at every entry "
    "point rather than a missing link, it is keyed on the number of administrators rather "
    "than on a flag somebody could set, and `reopening_gaps` reads the signatures here to "
    "prove nothing takes a parameter that could reopen it."
)

#: Why a step skipped now is not a decision the client is stuck with.
A_CONNECTION_SKIPPED_NOW_IS_NOT_A_CONNECTION_REFUSED: Final = (
    "Connecting a data source needs somebody who can authorise it in that source, and on "
    "install day that person is usually not in the room. A wizard that treated the step as "
    "required would be answered by whoever is, with whatever credentials they can find, "
    "which is the worst version of this decision. Skipping records that it was skipped and "
    "nothing else, and answering it commits nothing either: the connections screen sets no "
    "installation value, so a skipped install and an answered one are the same install."
)


class WizardError(Exception):
    """Raised when the wizard is asked for something it must not do."""


class WizardClosedError(WizardError):
    """Raised when the wizard is reached on an install that already has an administrator.

    Its own type rather than a flag on a message, because this is the refusal a route has to
    turn into "there is nothing here" without reading any text.
    """


class WizardLockedError(WizardError):
    """Raised when a screen behind the first one is reached without an accepted setup code.

    Distinct from `WizardClosedError`, and the difference is what a route does next. A closed
    wizard renders nothing at all. A locked one renders the first screen again, which is the
    only outcome that lets somebody who mistyped the code carry on. The message is the same
    for a wrong code, an expired one and a spent one: see `brain.firstrun`.
    """


# ------------------------------------------------------------------ the screens
class StepId(enum.StrEnum):
    """The screens, in the order they are shown.

    `REVIEW` and `FINISH` carry no questions and are still steps, because they are counted: a
    person told they are on step 3 of 8 has been told how much is left, and leaving the last
    two out would make the total shrink towards the end for no reason they can see.
    """

    SETUP_CODE = "setup_code"
    COMPANY = "company"
    ADMINISTRATOR = "administrator"
    STAFF_SOURCE = "staff_source"
    MODEL_PROVIDER = "model_provider"
    CONNECTIONS = "connections"
    REVIEW = "review"
    FINISH = "finish"


#: How many characters the setup code is, which is `openssl rand -hex 32` in
#: `brain.deployment.installer`'s mint step: 32 bytes rendered as 64 hex characters, so 256
#: bits. Written down here because the first screen has to be able to accept the value the
#: installer printed, and nothing else in this repository compares the two ends. A test reads
#: the byte count out of that step's shell rather than trusting this line.
SETUP_CODE_CHARS: Final = 64

#: The longest an ordinary answer may be. Not a policy about names: it is the length above
#: which an answer is being pasted rather than typed, and every one of these ends up in a page
#: title, an environment file line or a realm's client configuration. It is a ceiling on those
#: rather than a number chosen for its own sake, so what pins it is the chain
#: `MIN_SECRET_CHARS <= SETUP_CODE_CHARS <= MAX_ANSWER_CHARS < MAX_KEY_CHARS`: a cap below the
#: setup code would refuse the one answer the installer guarantees.
MAX_ANSWER_CHARS: Final = 200

#: The longest a pasted credential may be. Larger, and deliberately so: a provider key is
#: issued by somebody else in a format that is not ours to bound, and it goes to the vault
#: rather than onto a line of an environment file, so the reason for the ordinary cap does not
#: apply to it. A ceiling on a paste rather than a statement about any provider's format.
MAX_KEY_CHARS: Final = 1000

#: What a value chosen from a list looks like, in every list here: `google_workspace`,
#: `hosted`, `xero`. Lower case with underscores, so a display label pasted in by mistake is
#: refused at the shape before anything looks it up.
SLUG = re.compile(r"^[a-z][a-z0-9_]{0,38}$")

#: A validator: the value, and the error code it earns, or the empty string when it is fine.
#:
#: A code rather than a sentence, because the sentence lives in `brain.locale.MESSAGES` in
#: every shipped language, and a validator returning text would be a validator that had
#: already decided which language the reader has.
Check = Callable[[str], str]


def _anything(value: str) -> str:
    """No rule beyond the length one every question already carries."""
    return ""


def _absolute_url(value: str) -> str:
    """An address a browser can be sent to, whole, rather than a bare host.

    `https` is not required and `http` is accepted, because an install on a private network
    behind its own terminator is a real deployment and refusing it here would push a client
    to type a scheme they do not serve. What is refused is a value with no scheme or no host,
    which is the mistake people actually make.
    """
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        return "not_absolute"
    if not parts.netloc:
        return "not_absolute"
    return ""


def _work_address(value: str) -> str:
    """The address the first administrator signs in with.

    Delegated to `StaffRecord` rather than tested here, so there is one answer in this
    repository to what a work address is. The display name passed in is the address itself:
    the only rule `StaffRecord` applies to a display name is that it is not blank, and a
    non-blank address is a non-blank display name, so the only thing that can fail is the
    address.
    """
    try:
        StaffRecord(work_address=value, display_name=value)
    except ValueError:
        return "not_an_address"
    return ""


def _one_of(allowed: Sequence[str]) -> Check:
    """A validator refusing anything outside a closed list."""
    known = frozenset(allowed)

    def check(value: str) -> str:
        if value not in known:
            return "unknown_choice"
        return ""

    return check


def _slug_list(value: str) -> str:
    """A comma-separated list of source names, each shaped like a source name.

    Shape only, and there is no closed list to check against: nothing in this repository
    declares which sources are connectable at install time. `brain.connectors.registry` is a
    runtime registry of manifests that have already been installed, and inventing a second
    list here would be a list that disagrees with it the first time somebody adds a connector.
    Its own error code rather than `unknown_choice`, because "choose one of the options shown"
    is the wrong sentence for a screen with no options to show.
    """
    for one in value.split(","):
        name = one.strip()
        if name and not SLUG.match(name):
            return "not_a_source_name"
    return ""


#: The staff sources the wizard offers, and what each means to the identity provider.
#:
#: Four rather than the six `brain.identity.staff_adapters.ADAPTER_SOURCES` can parse. LDAP
#: and a Google Sheet are both real sources and neither is one a person picks on install day
#: without help; the console adds them afterwards. The map is to `INSTALL_BROKERED_DIRECTORY`,
#: whose own meaning names exactly these values, because choosing where the staff list comes
#: from is also choosing what signs people in, and asking those as two questions is how an
#: install ends up brokering to one directory and syncing from another.
STAFF_SOURCE_BROKERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "google_workspace": "google",
        "microsoft_entra": "microsoft",
        "lark": "lark",
        # A spreadsheet cannot be authenticated against, which
        # `staff_source.A_SPREADSHEET_CANNOT_BE_AUTHENTICATED_AGAINST` argues at length, so
        # the realm holds the passwords itself and the sheet is a roster only.
        "spreadsheet": "none",
    }
)

#: The two model profiles, spelled as `INSTALL_MODEL_PROFILE` spells them.
MODEL_PROFILES: Final[tuple[str, ...]] = ("local", "hosted")

#: The profile a client who has not chosen gets, matching that setting's own default: a client
#: who has not chosen to send their text off their own hardware has not chosen it.
LOCAL_ONLY: Final = "local"

#: The path the console receives an authorisation code on, as `ops/keycloak/realm-export.json`
#: already registers it. Derived from the web address rather than asked for, because a client
#: typing a redirect URI is a client typing the one value whose being wrong is an open
#: redirect, and it is the same string on every install.
CALLBACK_PATH: Final = "/auth/callback"


@dataclass(frozen=True)
class Question:
    """One thing a screen asks for, and what it means to the installation.

    `field` is a `brain.locale.FormField` rather than a label of our own, so the label and
    every error message are catalogue keys already proved to exist in every shipped language.

    `setting` names the `brain.install` setting this answer supplies, when it supplies one
    directly. Empty for an answer that is used rather than stored, or that several settings
    are derived from: the administrator's address is not a setting, and the web address
    becomes a redirect URI rather than being one.

    `max_chars` is per question rather than one number for the wizard, because the reason for
    the cap differs by question. An answer that becomes an environment file line is capped
    because of where it is going; a provider key is capped only because a paste has to stop
    somewhere. One number for both would have to be the larger, which would let a company name
    of a thousand characters into a page title.
    """

    field: FormField
    check: Check
    #: True when the screen cannot be finished without it. False for a question whose need
    #: depends on another answer; that rule lives in the step's `also`.
    required: bool = True
    #: True for an answer that must not survive the visit it was given in.
    secret: bool = False
    #: The `INSTALL_` setting this answer sets, or empty.
    setting: str = ""
    #: The longest this answer may be.
    max_chars: int = MAX_ANSWER_CHARS

    def __post_init__(self) -> None:
        if self.secret and self.setting:
            msg = (
                f"{self.field.name} is a secret and also names {self.setting}, which would "
                "put it in the environment file as an ordinary installation value"
            )
            raise WizardError(msg)
        if self.setting and self.setting not in BY_NAME:
            msg = (
                f"{self.field.name} names {self.setting!r}, which is not a declared "
                "installation setting, so nothing would read what this answer set"
            )
            raise WizardError(msg)
        if self.max_chars < 1:
            msg = (
                f"{self.field.name} accepts {self.max_chars} characters, so every answer to "
                "it is too long and the question can never be answered"
            )
            raise WizardError(msg)


#: A cross-field rule: one screen's answers, and every problem they have as a whole.
Rule = Callable[[Mapping[str, str]], tuple[FieldError, ...]]


def _no_rule(values: Mapping[str, str]) -> tuple[FieldError, ...]:
    """A screen whose questions answer for themselves."""
    return ()


def _provider_rule(values: Mapping[str, str]) -> tuple[FieldError, ...]:
    """What the model screen needs beyond each answer being well formed.

    Both directions, and the second is the one that would otherwise be silent. A hosted
    profile with no key is an install that cannot answer a question and says so on the first
    afternoon. A local profile carrying a key is an install where somebody supplied a
    credential the routing will never reach and believes their questions are going to that
    provider: nothing fails, and the belief is wrong for as long as it lasts.

    A profile that is not one of the two produces nothing at all. Its own question already
    refuses it, and adding two more messages to a screen whose first field is wrong buries
    the one the person can act on.
    """
    profile = values.get("model_profile", "").strip()
    supplied = values.get("provider_key", "").strip()
    if profile not in MODEL_PROFILES:
        return ()
    if profile == LOCAL_ONLY:
        if supplied:
            return (FieldError(field="provider_key", key="setup.error.key_not_wanted"),)
        return ()
    found: list[FieldError] = []
    if not values.get("model_provider", "").strip():
        found.append(FieldError(field="model_provider", key="setup.error.provider_needed"))
    if not supplied:
        found.append(FieldError(field="provider_key", key="setup.error.key_needed"))
    return tuple(found)


@dataclass(frozen=True)
class Step:
    """One screen: what it asks, whether it may be skipped, and its cross-field rule.

    `skippable` is declared rather than derived from every question being optional, and the
    difference is what `A_CONNECTION_SKIPPED_NOW_IS_NOT_A_CONNECTION_REFUSED` is about: a
    screen where every question happens to be optional is a screen somebody left blank, and a
    skipped screen is one they decided about. Only the second is a record.
    """

    key: StepId
    title_key: str
    questions: tuple[Question, ...] = ()
    also: Rule = _no_rule
    skippable: bool = False

    def __post_init__(self) -> None:
        if not self.title_key.strip():
            msg = f"{self.key} has no title key, so the screen cannot be headed or counted"
            raise WizardError(msg)
        names = [one.field.name for one in self.questions]
        if len(names) != len(set(names)):
            msg = f"{self.key} asks for {sorted(names)} with a repeat, so one answer wins"
            raise WizardError(msg)
        if self.skippable and any(one.required for one in self.questions):
            msg = (
                f"{self.key} is skippable and has a required question, so skipping it and "
                "answering it are two rules and the screen obeys whichever it is asked"
            )
            raise WizardError(msg)

    @property
    def stores(self) -> bool:
        """Whether anything this screen collects survives the visit.

        False for the setup code, whose one question is secret, which is what keeps the code
        out of the draft with no special case anywhere: a screen that stores nothing is not
        somewhere a resume can land.
        """
        return any(not one.secret for one in self.questions)

    def asks(self, name: str) -> bool:
        """Whether this screen has a question by that name.

        The gate on what `answer` keeps. A screen records what it asked for and nothing else,
        so a field a browser invented is dropped rather than written into a file the review
        screen does not show and nothing validates.
        """
        return any(one.field.name == name for one in self.questions)


#: Shared error keys. One sentence per kind of mistake rather than per field, and that is not
#: a shortcut: `brain.locale.FieldError` exists so a message is associated with its own input
#: rather than read out at the top of the page, which is what makes "this is needed before the
#: wizard can continue" actionable beside the box it belongs to.
BLANK: Final[Mapping[str, str]] = MappingProxyType({"blank": "setup.error.blank"})
TOO_LONG: Final[Mapping[str, str]] = MappingProxyType({"too_long": "setup.error.too_long"})
UNKNOWN: Final[Mapping[str, str]] = MappingProxyType(
    {"unknown_choice": "setup.error.unknown_choice"}
)


def _errors(*parts: Mapping[str, str]) -> Mapping[str, str]:
    """The error codes one question can produce, merged and frozen."""
    merged: dict[str, str] = {}
    for part in parts:
        merged.update(part)
    return MappingProxyType(merged)


def _q(
    name: str,
    *,
    errors: Mapping[str, str],
    check: Check = _anything,
    required: bool = True,
    secret: bool = False,
    setting: str = "",
    max_chars: int = MAX_ANSWER_CHARS,
) -> Question:
    """One question, with its label key derived from its name.

    Derived rather than passed, because a label key that can differ from the field name is a
    label key that will, and the failure is a screen showing one field's label above another
    field's input. `wizard_gaps` checks the derived key is in the catalogue.
    """
    return Question(
        field=FormField(name=name, label_key=f"field.{name}.label", errors=errors),
        check=check,
        required=required,
        secret=secret,
        setting=setting,
        max_chars=max_chars,
    )


#: The wizard. Eight screens, and the count is arithmetic rather than a number somebody typed:
#: `brain.deployment.installer.PLAN` carries a comment saying it has ten steps and has had
#: twelve since somebody appended two, which is the failure `progress_for` avoids by reading
#: `len` and never a constant.
WIZARD: Final[tuple[Step, ...]] = (
    Step(
        key=StepId.SETUP_CODE,
        title_key="setup.step.setup_code.title",
        questions=(
            _q(
                "setup_code",
                errors=_errors(BLANK, TOO_LONG, {"refused": "setup.error.refused"}),
                secret=True,
            ),
        ),
    ),
    Step(
        key=StepId.COMPANY,
        title_key="setup.step.company.title",
        questions=(
            _q("company_name", errors=_errors(BLANK, TOO_LONG), setting="INSTALL_COMPANY_NAME"),
            _q(
                "product_name",
                errors=_errors(TOO_LONG),
                required=False,
                setting="INSTALL_PRODUCT_NAME",
            ),
            _q(
                "web_address",
                errors=_errors(BLANK, TOO_LONG, {"not_absolute": "setup.error.not_absolute"}),
                check=_absolute_url,
            ),
            _q(
                "logo_url",
                errors=_errors(TOO_LONG, {"not_absolute": "setup.error.not_absolute"}),
                check=_absolute_url,
                required=False,
                setting="INSTALL_LOGO_URL",
            ),
        ),
    ),
    Step(
        key=StepId.ADMINISTRATOR,
        title_key="setup.step.administrator.title",
        questions=(
            _q("full_name", errors=_errors(BLANK, TOO_LONG)),
            _q(
                "work_address",
                errors=_errors(BLANK, TOO_LONG, {"not_an_address": "setup.error.not_an_address"}),
                check=_work_address,
            ),
        ),
    ),
    Step(
        key=StepId.STAFF_SOURCE,
        title_key="setup.step.staff_source.title",
        questions=(
            _q(
                "staff_source",
                errors=_errors(BLANK, TOO_LONG, UNKNOWN),
                check=_one_of(tuple(STAFF_SOURCE_BROKERS)),
            ),
        ),
    ),
    Step(
        key=StepId.MODEL_PROVIDER,
        title_key="setup.step.model_provider.title",
        questions=(
            _q(
                "model_profile",
                errors=_errors(BLANK, TOO_LONG, UNKNOWN),
                check=_one_of(MODEL_PROFILES),
                setting="INSTALL_MODEL_PROFILE",
            ),
            _q(
                "model_provider",
                errors=_errors(
                    TOO_LONG, UNKNOWN, {"provider_needed": "setup.error.provider_needed"}
                ),
                check=_one_of(tuple(one.slug for one in PROVIDER_SLOTS)),
                required=False,
            ),
            _q(
                "provider_key",
                errors=_errors(
                    TOO_LONG,
                    {
                        "key_needed": "setup.error.key_needed",
                        "key_not_wanted": "setup.error.key_not_wanted",
                    },
                ),
                required=False,
                secret=True,
                max_chars=MAX_KEY_CHARS,
            ),
        ),
        also=_provider_rule,
    ),
    Step(
        key=StepId.CONNECTIONS,
        title_key="setup.step.connections.title",
        questions=(
            _q(
                "connections",
                errors=_errors(TOO_LONG, {"not_a_source_name": "setup.error.not_a_source_name"}),
                check=_slug_list,
                required=False,
            ),
        ),
        skippable=True,
    ),
    Step(key=StepId.REVIEW, title_key="setup.step.review.title"),
    Step(key=StepId.FINISH, title_key="setup.step.finish.title"),
)

#: The wizard, indexed. Built once because every entry point resolves a step.
STEPS: Final[Mapping[StepId, Step]] = MappingProxyType({one.key: one for one in WIZARD})

#: Every answer that must not survive a visit, as `step.field`. Derived from the wizard rather
#: than listed, so a secret question added later is covered by `draft_from` without anybody
#: remembering to add it here.
SECRET_ANSWERS: Final[frozenset[str]] = frozenset(
    f"{step.key.value}.{one.field.name}" for step in WIZARD for one in step.questions if one.secret
)


def step_for(key: StepId) -> Step:
    """One screen, refusing an unknown one rather than answering None.

    Refuses for the reason `brain.deployment.installer.step_named` refuses: a caller handed
    None writes `if step is None: return` and the screen silently stops being part of the
    wizard.
    """
    found = STEPS.get(key)
    if found is None:
        msg = f"{key!r} is not a step in this wizard; it has {[one.key for one in WIZARD]}"
        raise WizardError(msg)
    return found


#: Every state a review row can be in that is not the person's own words. Keys rather than
#: sentences, for the same reason every label here is one: the review screen is the last thing
#: read before an install is written, and it is read in whichever language the install offers.
REVIEW_STATES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "supplied": "setup.review.supplied",
        "not_given": "setup.review.not_given",
        "skipped": "setup.review.skipped",
    }
)


def wizard_gaps(
    steps: Sequence[Step] = WIZARD, states: Mapping[str, str] = REVIEW_STATES
) -> tuple[str, ...]:
    """Every way this wizard would fail somebody reading it or somebody navigating it.

    Five findings. A title key the catalogue does not hold is a screen with no heading. Three
    are `brain.locale.form_gaps`' own, which is why they are delegated rather than
    reimplemented: an unlabelled input, a message key that is not in the catalogue, and a
    field that can fail with nothing to say. On top of those, a required question with no
    `blank` message and any question with no `too_long` message are the two codes
    `problems_with` can produce for every field, so a question missing either can refuse with
    a `WizardError` rather than a sentence. The review screen's own three states are checked
    here as well, because they are the only strings on that screen that are not somebody's
    own words and an absent one renders as a blank cell beside a real answer.

    Takes both the steps and the states so every refusal can be exercised against something
    built to fail, which is `brain.locale.catalogue_gaps`' argument: a check that can only run
    against the real thing has no test for the case it exists to find. The states were a
    module constant read directly here until a mutation run showed why that is not the same
    thing: the branch had no reachable failing case, so it could be deleted with the suite
    green.
    """
    findings: list[str] = []
    for state, key in sorted(states.items()):
        if key not in MESSAGES:
            findings.append(f"review: {state} reads {key!r}, which is not in the catalogue")
    for step in steps:
        if step.title_key not in MESSAGES:
            findings.append(f"{step.key}: title {step.title_key!r} is not in the catalogue")
        findings.extend(
            f"{step.key}: {one}" for one in form_gaps([one.field for one in step.questions])
        )
        for question in step.questions:
            name = question.field.name
            if question.required and "blank" not in question.field.errors:
                findings.append(
                    f"{step.key}.{name}: required with no blank message, so leaving it empty "
                    "refuses with an exception rather than a sentence"
                )
            if "too_long" not in question.field.errors:
                findings.append(
                    f"{step.key}.{name}: no too_long message, so a pasted document refuses "
                    "with an exception rather than a sentence"
                )
    return tuple(findings)


# ------------------------------------------------------------------ where a person is
@dataclass(frozen=True)
class Progress:
    """Where this screen sits, for the line that reads "step 3 of 8" (M42.5.4).

    `back` is the screen a back button goes to, and it is `None` in exactly two places. The
    first screen has nothing behind it. The last screen has the install behind it, and a back
    button there would offer to unwrite what has been written, which is either a lie or a
    second write path into an install that already has an administrator.
    """

    number: int
    of: int
    back: StepId | None

    def __post_init__(self) -> None:
        if self.number < 1:
            msg = "a step is counted from one, because that is how it is read aloud"
            raise WizardError(msg)
        if self.number > self.of:
            msg = f"step {self.number} of {self.of} is past the end of the wizard"
            raise WizardError(msg)


def progress_for(key: StepId, steps: Sequence[Step] = WIZARD) -> Progress:
    """The counted position of one screen (M42.5.4).

    `of` is `len(steps)` rather than a constant, so adding a screen renumbers every line that
    mentions the total. The screen with no back is found by position rather than by name, so a
    wizard built for a test behaves the way the real one does; naming `FINISH` here would make
    the rule true of one wizard and untested in every other.
    """
    order = [one.key for one in steps]
    if key not in order:
        msg = f"{key!r} is not in this wizard, so it has no position in it"
        raise WizardError(msg)
    at = order.index(key)
    back = None if at == 0 or at == len(order) - 1 else order[at - 1]
    return Progress(number=at + 1, of=len(order), back=back)


# ------------------------------------------------------------------ the accumulated answers
@dataclass(frozen=True)
class Draft:
    """Every answer given so far, and nothing that has been written.

    Frozen, and every change returns a new one. A mutable draft would make "what was
    answered" a question about an object's history, which is unanswerable after the browser
    was closed, and that is the whole subject of M42.5.12.

    **There is no time on this**, and the field that used to be here is the reason it is worth
    saying so. A draft carrying the instant the code was first offered is a second record of
    an expiry that already lives on the enrolment, and two records of one fact is one too many.
    See `A_WINDOW_THIS_MODULE_CANNOT_REOPEN_IS_NOT_A_WINDOW_IT_OWNS`.
    """

    answers: Mapping[str, Mapping[str, str]] = MappingProxyType({})
    #: Screens the person decided against. Distinct from a screen left blank.
    skipped: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for key in (*self.answers, *self.skipped):
            if key not in STEPS:
                msg = f"the draft carries {key!r}, which is not a screen in this wizard"
                raise WizardError(msg)
        both = sorted(set(self.answers) & set(self.skipped))
        if both:
            msg = f"{both} are answered and skipped, and a screen cannot be in two states"
            raise WizardError(msg)

    def values_for(self, key: StepId) -> Mapping[str, str]:
        """What was answered on one screen, or nothing."""
        return self.answers.get(key.value, MappingProxyType({}))


def new_draft() -> Draft:
    """The empty draft an install starts from."""
    return Draft()


def _message(question: Question, code: str) -> str:
    """The catalogue key one refusal is written under, refusing a code with no message.

    Raises rather than falling back, for `brain.locale.text`'s reason: a fallback means the
    catalogue is never finished, and the person who cannot read the fallback is the only one
    who could notice. `wizard_gaps` runs in the suite, so this is unreachable in the shipped
    wizard and reachable in a wizard somebody is building.
    """
    key = question.field.errors.get(code)
    if key is None:
        msg = (
            f"{question.field.name} produced {code!r} and has no message for it, so the "
            "screen would refuse with nothing a person could act on"
        )
        raise WizardError(msg)
    return key


def problems_with(step: Step, values: Mapping[str, str]) -> tuple[FieldError, ...]:
    """Everything wrong with one screen's answers, said against the field it belongs to.

    Each answer is stripped before it is judged, which is what makes `" "` a blank rather than
    a value: a company name of one space passes every non-empty test and renders as an unnamed
    install. Length is checked before the field's own rule, so a pasted document earns one
    message about its length rather than a message about its shape.

    The step's `also` runs after the per-field rules and its findings are appended rather than
    replacing them, because a hosted profile with an unknown provider and no key has two
    problems and fixing one leaves a screen that still refuses.
    """
    found: list[FieldError] = []
    for question in step.questions:
        name = question.field.name
        value = values.get(name, "").strip()
        if not value:
            if question.required:
                found.append(FieldError(field=name, key=_message(question, "blank")))
            continue
        if len(value) > question.max_chars:
            found.append(FieldError(field=name, key=_message(question, "too_long")))
            continue
        code = question.check(value)
        if code:
            found.append(FieldError(field=name, key=_message(question, code)))
    found.extend(step.also(values))
    return tuple(found)


def is_answered(step: Step, draft: Draft) -> bool:
    """Whether one screen is finished, which is not the same as its having been visited.

    A skipped screen counts as finished and an unvisited one does not, which is why the
    membership test comes first: a screen whose questions are all optional has no problems
    with no answers at all, so asking `problems_with` alone would report every optional screen
    as done before anybody had seen it.
    """
    if step.key.value in draft.skipped:
        return True
    if step.key.value not in draft.answers:
        return False
    return not problems_with(step, draft.values_for(step.key))


def next_step(draft: Draft) -> StepId:
    """The screen to show, which on a resume is where the person stopped (M42.5.12).

    Only screens that store anything are walked. The setup code is asked on every visit and
    never recorded, so it is not somewhere a resume can land, and the review screen is where a
    draft with every answer arrives.
    """
    for step in WIZARD:
        if not step.stores:
            continue
        if not is_answered(step, draft):
            return step.key
    return StepId.REVIEW


# ------------------------------------------------------------------ the closed door
#: A parameter name that would mean "do it anyway". Scanned for rather than trusted, because
#: the way this rule dies is one keyword added during an install that would not proceed.
REOPENING_NAMES: Final[frozenset[str]] = frozenset(
    {
        "force",
        "anyway",
        "override",
        "reopen",
        "allow_closed",
        "even_if_closed",
        "ignore_administrators",
        "skip_checks",
        "unsafe",
    }
)

#: A call that would make this module a place a credential is generated. Names rather than a
#: pattern over the text, so a mention in a docstring is not a finding and a call is.
MINTING_NAMES: Final[frozenset[str]] = frozenset(
    {
        "open_enrolment",
        "Enrolment",
        "digest_of",
        "token_hex",
        "token_bytes",
        "token_urlsafe",
        "urandom",
        "randbytes",
        "getrandbits",
        "uuid1",
        "uuid4",
    }
)

#: Every function a browser can reach. Named rather than derived from what happens to be
#: public, so a function added without being listed is one the closure check never runs
#: against, and `reopening_gaps` says so rather than silently covering less.
ENTRY_POINTS: Final[tuple[str, ...]] = ("unlock", "answer", "skip", "review", "apply_install")


def assert_open(administrators: int) -> None:
    """Refuse unless this install has no administrator (M42.5.11).

    One function every entry point calls, rather than the same condition written five times.
    The arithmetic is `brain.firstrun.is_open`'s, so there is one answer in this repository to
    whether first run is over and it is the one that takes a count rather than a flag. See
    `A_CLOSED_WIZARD_IS_UNREACHABLE_AND_NEVER_HIDDEN`.
    """
    if not is_open(administrators=administrators):
        msg = (
            "this install already has an administrator, so there is no setup wizard here. "
            f"{A_CLOSED_WIZARD_IS_UNREACHABLE_AND_NEVER_HIDDEN}"
        )
        raise WizardClosedError(msg)


def assert_unlocked(enrolment: Enrolment, presented: str, *, now: datetime) -> None:
    """Refuse a screen behind the first one without an accepted setup code (M42.5.3).

    Called by every entry point except the first screen, which reports the same refusal as a
    field error instead because on that screen it is one. **The enrolment `claim` returns is
    dropped**, so verifying costs nothing: it is spent once, in `apply_install`. See
    `A_CODE_CHECKED_ONLY_AT_THE_ENDS_IS_A_CODE_CHECKED_AT_NEITHER`.
    """
    if not claim(enrolment, presented=presented, now=now).accepted:
        msg = (
            "that setup code was not accepted, and which of the three reasons it was is not "
            f"said here. {A_SERVER_WITH_AN_OPEN_WIZARD_BELONGS_TO_WHOEVER_FINDS_IT}"
        )
        raise WizardLockedError(msg)


def module_functions() -> Mapping[str, Callable[..., Any]]:
    """Every function this module defines, by name, and none that it imported.

    Filtered on `__module__` rather than on the name, because an imported helper's signature
    is not this module's promise and reporting one would be a finding nobody here can fix.
    """
    here = sys.modules[__name__]
    return MappingProxyType(
        {
            name: value
            for name, value in vars(here).items()
            if inspect.isfunction(value) and value.__module__ == __name__
        }
    )


def module_source() -> str:
    """This module's own source, for the checks that read it rather than trusting it."""
    return Path(__file__).read_text(encoding="utf-8")


def reopening_gaps(
    functions: Mapping[str, Callable[..., Any]] | None = None,
    entry_points: Sequence[str] = ENTRY_POINTS,
) -> tuple[str, ...]:
    """Every way the closed door could be got round, read off the signatures (M42.5.11).

    Three findings. A parameter anywhere in this module whose name means "do it anyway" is a
    way to reach the install path on a server that already has an administrator. An entry
    point that does not take the number of administrators cannot tell whether this install is
    still open. An entry point that does not take the enrolment cannot ask for the setup code,
    which is the check the draft of this module had on the first screen and the last one and
    nowhere between.

    Read rather than asserted, for the reason `brain.firstrun.credential_field_gaps` scans its
    own models: the way this dies is one keyword added at three in the morning to get an
    install past a check, and never taken out. Takes the functions so all three findings can
    be tested against a module built to fail.
    """
    subject = module_functions() if functions is None else functions
    found: list[str] = []
    for name in sorted(subject):
        for parameter in sorted(inspect.signature(subject[name]).parameters):
            if parameter in REOPENING_NAMES:
                found.append(
                    f"{name} takes {parameter!r}, which is a way to reach the install path on "
                    f"a server that already has an administrator. "
                    f"{A_CLOSED_WIZARD_IS_UNREACHABLE_AND_NEVER_HIDDEN}"
                )
    for name in entry_points:
        entry = subject.get(name)
        if entry is None:
            found.append(f"{name} is listed as an entry point and this module has no such name")
            continue
        taken = inspect.signature(entry).parameters
        if "administrators" not in taken:
            found.append(
                f"{name} is reachable from a browser and does not take the number of "
                "administrators, so it cannot tell whether this install is still open"
            )
        if "enrolment" not in taken:
            found.append(
                f"{name} is reachable from a browser and does not take the enrolment, so it "
                f"cannot ask for the setup code. "
                f"{A_CODE_CHECKED_ONLY_AT_THE_ENDS_IS_A_CODE_CHECKED_AT_NEITHER}"
            )
    return tuple(found)


def minting_gaps(source: str | None = None) -> tuple[str, ...]:
    """Every call in this module that would generate or re-issue a credential (M42.5.3).

    One finding, read off the syntax tree rather than off the text, so a name in a docstring
    is prose and a name in a call position is a finding. What it refuses is both halves of the
    same claim: a generator here would make this the module that creates a client's password,
    and a call to `open_enrolment` here would make it the module that decides when their
    window closes. Both are somebody else's, and the first is nobody's in this repository.

    Takes the source so it can be tested against a module built to fail, which is the only way
    to know the check finds anything at all. See
    `THE_INSTALLER_MINTS_AND_THIS_MODULE_ONLY_EVER_COMPARES`.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(module_source() if source is None else source)):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = ""
        if isinstance(called, ast.Name):
            name = called.id
        elif isinstance(called, ast.Attribute):
            name = called.attr
        if name in MINTING_NAMES:
            found.append(
                f"line {node.lineno} calls {name!r}, so this module would mint or re-issue "
                f"the value it is meant only to compare. "
                f"{THE_INSTALLER_MINTS_AND_THIS_MODULE_ONLY_EVER_COMPARES}"
            )
    return tuple(found)


# ------------------------------------------------------------------ the first screen
def unlock(
    enrolment: Enrolment, values: Mapping[str, str], *, administrators: int, now: datetime
) -> tuple[FieldError, ...]:
    """Whether this visit may see the wizard at all, as the first screen's own form (M42.5.3).

    Returns field errors rather than a boolean, and rather than raising, because this is the
    one screen on which a wrong code is an answer to a question: the person is looking at the
    box they typed it into, and M42.5.13 wants the sentence beside that box. Every other entry
    point raises instead, because on those screens a refused code means the visit is not
    authorised at all rather than that one field is wrong.

    Shape first and value second. A blank or a pasted document earns the same message it would
    on any other screen and is never hashed; only a plausible value reaches `claim`. That is
    not an oracle worth having: it says the code is at most `MAX_ANSWER_CHARS` long, which
    anybody can read off this file.

    **Verifies without spending.** `brain.firstrun.claim` marks the enrolment spent on a
    correct presentation, which is right for the appointment it was written for and wrong
    here: an install whose browser was closed after the first screen would have spent its one
    enrolment on a wizard nobody finished, and the client would have no way back in. So the
    spent enrolment `claim` returns is deliberately dropped here and kept once, in
    `apply_install`, where it buys the administrator.
    """
    assert_open(administrators)
    step = step_for(StepId.SETUP_CODE)
    problems = problems_with(step, values)
    if problems:
        return problems
    presented = values.get("setup_code", "").strip()
    if not claim(enrolment, presented=presented, now=now).accepted:
        return (FieldError(field="setup_code", key="setup.error.refused"),)
    return ()


# ------------------------------------------------------------------ the middle screens
def answer(
    draft: Draft,
    key: StepId,
    values: Mapping[str, str],
    enrolment: Enrolment,
    presented: str,
    *,
    administrators: int,
    now: datetime,
) -> tuple[Draft, tuple[FieldError, ...]]:
    """Record one screen's answers, or say what is wrong with them (M42.5.13).

    Returns the draft unchanged beside the problems rather than raising, because a rejected
    screen is an ordinary event the same screen has to render: raising would make the caller
    catch an exception on the path a person takes several times while typing.

    **Only what the screen asked for is kept.** The draft that comes back carries the step's
    own question names and nothing else, so a field a browser added is dropped rather than
    written into a file that nothing validates and the review screen does not show. That is
    M42.5.10 read strictly: everything written is reviewed, so nothing unreviewed is written.

    **Nothing is written here either.** The draft that comes back is in memory; persisting it
    is `write_draft`, and the install is unchanged until `apply_install`. See
    `A_WIZARD_THAT_COMMITS_EACH_SCREEN_CANNOT_BE_CORRECTED`.
    """
    assert_open(administrators)
    assert_unlocked(enrolment, presented, now=now)
    step = step_for(key)
    if not step.stores:
        msg = (
            f"{key} stores nothing, so there is no answer to record: the setup code is "
            "presented to `unlock` on every visit and never kept"
        )
        raise WizardError(msg)
    problems = problems_with(step, values)
    if problems:
        return draft, problems
    kept = {name: text.strip() for name, text in values.items() if text.strip() and step.asks(name)}
    answers = {**draft.answers, key.value: MappingProxyType(kept)}
    return (
        replace(draft, answers=MappingProxyType(answers), skipped=draft.skipped - {key.value}),
        (),
    )


def skip(
    draft: Draft,
    key: StepId,
    enrolment: Enrolment,
    presented: str,
    *,
    administrators: int,
    now: datetime,
) -> Draft:
    """Record that a screen was decided against rather than left blank (M42.5.10).

    Refuses a screen that is not skippable rather than treating a skip as an empty answer. An
    empty answer to a required screen is one that will refuse at the review, and a skip that
    silently became one would move the refusal to the last screen, where the person can no
    longer see which screen it was about. See
    `A_CONNECTION_SKIPPED_NOW_IS_NOT_A_CONNECTION_REFUSED`.
    """
    assert_open(administrators)
    assert_unlocked(enrolment, presented, now=now)
    step = step_for(key)
    if not step.skippable:
        msg = (
            f"{key} cannot be skipped: it asks for something the install cannot be completed "
            "without, and skipping it would move the refusal to the review screen"
        )
        raise WizardError(msg)
    answers = {name: values for name, values in draft.answers.items() if name != key.value}
    return replace(draft, answers=MappingProxyType(answers), skipped=draft.skipped | {key.value})


# ------------------------------------------------------------------ the review screen
@dataclass(frozen=True)
class ReviewLine:
    """One row of the last screen before anything is written (M42.5.10).

    Exactly one of `shown` and `state_key` carries the row. `shown` is the person's own words
    and is never translated and never the value of a secret; `state_key` is a catalogue key
    for the three things a row can say that are not somebody's own words. Keeping them apart
    is what stops "skipped" appearing in English on an install running in another language,
    and stops a company literally called Skipped reading as a screen nobody filled in.
    """

    step: StepId
    field: str
    label_key: str
    shown: str = ""
    state_key: str = ""

    def __post_init__(self) -> None:
        if self.shown and self.state_key:
            msg = (
                f"{self.step}.{self.field} carries both an answer and a state, and a row that "
                "is both is one a screen renders twice or picks between"
            )
            raise WizardError(msg)
        if not self.shown and not self.state_key:
            msg = (
                f"{self.step}.{self.field} carries neither an answer nor a state, so the row "
                "renders as an empty cell beside a real one and reads as an answered blank"
            )
            raise WizardError(msg)


def review(
    draft: Draft, enrolment: Enrolment, presented: str, *, administrators: int, now: datetime
) -> tuple[ReviewLine, ...]:
    """Everything this install is about to become, before any of it is written (M42.5.10).

    Every question on every storing screen appears, including the ones nobody answered.
    Listing only what was answered would make an omission invisible on the one screen whose
    whole job is to show what is about to happen, and an unset logo and a logo nobody was
    asked about read identically once the install is finished.
    """
    assert_open(administrators)
    assert_unlocked(enrolment, presented, now=now)
    lines: list[ReviewLine] = []
    for step in WIZARD:
        if not step.stores:
            continue
        values = draft.values_for(step.key)
        for question in step.questions:
            name = question.field.name
            given = values.get(name, "").strip()
            state = ""
            shown = ""
            if step.key.value in draft.skipped:
                state = REVIEW_STATES["skipped"]
            elif not given:
                state = REVIEW_STATES["not_given"]
            elif question.secret:
                state = REVIEW_STATES["supplied"]
            else:
                shown = given
            lines.append(
                ReviewLine(
                    step=step.key,
                    field=name,
                    label_key=question.field.label_key,
                    shown=shown,
                    state_key=state,
                )
            )
    return tuple(lines)


# ------------------------------------------------------------------ resuming
#: The shape `snapshot` writes and `draft_from` reads. A number rather than a date, so a
#: document written by an older release refuses with a sentence about the version rather than
#: being read as though its fields meant what they mean today.
SNAPSHOT_VERSION: Final = 1


def snapshot(draft: Draft) -> dict[str, Any]:
    """The draft as a document, with every secret answer dropped (M42.5.12).

    Dropped rather than masked. A masked value is still a value in the file, one substitution
    away from being the real one, and a reader cannot tell a mask from a key that happens to
    look like one. See `A_DRAFT_THAT_KEPT_THE_KEY_WOULD_BE_A_KEY_IN_A_FILE_NOBODY_ROTATES`.

    A screen whose answers were entirely secret comes back as an empty mapping rather than
    disappearing, so the resume knows it was visited and `problems_with` reopens it.
    """
    answers: dict[str, dict[str, str]] = {}
    for step in WIZARD:
        if step.key.value not in draft.answers:
            continue
        secrets = {one.field.name for one in step.questions if one.secret}
        given = draft.values_for(step.key)
        answers[step.key.value] = {
            name: value for name, value in sorted(given.items()) if name not in secrets
        }
    return {
        "version": SNAPSHOT_VERSION,
        "answers": answers,
        "skipped": sorted(draft.skipped),
    }


def draft_from(document: Mapping[str, Any]) -> Draft:
    """A draft read back from a document, refusing one that carries a credential (M42.5.12).

    **The refusal is the point.** `snapshot` drops the secrets, so a document holding one was
    written by something else: an older release, a hand-edited file, or a well-meant change
    that made the resume smoother by keeping the key. Reading it would put that credential
    back into memory and, on the next write, back into the file. Refusing means the wizard
    stops rather than silently accepting a store that has started keeping keys.

    Named for what it produces rather than for what it undoes. `restore` is the obvious name
    and is taken: `tests/unit/test_installation.py` asserts that the only restore-shaped name
    under `src/brain` belongs to the recovery shelf, so that a backup screen cannot quietly
    acquire a second meaning of the word.
    """
    version = document.get("version")
    if version != SNAPSHOT_VERSION:
        msg = (
            f"this draft says it is version {version!r} and this release reads "
            f"{SNAPSHOT_VERSION}, so its fields cannot be assumed to mean what they mean here"
        )
        raise WizardError(msg)
    raw = document.get("answers", {})
    if not isinstance(raw, Mapping):
        msg = "the answers in this draft are not a mapping, so it was not written by `snapshot`"
        raise WizardError(msg)
    answers: dict[str, Mapping[str, str]] = {}
    for step_name, values in raw.items():
        if not isinstance(values, Mapping):
            msg = f"the answers for {step_name!r} are not a mapping of field to value"
            raise WizardError(msg)
        for field_name in values:
            if f"{step_name}.{field_name}" in SECRET_ANSWERS:
                msg = (
                    f"this draft carries {step_name}.{field_name}, which is a credential. "
                    f"{A_DRAFT_THAT_KEPT_THE_KEY_WOULD_BE_A_KEY_IN_A_FILE_NOBODY_ROTATES}"
                )
                raise WizardError(msg)
        answers[str(step_name)] = MappingProxyType(
            {str(name): str(value) for name, value in values.items()}
        )
    return Draft(
        answers=MappingProxyType(answers),
        skipped=frozenset(str(one) for one in document.get("skipped", ())),
    )


#: What the draft is called inside the install directory. Beside the environment file, in the
#: directory the installer created, so an uninstall is still one removal.
DRAFT_FILE_NAME: Final = "setup-draft.json"

#: The mode the draft is created with. Owner only, matching the `umask 077` the installer sets
#: before it mints anything. Asserted against the property rather than against itself:
#: `DRAFT_MODE & 0o077 == 0` is what "nobody else may read it" means.
DRAFT_MODE: Final = 0o600


def write_draft(path: Path, draft: Draft) -> None:
    """Persist the draft, replacing any earlier one (M42.5.12).

    Removed and recreated rather than truncated, because a mode is applied when a file is
    created and not when it is opened: writing into a file somebody had already made
    world-readable would leave it world-readable. A umask can only take bits away from
    `DRAFT_MODE`, never add them, so this is a ceiling.

    `newline` is stated because Python inserts CRLF without it on Windows, and a document
    written on a developer's machine and read on the server is a document whose bytes differ
    from the ones anything compared against.
    """
    path.unlink(missing_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, DRAFT_MODE)
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(snapshot(draft), indent=2, sort_keys=True) + "\n")


def read_draft(path: Path) -> Draft | None:
    """The draft this install stopped at, or None when there has never been one.

    None rather than an empty draft, so a caller can tell a resumed visit from a first one
    without inspecting the answers: those two are the same object and only one of them means
    somebody has been here. Not an entry point, and it takes neither the enrolment nor the
    administrator count on purpose: it reads a file that is 0600 in the install directory, so
    reaching it already means reaching the server, and every function that shows an answer to
    a browser is gated.
    """
    if not path.is_file():
        return None
    return draft_from(json.loads(path.read_text(encoding="utf-8")))


def discard_draft(path: Path) -> None:
    """Remove the draft, which is what finishing an install does to it.

    Called after `apply_install` rather than before, so a failure between the two leaves a
    draft that can be resumed rather than an install with nothing to resume from.
    """
    path.unlink(missing_ok=True)


# ------------------------------------------------------------------ the one write
def settings_from(draft: Draft) -> Mapping[str, str]:
    """The installation values these answers set, as `brain.install` names them.

    Two kinds, and the second is why this is a function rather than a comprehension. Most
    answers name their setting on the question. The redirect URI and the brokered directory
    are derived: a client typing a redirect URI is a client typing the one value whose being
    wrong is an open redirect, and choosing where the staff list comes from is choosing what
    signs people in.

    **This does not finish the install and is not meant to look as though it does.**
    `brain.install.INSTALL_OIDC_ISSUER` is required, has no safe default and is not asked for
    on any screen, because an issuer guessed from the web address is a sign-in page pointing
    at somebody else's identity provider: that is
    `brain.install.A_GUESSED_IDENTITY_PROVIDER_IS_WORSE_THAN_A_STOPPED_ONE`, and the installer
    sets it where the realm is created. A test pins `brain.install.missing` over this result to
    exactly that one name, so a required setting added later fails here rather than on a
    client's server.

    Every name produced here is a declared setting, checked when `Question` is constructed, so
    a wizard that set something nothing reads is refused at import rather than on a client's
    server.
    """
    values: dict[str, str] = {}
    for step in WIZARD:
        answers = draft.values_for(step.key)
        for question in step.questions:
            if not question.setting:
                continue
            given = answers.get(question.field.name, "").strip()
            if given:
                values[question.setting] = given

    web = draft.values_for(StepId.COMPANY).get("web_address", "").strip()
    if web:
        values["INSTALL_OIDC_REDIRECT_URIS"] = f"{web.rstrip('/')}{CALLBACK_PATH}"
    source = draft.values_for(StepId.STAFF_SOURCE).get("staff_source", "").strip()
    if source:
        values["INSTALL_BROKERED_DIRECTORY"] = STAFF_SOURCE_BROKERS[source]
    return MappingProxyType(values)


@dataclass(frozen=True)
class Applied:
    """What one completed wizard produces, and nothing it has already done.

    Returned rather than written, so the single act at the end is the caller's and this module
    still has no connection and no vault. The pieces go to different places: the grant to
    `brain.identity.roles`, the settings to this install's environment file, the spent
    enrolment back to wherever the enrolment is kept, because an enrolment spent and not
    stored is one that works a second time, and the provider key to the vault.

    `provider_key` is on the result and never in `settings`, because
    `brain.ops.provider_keys` is where a provider key lives and an environment file is not it.
    **It is also the one field here excluded from the repr**, which is not decoration: an
    exception raised anywhere holding this object renders every field into the traceback, and
    a traceback is written to a log by whatever catches it. `brain.firstrun.Claim` solves the
    same problem by having no such field at all, which is not available here: somebody has to
    carry the key from the screen to the vault, and this is that somebody.

    The two guards say what the model screen already said, at the type rather than at the
    screen. A local profile carrying a key is an install where the routing will never reach
    that credential and the person believes it will; a provider named with no key, or a key
    with no provider, is half an answer that nothing downstream can act on.
    """

    grant: RoleGrant
    settings: Mapping[str, str]
    enrolment: Enrolment
    provider: str = ""
    provider_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        # Read out first so the condition fits on one line. `.scratch/guard_audit.py` mutates
        # an `if` by rewriting the line it starts on and skips one whose condition wraps, and
        # a guard the audit cannot reach is one that will be quietly skipped for ever.
        profile = self.settings.get("INSTALL_MODEL_PROFILE", LOCAL_ONLY)
        if profile == LOCAL_ONLY and (self.provider or self.provider_key):
            msg = (
                "this install keeps every question on its own hardware and also carries a "
                "provider credential, which nothing will ever reach and somebody believes in"
            )
            raise WizardError(msg)
        if bool(self.provider) != bool(self.provider_key):
            msg = (
                "a provider with no key and a key with no provider are both half an answer, "
                "and neither can be written into the vault as it stands"
            )
            raise WizardError(msg)


def apply_install(
    draft: Draft,
    enrolment: Enrolment,
    presented: str,
    *,
    principal_id: str,
    administrators: int,
    now: datetime,
) -> Applied:
    """The single act that turns a reviewed draft into an installation (M42.5.10, M42.5.6).

    Three refusals in one order, and the order is the argument. The wizard being closed is
    asked first, because an install that already has an administrator must not learn whether a
    code was right. The code is next, so an unfinished screen is not reported to somebody who
    has not shown they may be here. Then the answers, all of them at once, because an install
    missing two screens has two problems and fixing one leaves a wizard that still refuses.

    **This is where the code is spent.** Every other entry point verifies and drops what
    `claim` returns; this one keeps it, and the spent enrolment comes back on the result for
    the caller to store. A caller that stored the enrolment `unlock` produced would have spent
    it on the first screen.
    """
    assert_open(administrators)
    claimed = claim(enrolment, presented=presented, now=now)
    if not claimed.accepted:
        msg = (
            "that setup code was not accepted, and which of the three reasons it was is not "
            f"said here. {A_SERVER_WITH_AN_OPEN_WIZARD_BELONGS_TO_WHOEVER_FINDS_IT}"
        )
        raise WizardLockedError(msg)

    outstanding = [
        step.key.value for step in WIZARD if step.stores and not is_answered(step, draft)
    ]
    if outstanding:
        msg = f"these screens are not finished and nothing has been written: {outstanding}"
        raise WizardError(msg)

    provider = draft.values_for(StepId.MODEL_PROVIDER)
    return Applied(
        grant=first_administrator(
            claimed, principal_id=principal_id, administrators=administrators, now=now
        ),
        settings=settings_from(draft),
        enrolment=claimed.enrolment,
        provider=provider.get("model_provider", "").strip(),
        provider_key=provider.get("provider_key", "").strip(),
    )
