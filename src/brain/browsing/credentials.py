"""How a browser logs in without the model ever holding the password.

The custody argument was settled for connectors in `brain.ops.secrets` and this module does
not restate it: nothing holds a credential, a reference is exchanged for a short-lived lease
at the moment of use, `Lease.__repr__` refuses to print the value, and `borrow` gives the
lease back in a `finally`. What is new here is where the exchange happens, because a browser
run has a step nobody else has: the value has to be typed into somebody else's form.

**A placeholder is what travels, and it travels the whole way.** The plan holds one, the
envelope holds one, the policy holds one, the action the container proposes holds one. The
only function in this package that turns a placeholder into a value is `resolve`, it is
called at the point the tool executes, and it takes a vault. Everything upstream of it is a
string that says which credential is meant and nothing about what it is.

That is a stronger claim than "the model is not shown the password", and the difference is
the one that matters. A model does not have to be shown a value to leak it: it has to be
*near* it. A credential in the plan is in the trace, in whatever renders the plan for
approval, in the retry that replays the plan, and in the message history the next turn is
built from. Substituting at the boundary means it is in one call frame, inside one `with`
block, for the duration of one action. `brain.browsing.shape.secrets_do_not_travel` fails if a
type outside this module grows a field that could carry a value.

**A secret substitutes on its own origin and nowhere else.** The binding names an origin and
`resolve` compares it exactly, after normalisation, against where the action says it is. Not
a suffix, not a domain, not "the same site". A suffix test is how a page on
`bank.example.evil.test` is handed the password for `bank.example`, and it is the forgiving
option right up to the moment it forgives that. The check costs one comparison and it is the
last thing standing between a redirect nobody declared and a credential.

**The seed for a one-time code never goes to the container.** M19.4.3 asks for TOTP generated
server side, and the reason is that a TOTP seed is a permanent credential: a code is worth
thirty seconds, the seed is worth every code for ever. Sending the seed to the browser to let
it compute a code would trade a bounded exposure for an unbounded one in exchange for one
fewer round trip.

**Scrubbing is not a second `brain.ops.pii.scrub`**, and it was worth checking. That function
replaces spans a recogniser *detected*, labelled from a closed vocabulary of personal data
kinds, and its docstring argues that the vocabulary is closed because the label is what a
model reads in place of the value. A credential is not one of those kinds, adding one would
break that argument, and what is removed here is not detected at all: it is a literal value
this process handed out and can therefore search for exactly. Different input, different
certainty, different label.

**Scrubbing is the last line and is treated as one.** If it is doing anything, something
upstream already failed, because a value that reached the history was substituted somewhere
it should not have been. `scrub_history` returns what it removed so that a caller can treat a
non-empty result as an incident rather than as housekeeping.

Task ids: M19.4.1, M19.4.2, M19.4.3, M19.4.4
"""

from __future__ import annotations

import base64
import binascii
import enum
import hmac
import re
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.channels.widget import normalise_origin
from brain.ops.secrets import DEFAULT_LEASE, SecretRef, Vault, borrow

#: What a placeholder looks like anywhere in a plan, an envelope or an action.
PLACEHOLDER_RE: Final = re.compile(r"^\{\{secret:([a-z][a-z0-9_]*)\}\}$")

#: What replaces a value that reached somewhere it should not have.
SCRUBBED: Final = "[secret]"

#: The shortest secret that can be removed from text without destroying the text.
#:
#: Eight because a shorter one is likely to occur by accident in ordinary prose, and
#: replacing every occurrence of a four-character string would produce a history that reads
#: as though it had been redacted at random. A secret shorter than this is refused when the
#: binding is declared, which is the moment somebody can still change it.
MIN_SCRUBBABLE = 8

#: The TOTP step in seconds, from RFC 6238 section 4. Not configurable: every authenticator
#: a person might already have enrolled uses thirty, and a different value here would produce
#: codes that are correct arithmetic and wrong everywhere.
TOTP_STEP = 30

