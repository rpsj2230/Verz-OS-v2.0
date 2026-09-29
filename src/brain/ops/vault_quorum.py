"""How the vault's recovery key is split, who holds a piece, and what happens to the root token.

**Since 2026-09-29 the vault opens itself, and this module decides the emergency spare.** Until then
every restart of the vault needed three of five people to type an unseal piece, and a release that
changed a policy needed the same three to generate a root token. On 2026-09-29 a release changed two
policies, nobody could find three pieces, and the owner decided (`docs/needs-rupash.md` item 114):
the vault unseals itself from a key file only root on the server can read, every release applies its
own policies with a narrow deploy token, and the pieces become **recovery** pieces, an optional
emergency spare chosen at install. A recovery piece does not open the vault; with the static seal
nothing but the key file does. What a recovery quorum still does is generate a root token (`bao
operator generate-root`) when the deploy token has lapsed or a policy only root may write has
changed, which is why the numbers are still worth refusing when they are wrong.

**Two choices, and the default is the simple one.** `SINGLE_RECOVERY_KEY` is one recovery key,
written by the installer to a root-only file for whoever runs the install to move into a password
manager. `RECOVERY_SPLIT` is the three-of-five the owner decided in item 17, kept as the stricter
choice (`--recovery-split` on the installer) for a company that wants no single person able to
make a root token. The trade-off the owner accepted is written in item 114 in plain words: on one
server, anyone with root can open the vault, and that person can already read the running
application's memory, so pieces held by five people bought ceremony rather than protection.

**The split is still an object, and the rule the module exists to keep has not changed: the
numbers cannot be in two places disagreeing.** The shell accepts every wrong combination silently,
and each looks like the shape of the right answer. `-recovery-shares=5 -recovery-threshold=1`
initialises perfectly and hands five people a key each of them can make a root token with alone;
`-recovery-shares=5 -recovery-threshold=5` means one lost piece ends the emergency route for good.
Neither is a typo a reviewer catches by reading. One key on its own is not a split and is not
refused as one: it is the named single-key choice, and the split rules apply only to a split.

**A frozen dataclass, not a pydantic model, and the dependency is not the reason.** Pydantic's
value is parsing untrusted input at a trust boundary, and there is none here: this object is built
from literals in this file, under review, and never from a request body or an environment
variable. Pydantic would helpfully turn `shares="5"` into `5`, and for a number this consequential
a string is a mistake that should stop a type check rather than be quietly normalised.

**Source, not a database row.** The split is fixed at `bao operator init` and the only way to
change it afterwards is `bao operator rekey -target=recovery`, which itself needs the current
recovery quorum. A save button that changed a number the vault ignores would report success for a
change that did not happen, and this policy governs the vault that holds the database's
neighbours' credentials, so keeping it in that database makes it unreadable when it is needed.

**Rejected: keeping the root token in a sealed envelope.** An envelope protects the paper, not the
token: it is still live, still bypasses every policy in `ops/openbao/policies`, and appeared in
whatever terminal printed it. The audit log records a root token as an ordinary accessor HMAC, so
no query distinguishes "somebody opened the envelope" from legitimate work. `bao operator
generate-root` rebuilds one from the recovery key and leaves a record, so the token is revoked and
`revoke_root_command` is the step that does it.

**Rejected: no recovery key at all.** The owner was offered it. Without one, a lapsed deploy token
or a change to the deploy policy itself has no way back short of a new vault and every credential
re-issued by hand, and the file costs one line in a password manager.

Task ids: M31.3.2.1
"""

from __future__ import annotations

from dataclasses import dataclass


class QuorumPolicyError(ValueError):
    """A quorum that would not be a quorum, refused before it can reach `bao operator init`.

    A `ValueError` subclass rather than a new base, so that an `except ValueError` around
    configuration loading still catches it while anything that wants to tell this apart from
    an ordinary bad value can.
    """


#: The container the vault runs in, from `ops/openbao/compose.yml`. Named here so the commands
#: this module renders are lines an operator can paste whole, rather than fragments they have
#: to wrap correctly at the moment they are least able to.
VAULT_CONTAINER = "brain-vault"

