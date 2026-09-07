"""Creating the first administrator on an install where nobody exists yet, with no password.

Every system has this moment and almost every system solves it the same way: a default
account with a documented password, changed on first login by whoever remembers. That
default is published the instant it is written down, it is the same on every install, and
the window between the install finishing and somebody logging in is a window in which the
widest account in the system is reachable by anyone who can find the address. M41.2.4 says
"no default password anywhere", and this module is what that sentence costs.

**A one-time enrolment, not a credential.** The installer mints one secret, hands it to the
person who is going to become the administrator, and this module keeps only its digest. The
secret is presented once. It is then spent, and there is no state it can return to in which
it works again. That is the whole difference from a password: a password is a value that
keeps working, and a value that keeps working is a value somebody keeps. See
`A_VALUE_THAT_GOES_ON_WORKING_IS_A_CREDENTIAL`.

**Nothing here mints anything, and that is deliberate rather than incomplete.** There is no
function in this module that produces a secret, no constant holding one, and no default
anywhere that could stand in for one. The value belongs to the installation and is generated
at install time on the client's own machine; what this module owns is the rule about what may
be done with it. A module that could generate a token is a module whose test suite contains
one, and a token in a test suite is a token in a repository. See
`THE_VALUE_IS_THE_INSTALLERS_AND_THE_RULE_IS_OURS`.

**No refusal says why.** An enrolment that is expired, one that is already spent and one that
was never right refuse identically, because the difference between them is information about
whether somebody guessed correctly, and an attacker with a distinguishable refusal has an
oracle. The reason is carried on the result for the ledger, where the person presenting the
token cannot read it. This is the platform's DENIED-and-ABSENT rule applied to a credential:
see `A_REFUSAL_THAT_SAYS_WHY_IS_AN_ORACLE`.

**And the door closes behind the first administrator.** Once one exists, first run is over
permanently. There is no parameter that reopens it, no flag on an enrolment that survives an
administrator existing, and `is_open` takes the count rather than a boolean somebody could
set. A second administrator is appointed by the first, through `brain.identity.roles`, which
is where appointments are reviewed. See `THE_FIRST_ADMINISTRATOR_CLOSES_THE_DOOR`.

**What is checked statically, and what is not.** `credential_default_gaps` reads the
deployment configuration for a credential that carries a value, which is the shape a default
password has in this repository: `docker-compose.keycloak.yml` already refuses one with `:?`
rather than `:-`, and its comment argues for a page. What that sweep does not read is `src`,
because ruff's `S105` and `S106` already refuse a hardcoded password in Python and a second
reader of the same rule is a second place for it to disagree.

Task ids: M41.2.4
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import re
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from brain.identity.roles import Role, RoleGrant

REPO: Final = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ written-down reasons
#: Why an enrolment is spent rather than valid until it expires.
A_VALUE_THAT_GOES_ON_WORKING_IS_A_CREDENTIAL: Final = (
    "A value that goes on working is a value somebody keeps: in a terminal history, in the "
    "message it was sent in, in the ticket where the install was tracked. The property that "
    "makes this not a password is that presenting it consumes it, so the copy left behind is "
    "worth nothing. An enrolment that merely expired would be a password with an end date, "
    "and the end date is always further away than the person who wrote it down expects."
)

#: Why this module has no generator.
THE_VALUE_IS_THE_INSTALLERS_AND_THE_RULE_IS_OURS: Final = (
    "A function that produces a secret needs a test, and a test that exercises it either "
    "contains a value or asserts nothing. Neither belongs in a repository shipped to every "
    "client. So the secret is minted at install time on the client's own machine and reaches "
    "this module as a digest of something already gone: what lives here is the rule about "
    "how many times it may be presented and what it may be exchanged for."
)

#: Why every refusal is identical.
A_REFUSAL_THAT_SAYS_WHY_IS_AN_ORACLE: Final = (
    "Expired, already spent and simply wrong are three different facts, and telling them "
    "apart tells somebody whether the value they presented was ever right. That is the same "
    "disclosure this platform refuses everywhere else: DENIED and ABSENT read alike to a "
    "person. The reason travels on the result for the ledger, which is read by the operator "
    "and not by whoever is at the screen."
)

#: Why first run cannot be reopened.
THE_FIRST_ADMINISTRATOR_CLOSES_THE_DOOR: Final = (
    "First run exists because there is nobody to authorise an appointment. The moment an "
    "administrator exists, there is, and every later appointment goes through the review "
    "`brain.identity.roles` performs. A first-run path that stayed available would be a "
    "permanent unauthenticated route to the widest role in the system, guarded by a value "
    "somebody printed once, months ago, and probably still has."
)

#: Why a path to a secret is not a secret.
A_PATH_TO_A_CREDENTIAL_IS_NOT_ONE: Final = (
    "`TOKEN_FILE=/root/.coolify-deploy-token` names where a credential lives, which is the "
    "entire point of keeping one in a file rather than in a variable. A sweep reporting it "
    "would be a sweep reporting the correct pattern, and the first thing anybody does with a "
    "check that fires on the right answer is switch it off."
)

# ------------------------------------------------------------------ the enrolment
#: How long an enrolment may stand before it expires. One working hour, because an install
#: is finished by somebody who is present: a window long enough to cover a coffee is long
#: enough, and a window measured in days is a credential.
DEFAULT_WINDOW: Final = timedelta(hours=1)

#: Nothing may ask for longer. A ceiling an operator can raise is one that gets raised during
#: the install that made it inconvenient, which is the same argument
#: `brain.identity.roles.MAX_BREAK_GLASS` makes about its own.
MAX_WINDOW: Final = timedelta(hours=24)

#: What a digest looks like. sha256, lower-case hex, so a truncated or differently-derived
#: value is refused at construction rather than compared and quietly never matching.
DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: The shortest secret this will accept a digest of. Not a password policy: it is the length
#: below which a one-time value can be guessed inside its own window, and it is checked
#: against the secret rather than the digest because the digest of a short secret looks like
#: the digest of a long one.
MIN_SECRET_CHARS: Final = 32


class FirstRunError(Exception):
    """Raised when first run is asked for something it must not do."""


class Refusal(enum.StrEnum):
    """Why a claim did not succeed. For the ledger, never for the person at the screen.

    Three members and no `UNKNOWN`. A fourth meaning "something else" is where a future
    branch goes when nobody wants to think about which of these it is, and the value of this
    enum is that every path through `claim` lands on a stated one.
    """

    #: The window has passed.
    EXPIRED = "expired"
    #: It has already been presented once.
    SPENT = "spent"
    #: It did not match.
    WRONG = "wrong"


def digest_of(secret: str) -> str:
    """The digest an enrolment is opened with. Derives; does not generate.

    sha256 without a salt or a work factor, and both absences are deliberate. A salt protects
    a stored value against a table of precomputed hashes of *guessable* inputs, and this
    input is a high-entropy one-time value rather than something a person chose; a work
    factor slows an attacker who has the stored digest and time, and this digest is worthless
    an hour after it is written. What matters here is that the secret is not stored, and a
    plain digest achieves exactly that.
    """
    if len(secret) < MIN_SECRET_CHARS:
        msg = (
            f"an enrolment secret of {len(secret)} character(s) can be guessed inside its own "
            f"window; {MIN_SECRET_CHARS} is the floor"
        )
        raise FirstRunError(msg)
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Enrolment:
    """One chance to become the first administrator.

    **There is no field on this holding the secret**, and that is the model rather than an
    omission: a structure with somewhere to put it is a structure that will have it put
    there, by a debug branch or by a serialiser. `credential_field_gaps` asserts the absence
    against the names such a field would have.
    """

    digest: str
    issued_at: datetime
    expires_at: datetime
    #: When it was presented. Set once, and an enrolment carrying it is finished.
    claimed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not DIGEST.match(self.digest):
            msg = "an enrolment digest is 64 lower-case hex characters; this is not one"
            raise FirstRunError(msg)
        for name, value in (("issued_at", self.issued_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None:
                msg = f"{name} is naive, and a naive time compares wrongly against an aware one"
                raise FirstRunError(msg)
        if self.expires_at <= self.issued_at:
            msg = "an enrolment that expires before it is issued can never be presented"
            raise FirstRunError(msg)
        if self.expires_at - self.issued_at > MAX_WINDOW:
            msg = (
                f"an enrolment window of {self.expires_at - self.issued_at} is longer than "
                f"{MAX_WINDOW}, at which point it is a credential rather than an enrolment"
            )
            raise FirstRunError(msg)
        if self.claimed_at is not None and self.claimed_at.tzinfo is None:
            msg = "claimed_at is naive"
            raise FirstRunError(msg)

    @property
    def spent(self) -> bool:
        return self.claimed_at is not None


def open_enrolment(
    *, digest: str, issued_at: datetime, window: timedelta = DEFAULT_WINDOW
) -> Enrolment:
    """Open the one enrolment an install gets, from a digest the installer supplies.

    Takes a digest and never a secret, so there is no call anywhere in this repository that
    has a secret in it. See `THE_VALUE_IS_THE_INSTALLERS_AND_THE_RULE_IS_OURS`.
    """
    if window <= timedelta(0):
        msg = "an enrolment window has to be positive; this one closes before it opens"
        raise FirstRunError(msg)
    return Enrolment(digest=digest, issued_at=issued_at, expires_at=issued_at + window)


@dataclass(frozen=True)
class Claim:
    """The outcome of presenting a secret, and the enrolment as it now stands.

    Carries the enrolment back rather than mutating one, so the spent state is a value the
    caller has to store. An in-place flag would make "was it spent" a question about an
    object's history, which is unanswerable after a restart.

    **No field holds what was presented.** A `presented` or `attempted` field would put the
    secret in whatever writes this to a log, which is exactly where a credential goes to
    live forever.
    """

    accepted: bool
    enrolment: Enrolment
    #: Populated only on a refusal, and only for the ledger.
    reason: Refusal | None = None

    def __post_init__(self) -> None:
        if self.accepted and self.reason is not None:
            msg = "an accepted claim carries a refusal reason; one of the two is wrong"
            raise FirstRunError(msg)
        if not self.accepted and self.reason is None:
            msg = "a refused claim with no reason is one the ledger cannot record"
            raise FirstRunError(msg)


def claim(enrolment: Enrolment, *, presented: str, now: datetime) -> Claim:
    """Present a secret once.

    The comparison is `hmac.compare_digest` rather than `==`, because a short-circuiting
    comparison over a hex digest leaks how many leading characters were right, and an
    attacker who can measure that recovers the digest one character at a time.

    A refusal is a refusal. Which of the three it was is on the result for the ledger and is
    not the caller's to show anybody: see `A_REFUSAL_THAT_SAYS_WHY_IS_AN_ORACLE`.

    **The spend happens on a correct presentation and on the window closing, and not on a
    wrong one.** A wrong guess that spent the enrolment would let anybody who can reach the
    endpoint destroy an install's only way in, which turns a guessing attack into a denial of
    service with a guaranteed hit rate.
    """
    if now.tzinfo is None:
        msg = "a naive now compares wrongly against an aware expiry"
        raise FirstRunError(msg)
    if enrolment.spent:
        return Claim(accepted=False, enrolment=enrolment, reason=Refusal.SPENT)
    if now >= enrolment.expires_at:
        return Claim(accepted=False, enrolment=enrolment, reason=Refusal.EXPIRED)
    try:
        offered = digest_of(presented)
    except FirstRunError:
        # A secret too short to be one of ours cannot match, and saying so separately would
        # be the oracle this function exists to avoid.
        return Claim(accepted=False, enrolment=enrolment, reason=Refusal.WRONG)
    if not hmac.compare_digest(offered, enrolment.digest):
        return Claim(accepted=False, enrolment=enrolment, reason=Refusal.WRONG)
    return Claim(
        accepted=True,
        enrolment=Enrolment(
            digest=enrolment.digest,
            issued_at=enrolment.issued_at,
            expires_at=enrolment.expires_at,
            claimed_at=now,
        ),
    )


def is_open(*, administrators: int) -> bool:
    """Whether first run is still available, from the number of administrators there are.

    Takes the count rather than a boolean, and there is no `force` beside it. A boolean is a
    value somebody sets; a count is a fact about the system. See
    `THE_FIRST_ADMINISTRATOR_CLOSES_THE_DOOR`.
    """
    if administrators < 0:
        msg = "a negative number of administrators is not a state this system can be in"
        raise FirstRunError(msg)
    return administrators == 0


#: What the first administrator's grant records as its author. There is no person to name:
#: the appointment was authorised by holding the enrolment, and recording a human's name
#: would put a false statement in the one row that explains where the widest role came from.
GRANTED_BY: Final = "first-run"

#: The reason on that grant, which is required and is read during every later review.
GRANT_REASON: Final = "first administrator, created at first run against a one-time enrolment"


def first_administrator(
    claimed: Claim, *, principal_id: str, administrators: int, now: datetime
) -> RoleGrant:
    """The Super Admin grant a spent enrolment buys, and nothing else.

    Three refusals, and each is a different way the same mistake is made. A claim that was
    not accepted buys nothing, so a caller that ignored `accepted` cannot proceed by passing
    the object on. An install that already has an administrator is past first run, whatever
    a caller believes. And a claim whose enrolment is not marked spent is one the caller
    built rather than one `claim` returned, which is how a replay is written by accident.

    The grant is standing rather than a deputy appointment: `brain.identity.roles` keeps a
    floor of two standing Super Admins, and a deputy does not count towards it, so a first
    administrator who was a deputy would leave the install permanently below its own floor.
    """
    if not claimed.accepted:
        msg = "a refused claim appoints nobody"
        raise FirstRunError(msg)
    if not is_open(administrators=administrators):
        msg = (
            f"this install already has an administrator. {THE_FIRST_ADMINISTRATOR_CLOSES_THE_DOOR}"
        )
        raise FirstRunError(msg)
    if claimed.enrolment.claimed_at is None:
        msg = (
            "the enrolment on this claim is not marked spent, so it was not produced by "
            f"`claim`. {A_VALUE_THAT_GOES_ON_WORKING_IS_A_CREDENTIAL}"
        )
        raise FirstRunError(msg)
    return RoleGrant(
        principal_id=principal_id,
        role=Role.SUPER_ADMIN,
        granted_by=GRANTED_BY,
        reason=GRANT_REASON,
        granted_at=now,
    )


# ------------------------------------------------------------------ the static rules
#: Field names that would turn one of the models above into somewhere a secret lives.
_SECRET_NAMES: Final[frozenset[str]] = frozenset(
    {
        "secret",
        "password",
        "token",
        "presented",
        "attempted",
        "plaintext",
        "value",
        "credential",
        "passphrase",
    }
)

#: The models a secret could arrive on. Named so the scan below runs against a stated list
#: rather than against whatever this module happens to define today.
FIRST_RUN_MODELS: Final[tuple[type, ...]] = (Enrolment, Claim)


def credential_field_gaps(models: tuple[type, ...] = FIRST_RUN_MODELS) -> tuple[str, ...]:
    """Every field on these models that a secret could be stored in.

    Scanned rather than trusted, because the way this rule dies is one field added during an
    incident to work out why a token was not matching, and never taken out.
    """
    # `fields` wants a dataclass instance or type and mypy cannot see that every entry is
    # one, because the parameter is typed as a tuple of plain types so a caller can pass a
    # deliberately careless class in a test.
    return tuple(
        f"{model.__name__}.{one.name} could hold the secret itself"
        for model in models
        for one in fields(model)
        if one.name.lower() in _SECRET_NAMES
    )


#: A name that holds a credential rather than describing one.
_CREDENTIAL_NAME = re.compile(
    r"(PASSWORD|PASSWD|SECRET|TOKEN|CREDENTIAL|PASSPHRASE|_KEY|_KEY_ID)", re.IGNORECASE
)

#: A name that says *where* a credential is rather than what it is. See
#: `A_PATH_TO_A_CREDENTIAL_IS_NOT_ONE`.
_NAMES_A_PLACE = re.compile(r"_(FILE|PATH|NAME|HEADER|URL|ENV|VAR|ID)$", re.IGNORECASE)

#: `NAME: value` in compose, `NAME=value` in an environment file or a shell script.
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")

#: A password sitting in the userinfo half of a URL, which is how one hides from a check
#: that only reads variable names.
_URL_PASSWORD = re.compile(r"://[^/\s:@]+:([^/\s@]+)@")

#: Where a credential default would actually be deployed. `src` is deliberately absent: ruff's
#: S105 and S106 already refuse a hardcoded password in Python, and a second implementation of
#: one rule is a second place for it to disagree.
CONFIGURATION: Final[tuple[str, ...]] = (
    "docker-compose*.yml",
    ".env.example",
    "ops/*.sh",
    "ops/deploy/*",
    "ops/vps/*",
)


def credential_default_gaps(repo: Path = REPO) -> tuple[str, ...]:
    """Every credential in the deployment configuration that carries a value (M41.2.4).

    A credential must be required, never defaulted. `docker-compose.keycloak.yml` already
    spells that `${KEYCLOAK_ADMIN_PASSWORD:?set KEYCLOAK_ADMIN_PASSWORD}`, which fails the
    deploy when it is unset rather than starting an identity provider anybody can take over.
    What this adds is that the same rule holds for every other credential, including the ones
    written next year.

    Three shapes are refused and one is not: a literal value, a `${VAR:-default}` with a
    non-empty default, and a password inside a URL. `${VAR}` and `${VAR:?...}` both pass, and
    so does an empty value, because an empty credential is one the system refuses to start
    with rather than one it starts with.
    """
    findings: list[str] = []
    for pattern in CONFIGURATION:
        for path in sorted(repo.glob(pattern)):
            if not path.is_file():
                continue
            where = path.relative_to(repo).as_posix()
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                findings.extend(f"{where}:{number}: {one}" for one in _line_gaps(line))
    return tuple(findings)


def _line_gaps(line: str) -> tuple[str, ...]:
    """What one configuration line says about a credential, if anything."""
    bare = line.split("#", 1)[0]
    matched = _ASSIGNMENT.match(bare)
    if not matched:
        return ()
    name, raw = matched.group(1), matched.group(2).strip().strip("\"'")

    embedded = _URL_PASSWORD.search(raw)
    if embedded and not embedded.group(1).startswith("${"):
        return (
            f"{name} carries a password inside a URL, which is a default credential that a "
            "check reading variable names alone would not see",
        )
    if not _CREDENTIAL_NAME.search(name) or _NAMES_A_PLACE.search(name):
        return ()
    if not raw:
        return ()
    if raw.startswith("${"):
        _, separator, fallback = raw.partition(":-")
        if separator and fallback.rstrip("}"):
            return (
                f"{name} defaults to {fallback.rstrip('}')!r}. A credential must be required, "
                "the way KEYCLOAK_ADMIN_PASSWORD is with `:?`, or the default is the value "
                "every install that forgets to set it runs with",
            )
        return ()
    return (f"{name} carries the literal value {raw!r}, which is a default password",)


def first_run_gaps(repo: Path = REPO) -> tuple[str, ...]:
    """Both static rules, for a sweep and for anything else that wants one answer."""
    return (*credential_field_gaps(), *credential_default_gaps(repo))