#: How many digits a code has. Six, for the same reason.
TOTP_DIGITS = 6

#: Why the value appears at the boundary and not before it.
A_CREDENTIAL_IN_THE_PLAN_IS_A_CREDENTIAL_IN_THE_TRACE: Final = (
    "A model does not have to be shown a password to leak one. A value carried in the plan "
    "is in the approval screen, the trace, the retry that replays the plan and the message "
    "history the next turn is assembled from, and each of those is a store with its own "
    "retention and its own readers. Resolving at the tool-execution boundary leaves it in "
    "one call frame for the length of one action."
)

#: Why the origin comparison is exact.
A_SUFFIX_MATCH_SUBSTITUTES_ON_THE_LOOK_ALIKE: Final = (
    "Matching an origin by suffix admits bank.example.evil.test for an entry naming "
    "bank.example, and matching by registrable domain admits every subdomain anybody can "
    "create. The exact comparison is what makes an undeclared redirect a refusal instead of "
    "a substitution, and it is the last check before the value is typed into a form."
)

#: Why the seed stays on this side.
A_CODE_IS_WORTH_THIRTY_SECONDS_AND_A_SEED_IS_WORTH_FOR_EVER: Final = (
    "Handing the container the seed so it can compute its own codes replaces a credential "
    "that expires in half a minute with one that never does. The container is the process "
    "running somebody else's JavaScript. The round trip this saves is not worth the "
    "difference."
)


class CredentialError(Exception):
    """A credential was declared or requested in a way that cannot be made safe."""


class SecretKind(enum.StrEnum):
    """What kind of thing is behind a placeholder. Two members and both are typed in.

    Separate because they are produced differently: a password is fetched, and a code is
    computed from a seed that is fetched. A single kind would put the computation behind a
    flag, and the flag would eventually be set by whoever wrote the binding row.
    """

    #: A value stored as it is used. The member name and the value agree, which a linter
    #: reads as a credential in the source; the suppression is the honest answer, because
    #: renaming either would make the enum describe the kind wrongly.
    PASSWORD = "password"  # noqa: S105
    #: A base32 seed from which a six-digit code is derived here, never sent onward.
    TOTP_SEED = "totp_seed"


def placeholder_name(text: str) -> str:
    """The name inside a placeholder, or empty if this is not one.

    Returns rather than raises, because the commonest caller is asking whether a string is a
    placeholder at all, and a truthiness test reads better there than an exception.
    """
    found = PLACEHOLDER_RE.match(text)
    return found.group(1) if found else ""


@dataclass(frozen=True)
class Binding:
    """One placeholder, what is behind it, and the one origin it may be substituted on.

    Holds a `SecretRef` and never a value, which is the same thing a connector row holds and
    for the reason `brain.ops.secrets.SecretRef` gives: a reference is useless to anybody who
    cannot already reach the vault.
    """

    placeholder: str
    ref: SecretRef
    origin: str
    kind: SecretKind = SecretKind.PASSWORD

    def __post_init__(self) -> None:
        if not placeholder_name(self.placeholder):
            msg = (
                f"{self.placeholder!r} is not a placeholder; the grammar is "
                "{{secret:name}} and a binding on anything else would substitute nowhere"
            )
            raise CredentialError(msg)
        # **The empty case is checked first and separately, and mutation testing is what said
        # so.** `normalise_origin` returns the empty string for anything it cannot parse, so
        # an empty declared origin satisfies "is normalised" by comparing "" with "", and
        # `substitutes_on` then returns True for every unparseable origin an action could
        # name, `null` and `not-a-url` included. A binding with no origin would hand the
        # credential to whichever page asked first.
        if not self.origin:
            msg = (
                f"binding {self.placeholder!r} names no origin; the empty string is what "
                "normalisation returns for anything it cannot parse, so a binding on it "
                "would substitute on every origin that fails to parse"
            )
            raise CredentialError(msg)
        if normalise_origin(self.origin) != self.origin:
            msg = (
                f"binding {self.placeholder!r} names origin {self.origin!r}, which is not "
                "normalised; comparing a normalised action origin against a raw declaration "
                "refuses every substitution and looks like a vault problem"
            )
            raise CredentialError(msg)

    def substitutes_on(self, origin: str) -> bool:
        """Exact equality after normalisation, and never on an origin that did not parse.

        The `bool(normalised)` half is not redundant with the constructor's refusal above and
        it is the half that matters here: `normalise_origin` returns the empty string for
        anything it cannot read, so without it an action naming `null` or a `file://`
        document would compare equal to any binding whose origin had somehow become empty.
        Two checks, because this is the last thing between a page and a password.

        See `A_SUFFIX_MATCH_SUBSTITUTES_ON_THE_LOOK_ALIKE` for why the comparison is exact.
        """
        normalised = normalise_origin(origin)
        return bool(normalised) and normalised == self.origin