#: What an unnamed holder slot looks like. A prefix on the id rather than a boolean flag on
#: `Holder`, deliberately: a flag can be flipped to "configured" without a person being named,
#: and the whole point of the check is that naming somebody is the only way to pass it.
PLACEHOLDER_ID_PREFIX = "unassigned-"

#: The other half of the same guard. Somebody who invents a real-looking id and leaves the
#: name alone has still named nobody, and a check on the id alone would let that through.
PLACEHOLDER_NAME = "UNASSIGNED"

#: What `UNSEAL.md` tells an operator to run to see the numbers and whether the holders have
#: been named. Here rather than only in the runbook so a test can hold the two together; if
#: this module is ever renamed or moved, this string moves with it and the test comparing it
#: against `QuorumPolicy.__module__` fails rather than an operator finding out at a prompt.
PRINT_COMMAND = "uv run python -m brain.ops.vault_quorum"


@dataclass(frozen=True)
class Holder:
    """One person who holds one piece of the unseal key.

    Three fields, and only the third needed arguing about.

    `holder_id` is stable and `name` is not. Names change, get spelled two ways, and are
    shared: two people called Wei Ming are two pairs of hands and one string. The id is what
    the duplicate check compares and what any later question about custody refers to.

    `on_call` is the one operational fact stored, and it is here because the runbook already
    demands it: at least one piece has to sit outside the group that would be handling an
    incident, or a bad enough incident takes out the on-call rotation and the quorum together.
    Recording it turns a "should" in prose into a refusal at construction.

    **What is absent is the point.** No email address, no phone number, no department, no
    manager, no location. This file is committed, cloned by everyone who works on the project,
    and copied into every backup. Contact details in it would make it a single document
    answering "who do I have to reach to open this company's vault, and how" for anybody who
    obtains a copy. The five names are already the sensitive half; the way to reach them must
    not sit beside them, and whoever runs the setup knows how to contact their own colleagues.
    """

    holder_id: str
    name: str
    #: Whether this holder is in the incident on-call rotation.
    on_call: bool = True

    @property
    def identity(self) -> str:
        """The id as the duplicate check compares it: stripped and case-folded.

        Compared normalised because the ids in this file are typed by a person editing a
        list, and `r.jones` beside `R.Jones` is one pair of hands and two strings. Comparing
        raw is a guard that exists, is tested, and does not hold: five slots are accepted,
        the declared three-of-five is really two-of-four, and nothing anywhere says so.

        Over-merging is the safe direction. Two genuinely different holders whose ids differ
        only in case would be refused, and a refusal sends somebody back to a five-line list
        to look; under-merging lowers the threshold silently and forever.
        """
        return self.holder_id.strip().casefold()

    @property
    def is_placeholder(self) -> bool:
        """Whether this slot still names nobody.

        Three ways to be unnamed, because there are three ways to half-fill the slots and each
        of them looks configured at a glance: the shipped id left alone, the shipped name left
        alone, or a name blanked out ready to be typed over and then not typed over.
        """
        return (
            self.holder_id.startswith(PLACEHOLDER_ID_PREFIX)
            or not self.name.strip()
            or self.name.strip().upper() == PLACEHOLDER_NAME
        )


