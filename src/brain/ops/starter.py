"""What a new install is furnished with, and why none of it is anybody's data.

A client who has just run the installer opens a system with no roles, no permission sets, no
agents and no defaults. Everything works and nothing is set up, so the first hour is spent
inventing decisions this product has already made: which six roles exist, what a maintenance
engineer needs to do their job, which agents are worth having, how long a session lasts.

**A furnished system and a demonstration are different deliveries, and M41.2.8 exists because
they get conflated.** `brain.demo` seeds Northwind Facilities: four departments, invented
people, invented clients, invented records. A client wants the roles and does not want the
fictitious records, and the day somebody loads both because they arrived together is the day
Northwind's contract values sit in a real company's database looking exactly like their own.

So the two are separate modules with separate entry points, and `starter_gaps` refuses any
overlap between them. That refusal is structural rather than a convention: the demo prefixes
every row it creates, and nothing here may carry that prefix.

**Nothing here is client-specific and nothing here is a person.** The starter set is roles,
capability packs, agent templates and defaults, which are all facts about the product. It
creates no principal, because a principal is somebody real and the only account an install
may create is the first administrator, through `brain.firstrun`, from a value the installer
supplies. A starter set that shipped an account would ship one nobody created.

**Rejected: loading the starter set inside the migrations.** It is tempting, because it would
mean an install could not forget it. But a migration that inserts rows makes the schema and
its contents one thing, so a client who deletes an agent they do not want finds it back after
the next upgrade, and there is no honest way to tell that apart from a repair. The starter set
is applied once, at install, and after that it is the client's to change.

Task ids: M41.2.7, M41.2.8
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from brain.agents.catalogue import CATALOGUE
from brain.demo import DEMO_PREFIX
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.packs import CapabilityPack
from brain.identity.roles import Role

#: Why the roles are a compiled constant rather than rows an install writes.
THE_SIX_ROLES_ARE_THE_PRODUCT_AND_NOT_A_CLIENTS_CHOICE: Final = (
    "Every permission decision in this system is written against these six. A client who "
    "could add a seventh would have a role nothing resolves, and one who could delete "
    "`super_admin` would have an install nobody can administer. They are furnished as a fact "
    "about the product, which is why this module lists them and does not create them."
)

#: Why a furnished system and a demonstration are separate deliveries.
A_CLIENT_WANTS_THE_ROLES_AND_NOT_THE_FICTITIOUS_RECORDS: Final = (
    "Loading the demo alongside the starter set puts Northwind Facilities' invented clients "
    "and contract values into a real company's database, where they look exactly like the "
    "company's own. Separate entry points are not enough on their own, because the two "
    "arrive together in the same repository, so `starter_gaps` refuses any row here that "
    "carries the demo's prefix."
)

#: Why this creates no account.
A_STARTER_SET_THAT_SHIPS_AN_ACCOUNT_SHIPS_ONE_NOBODY_CREATED: Final = (
    "A principal is somebody real. The only account an install may create is the first "
    "administrator, and `brain.firstrun` creates it from a value the installer supplies so "
    "that no credential exists in this repository. Anything else furnished with an account "
    "is an account with no owner and no audit trail explaining where it came from."
)

#: Why the starter set is applied once rather than by a migration.
A_MIGRATION_THAT_INSERTS_ROWS_TAKES_THEM_BACK_ON_THE_NEXT_UPGRADE: Final = (
    "Putting the starter set in a migration would mean an install could not forget it, and "
    "would also mean a client who deletes an agent they do not want finds it back after the "
    "next upgrade, with no honest way to tell that apart from a repair. It is applied once, "
    "at install, and after that it is theirs."
)


@dataclass(frozen=True)
class Default:
    """One setting a new install starts with, and the sentence that says why.

    `meaning` is required for the same reason `brain.install.Setting` requires one: this is
    what an administrator reads when they wonder whether to change it, and a default nobody
    can explain is one that gets changed to whatever the first incident suggests.
    """

    name: str
    value: str
    meaning: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            msg = f"{self.name} has an empty default, which is an unset setting wearing a value"
            raise ValueError(msg)
        if not self.meaning.strip():
            msg = f"{self.name} has no meaning written down"
            raise ValueError(msg)


#: The permission sets a new install starts with.
#:
#: `STARTER_PACK` is reused rather than restated. It is the joiner's pack, the one
#: `brain.identity.lifecycle` assigns to somebody on their first day, and an install that
#: furnished a second bundle meaning the same thing would have two that drift.
PACKS: Final[tuple[CapabilityPack, ...]] = (STARTER_PACK,)

#: What a new install starts with switched on.
#:
#: Values rather than behaviour: each one is a figure somebody would otherwise pick on their
#: first day with no information, and each is the figure this product's own modules already
#: argue for, so a client who changes one is disagreeing with a written argument rather than
#: guessing against a blank.
DEFAULTS: Final[tuple[Default, ...]] = (
    Default(
        name="session_idle_minutes",
        value="30",
        meaning=(
            "How long a console session may sit untouched before it is closed. Decided as "
            "item 19 and argued there against the absolute ten-hour limit beside it."
        ),
    ),
    Default(
        name="session_absolute_hours",
        value="10",
        meaning=(
            "The longest a session may live however active it is, so a stolen token expires "
            "on its own rather than on somebody noticing."
        ),
    ),
    Default(
        name="approval_required_above",
        value="0",
        meaning=(
            "Zero means every action carrying a side effect is approved by a person until "
            "somebody raises it. A new install trusting itself is the wrong default: nobody "
            "has watched it work yet."
        ),
    ),
    Default(
        name="knowledge_visibility",
        value="department",
        meaning=(
            "New knowledge is visible to the uploader's department and no wider. Widening is "
            "a decision somebody makes about a document; narrowing afterwards is a decision "
            "made too late."
        ),
    ),
)


def roles() -> tuple[Role, ...]:
    """The six, in a fixed order. See `THE_SIX_ROLES_ARE_THE_PRODUCT_AND_NOT_A_CLIENTS_CHOICE`.

    Read off the enum rather than listed here, so this cannot disagree with the type every
    permission decision is written against. A seventh role added to `Role` appears here, and
    the test that pins the count is what makes that a decision rather than an accident.
    """
    return tuple(Role)


def agents() -> tuple[str, ...]:
    """The template ids a new install is furnished with.

    Every manifest in the catalogue, by id, because the catalogue is already the list of
    templates this product ships and a second list would be one that drifts. Ids rather than
    manifests: what an install writes is a row naming a template, and handing the manifests
    around here would invite somebody to modify one on the way in.
    """
    return tuple(sorted(manifest.identity.template_id for manifest in CATALOGUE))


def starter_gaps(
    templates: Sequence[str] | None = None,
    packs: Sequence[CapabilityPack] = PACKS,
    defaults: Sequence[Default] = DEFAULTS,
) -> tuple[str, ...]:
    """Everything about the starter set that would make it the wrong delivery.

    Four checks. The first is M41.2.8 and the rest are the ways a furnished system stops
    being a fact about the product.

    **Takes its inputs rather than reading the module, and a mutation is why.** The first
    version read the constants directly, so on today's data it had nothing to report, and
    switching off either refusal changed nothing observable: both mutations survived, not
    because the checks were wrong but because no test could hand them a bad case. A
    diagnostic that can only be run against the real tree cannot be tested for its refusals,
    which is the same argument `brain.ops.connections.undeclared_clients` and
    `brain.ops.handover.handover_gaps` both make about their own parameters.

    The defaults are the real values, so calling it with no arguments is the deployment check
    and calling it with a constructed set is the test.
    """
    findings: list[str] = []
    templates = agents() if templates is None else templates

    for template in templates:
        if template.startswith(DEMO_PREFIX):
            findings.append(
                f"the starter set would load {template!r}, which carries the demo's prefix. "
                f"{A_CLIENT_WANTS_THE_ROLES_AND_NOT_THE_FICTITIOUS_RECORDS}"
            )
    for pack in packs:
        if pack.slug.startswith(DEMO_PREFIX):
            findings.append(f"pack {pack.slug!r} carries the demo's prefix")
        if not pack.capabilities:
            findings.append(f"pack {pack.slug!r} grants nothing, so assigning it does nothing")

    if not roles():
        findings.append(
            "the starter set furnishes no roles, so a new install has no permission model"
        )
    if not templates:
        findings.append("the starter set furnishes no agents, so a new install opens blank")

    names = [one.name for one in defaults]
    repeated = sorted({one for one in names if names.count(one) > 1})
    if repeated:
        findings.append(f"{repeated} is defaulted twice, so which value applies is arbitrary")

    return tuple(findings)