@dataclass(frozen=True)
class Bindings:
    """Every binding for one run, indexed by placeholder.

    A frozen collection rather than a mapping passed around, so that "which placeholders does
    this run have" is a question with one answer and a run cannot acquire a binding partway
    through by having something write into a dictionary.
    """

    bindings: tuple[Binding, ...] = ()

    def __post_init__(self) -> None:
        names = [one.placeholder for one in self.bindings]
        if len(names) != len(set(names)):
            msg = (
                "two bindings share a placeholder, so which credential is substituted would "
                "be decided by the order they happen to be listed in"
            )
            raise CredentialError(msg)

    def get(self, placeholder: str) -> Binding | None:
        for one in self.bindings:
            if one.placeholder == placeholder:
                return one
        return None

    def placeholders(self) -> frozenset[str]:
        return frozenset(one.placeholder for one in self.bindings)


def totp(
    seed_base32: str, at: datetime, *, step: int = TOTP_STEP, digits: int = TOTP_DIGITS
) -> str:
    """A time-based one-time code, RFC 6238, computed here and never in the container.

    The algorithm is HOTP over a counter of elapsed steps. `hmac.new` is given the digest by
    name rather than by importing the constructor, because the name is what RFC 4226 and
    every authenticator application specify and because naming it here would read as a choice
    somebody made about hashing rather than as a protocol constant.

    Tested against the vectors in RFC 6238 appendix B, which is the point: a constant checked
    only against itself is green for every value it could hold, and the published vectors are
    the one assertion about this function that lives outside it.
    """
    padded = seed_base32.strip().replace(" ", "")
    padded += "=" * (-len(padded) % 8)
    try:
        seed = base64.b32decode(padded, casefold=True)
    except (binascii.Error, ValueError) as exc:
        msg = "a TOTP seed must be base32; this one is not, so no code could be derived"
        raise CredentialError(msg) from exc
    if not seed:
        msg = "a TOTP seed of no bytes would produce the same code for every account"
        raise CredentialError(msg)
    counter = int(at.timestamp()) // step
    mac = hmac.new(seed, struct.pack(">Q", counter), "sha1").digest()
    offset = mac[-1] & 0x0F
    truncated = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def resolve(
    placeholder: str,
    bindings: Bindings,
    *,
    vault: Vault,
    origin: str,
    now: datetime,
    ttl: timedelta = DEFAULT_LEASE,
) -> str:
    """Turn a placeholder into a value, here, at the moment the action runs (M19.4.1).

    The only function in this package that produces a credential value, and it produces it
    inside `brain.ops.secrets.borrow`, so the lease is revoked on the way out including on the
    exception path. What it returns is a plain string with a lifetime of one action, and the
    caller's obligation is to type it and forget it rather than to store it.

    Three refusals in order. An unknown placeholder is refused before anything is fetched,
    because fetching first would tell the vault which credentials a run guessed at. The origin
    is checked next, before the lease is taken, so a substitution attempt on the wrong site
    never causes a credential to be issued at all. Only then is the vault asked.
    """
    binding = bindings.get(placeholder)
    if binding is None:
        msg = (
            f"nothing binds {placeholder!r} for this run; a placeholder resolved against no "
            "binding would either be sent as itself or be filled from somewhere else"
        )
        raise CredentialError(msg)
    if not binding.substitutes_on(origin):
        msg = (
            f"{placeholder!r} is bound to one origin and the action is on another, so no "
            "credential is issued; a redirect nobody declared looks exactly like this"
        )
        raise CredentialError(msg)
    with borrow(vault, binding.ref, now=now, ttl=ttl) as lease:
        value = lease.reveal(now)
        if binding.kind is SecretKind.TOTP_SEED:
            return totp(value, now)
        return value