@dataclass(frozen=True)
class QuorumPolicy:
    """`shares` recovery pieces, any `threshold` of which make a root token.

    Every combination refused in `__post_init__` is one OpenBao accepts without complaint. The
    vault does not have an opinion about whether a split is a sensible custody arrangement; it
    has an opinion about whether the arithmetic parses. This is where the difference is caught,
    and it has to be caught before the one command that can never be run twice.

    **One key is the named exception, not a loophole.** `shares=1, threshold=1` is the single
    recovery key, and the three split rules (a threshold of one, a threshold equal to the share
    count, every holder on call) are rules about a split, so they are not asked of it. Anything
    else with a threshold of one is five copies of one key and is still refused.
    """

    shares: int
    threshold: int
    holders: tuple[Holder, ...]

    def __post_init__(self) -> None:
        if self.shares < 1:
            msg = f"a key split into {self.shares} pieces is no key at all"
            raise QuorumPolicyError(msg)

        if self.threshold < 1:
            msg = (
                f"a threshold of {self.threshold} would mean the vault opens with no piece "
                "presented"
            )
            raise QuorumPolicyError(msg)

        if self.threshold > self.shares:
            msg = (
                f"{self.threshold} of {self.shares} can never be met, so the vault would be "
                "initialised into a state nobody can ever open. OpenBao accepts this at init "
                "and the failure only appears at the first unseal, by which time the pieces "
                "have been distributed and the root token has scrolled off the screen."
            )
            raise QuorumPolicyError(msg)

        if len(self.holders) != self.shares:
            msg = (
                f"{self.shares} pieces and {len(self.holders)} named holders. A piece nobody "
                "is named against is a piece whose location cannot be stated, and in practice "
                "that is the one still sitting in the terminal it was printed in."
            )
            raise QuorumPolicyError(msg)

        if self.is_single_key:
            return

        if self.threshold == 1:
            msg = (
                f"a threshold of 1 over {self.shares} pieces is not a split: every holder can "
                "make a root token alone, and all the pieces buy is more copies of one key to "
                "lose. One key is the single-key choice, with one holder"
            )
            raise QuorumPolicyError(msg)

        if self.threshold == self.shares:
            msg = (
                f"{self.shares} of {self.shares} means one lost piece ends the emergency route "
                "for good: no root token can ever be generated again, so a lapsed deploy token "
                "or a change to the deploy policy has no way back short of a new vault and every "
                "credential re-issued by hand."
            )
            raise QuorumPolicyError(msg)

        seen: set[str] = set()
        doubled: set[str] = set()
        for holder in self.holders:
            if holder.identity in seen:
                doubled.add(holder.holder_id)
            seen.add(holder.identity)
        if doubled:
            msg = (
                f"{sorted(doubled)} holds more than one piece. Two pieces in one pair of hands "
                f"makes the declared threshold a fiction: {self.threshold}-of-{self.shares} "
                f"with one person holding two is really {self.threshold - 1}-of-"
                f"{self.shares - 1}, and the number everybody reasons with is the one written "
                "here."
            )
            raise QuorumPolicyError(msg)

        if all(holder.on_call for holder in self.holders):
            msg = (
                "every holder is on call, so the incident that takes out the on-call rotation "
                "takes the quorum with it. At least one piece has to sit outside the group "
                "that would be handling the outage."
            )
            raise QuorumPolicyError(msg)

    @property
    def is_single_key(self) -> bool:
        """Whether this is the one-key choice rather than a split."""
        return self.shares == 1 and self.threshold == 1

    @property
    def survivable_losses(self) -> int:
        """How many pieces can be lost with a root token still possible to generate."""
        return self.shares - self.threshold

    @property
    def is_configured(self) -> bool:
        """Whether every slot names a real person."""
        return not any(holder.is_placeholder for holder in self.holders)

    def assert_configured(self) -> None:
        """Refuse a policy whose holders are still the shipped placeholders.

        The failure this exists for is not a wrong number, it is a right-looking one. Five
        slots reading `UNASSIGNED` are a filled-in policy at a glance, and a vault initialised
        against them distributes five pieces to nobody in particular. Anything that acts on
        this policy as though the custody question were settled calls this first.
        """
        unnamed = [holder.holder_id for holder in self.holders if holder.is_placeholder]
        if unnamed:
            msg = (
                f"this policy still names nobody yet in {len(unnamed)} of {self.shares} slots "
                f"({', '.join(unnamed)}). Five pieces cannot be handed out until there are "
                "five people to hand them to, and a placeholder that reaches init is a piece "
                "with no owner from the first minute."
            )
            raise QuorumPolicyError(msg)


#: The stricter choice: the decision from `docs/needs-rupash.md` item 17, five pieces and any three.
#:
#: Shipped with placeholder holders on purpose, and `assert_configured` refuses it in that state:
#: the people who hold a company's pieces are that company's decision, never this file's. Since
#: item 114 it is a choice at install (`--recovery-split`), and the pieces it makes are recovery
#: pieces: they make a root token in an emergency and do not open the vault, which opens itself.
RECOVERY_SPLIT = QuorumPolicy(
    shares=5,
    threshold=3,
    holders=(
        Holder("unassigned-1", PLACEHOLDER_NAME),
        Holder("unassigned-2", PLACEHOLDER_NAME),
        Holder("unassigned-3", PLACEHOLDER_NAME),
        Holder("unassigned-4", PLACEHOLDER_NAME),
        # The slot the runbook requires to sit outside the on-call rotation, marked here so
        # the requirement survives whoever fills the names in without reading the prose.
        Holder("unassigned-5", PLACEHOLDER_NAME, on_call=False),
    ),
)