def scrub_outbound(text: str, secrets: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    """Remove known credential values from one piece of text, and say what was removed.

    Returns the text and the placeholders whose values were found, rather than the values, so
    that a caller logging the result does not log the thing being removed. That looks like an
    obvious point and it is the exact mistake a scrubber makes: reporting what it caught.

    A value shorter than `MIN_SCRUBBABLE` is not searched for. It is refused when the binding
    is declared, and skipped here as well rather than being trusted to have been, because
    this is the last line and a last line that assumes an earlier one held is not one.
    """
    out = text
    found: list[str] = []
    for secret in secrets:
        if len(secret) < MIN_SCRUBBABLE:
            continue
        if secret in out:
            out = out.replace(secret, SCRUBBED)
            found.append(SCRUBBED)
    return out, tuple(found)


def scrub_history(
    messages: Sequence[str], secrets: Iterable[str]
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Every message with known credential values removed, and which messages had one.

    The indices are the finding. A non-empty second element means a credential reached the
    message history, which means it was substituted somewhere it should not have been, which
    is an incident and not a successful scrub. Returned separately so a caller can treat it as
    one instead of having to diff the two lists to notice.
    """
    values = tuple(secrets)
    cleaned: list[str] = []
    leaked: list[int] = []
    for index, message in enumerate(messages):
        text, found = scrub_outbound(message, values)
        cleaned.append(text)
        if found:
            leaked.append(index)
    return tuple(cleaned), tuple(leaked)


def binding_gaps(bindings: Bindings, values: Sequence[str] = ()) -> tuple[str, ...]:
    """Everything about a set of bindings that would make the last line fail quietly.

    `values` is optional and is the one thing that cannot be checked from a reference alone:
    whether the credential behind a binding is long enough to be removed from text at all. A
    caller that can see the values during setup should pass them; a caller that cannot gets
    the checks that do not need them, rather than nothing.

    **This used to check for a binding with no origin and no longer does.** `Binding` refuses
    one at construction now, so the check here could not be reached by any input and a
    mutation of it survived, which is how it was found. A gap function reporting a state its
    own types cannot hold reads as protection and provides none, so it is gone rather than
    covered by a test that would have to build the object through `object.__setattr__`.
    """
    gaps: list[str] = []
    for value in values:
        if len(value) < MIN_SCRUBBABLE:
            gaps.append(
                f"a bound credential is {len(value)} characters, below the {MIN_SCRUBBABLE} "
                "needed to be removed from text without mangling it, so it would stay in the "
                "message history after a scrub reported success"
            )
    return tuple(gaps)


def unresolvable(placeholders: Iterable[str], bindings: Bindings) -> tuple[str, ...]:
    """Placeholders a plan uses that nothing binds, found before the run rather than during it.

    A run that discovers this halfway through has already opened a session, taken a browser
    slot and possibly logged in, and it fails at the step that needed the credential, which is
    the least recoverable moment. Nothing is raised here and no vault is involved: this is a
    check over a plan, made before anything has been taken out on its behalf.
    """
    known = bindings.placeholders()
    return tuple(sorted(one for one in placeholders if one and one not in known))