#: The default since `docs/needs-rupash.md` item 114: one recovery key, which the installer
#: writes to a root-only file for whoever installs to move into a password manager.
SINGLE_RECOVERY_KEY = QuorumPolicy(
    shares=1,
    threshold=1,
    holders=(Holder("unassigned-1", PLACEHOLDER_NAME, on_call=False),),
)

#: What an install gets unless it asks for the split.
DEFAULT_POLICY = SINGLE_RECOVERY_KEY

#: The installer flag that chooses the split, and the policy it chooses.
SPLIT_FLAG = "--recovery-split"


def init_args(policy: QuorumPolicy = DEFAULT_POLICY) -> tuple[str, ...]:
    """The `bao operator init` flags this policy means, and nothing else.

    **Recovery flags, because the vault's seal is the key file.** With a `static` seal OpenBao
    refuses to split an unseal key it does not have, and what it splits is the recovery key.
    Measured on OpenBao 2.4.1 on 2026-09-29: `-recovery-shares=1 -recovery-threshold=1` answers
    with one `Recovery Key 1:` line and an `Initial Root Token:` line, and the vault is unsealed
    before the command returns.

    Deliberately pure and deliberately not gated on `assert_configured`: the numbers were decided
    before the people were, and a renderer that refused to state them until five names existed
    would make the runbook unable to explain the shape of the thing it describes.
    """
    return (f"-recovery-shares={policy.shares}", f"-recovery-threshold={policy.threshold}")


def init_command(policy: QuorumPolicy = DEFAULT_POLICY) -> str:
    """The whole line, so `UNSEAL.md` can quote it verbatim and a test can hold the two equal.

    A whole line rather than the flags alone, because comparing flags would let the surrounding
    command drift while the check still passed, and the surrounding command is the half with the
    container name in it.
    """
    return f"docker exec -it {VAULT_CONTAINER} bao operator init " + " ".join(init_args(policy))


def revoke_root_command() -> str:
    """The line that ends the root token's existence. The `revoke_root` step of the runbook.

    Takes no policy: revocation is not parameterised by the split, and giving it an argument
    would suggest there is a configuration in which it is skipped. There is not. See the
    module docstring for why the sealed-envelope alternative was rejected.
    """
    return f"docker exec -it {VAULT_CONTAINER} bao token revoke -self"


def generate_root_command() -> str:
    """The line that starts making a root token from the recovery key, for the emergency section.

    The only route to a root token once the installer has revoked its own, and the reason a
    recovery key is kept at all. It prints a nonce and a one-time password and then asks for a
    recovery key, as many times as the threshold, at a prompt that does not echo.
    """
    return f"docker exec -it {VAULT_CONTAINER} bao operator generate-root -init"


def main() -> int:
    """`python -m brain.ops.vault_quorum`. Prints both choices and the lines `UNSEAL.md` quotes.

    Exits zero: the default needs nobody named, because one key is kept by whoever installs.
    The split's holders are listed with the slots still unnamed marked, and naming them is the
    installing company's decision, recorded outside this repository.
    """
    for label, policy in (("default", DEFAULT_POLICY), (SPLIT_FLAG, RECOVERY_SPLIT)):
        print(f"{label}: {policy.threshold} of {policy.shares} recovery pieces")
        print(f"  initialise:  {init_command(policy)}")
    print()
    print(f"revoke_root:   {revoke_root_command()}")
    print(f"generate_root: {generate_root_command()}")
    print()
    print(f"{SPLIT_FLAG} holders:")
    for position, holder in enumerate(RECOVERY_SPLIT.holders, 1):
        rota = "on call" if holder.on_call else "outside the on-call rotation"
        flag = "   <- nobody named yet" if holder.is_placeholder else ""
        print(f"  {position}. {holder.name} ({holder.holder_id}, {rota}){flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
