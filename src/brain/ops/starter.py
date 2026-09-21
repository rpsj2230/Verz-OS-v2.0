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

**Rejected: applying it from `brain.seed`, and the reason is measurable rather than
stylistic.** It is the obvious host - it is the one command that writes rows, it already runs
at install time, and `make seed` is already in the Makefile. It is the wrong one twice over.
The first reason is the one M41.2.8 is about: a client who wanted the roles would have to load
Northwind Facilities to get them, which is the conflation this whole module exists to refuse.
The second is structural and was measured on 2026-09-11 against a real PostgreSQL. `brain.seed`
refuses any database holding rows it does not own, and a real install holds rows before the
starter set is wanted: the first administrator is created by a person at first run, and that
row alone is enough for the seed to refuse. **The two deliveries have opposite preconditions.**
The demonstration wants a database with nothing in it; the furnished system wants the database
a client is actually about to use. One command cannot be right for both, and the one that tried
would be wrong for whichever it was not written for. See
`A_FURNISHED_SYSTEM_AND_A_DEMONSTRATION_HAVE_OPPOSITE_PRECONDITIONS`.

**So it belongs on the install plan, and the plan already has the concept it needs.**
`brain.deployment.installer.PLAN` is the sequence that runs once on a client's server, and
`brain.deployment.installer.Step` requires `already_done` of any step that writes: a shell
test that is true when the step has nothing left to do. That is
`A_MIGRATION_THAT_INSERTS_ROWS_TAKES_THEM_BACK_ON_THE_NEXT_UPGRADE`'s "once, at install"
expressed as a first-class property rather than as a convention, and it is the difference
between a starter set a client can delete from and one that grows back.

**Until 2026-09-17 nothing applied the starter set, and this paragraph said so.** A fresh install
held no scope, no pack and no registered capability, so the grant route, which resolves a scope
by name, refused every grant anybody tried to write, a first administrator's included.
`brain.ops.starter_store` is the applying half now, and it is called at every start of the
application, by the installer's `furnish the install` step, and by `python -m
brain.ops.starter_store`. This module stays the declaration and never opens a connection.

**Three things are declared here for it to write, and each is the product's rather than a
company's.** `SCOPES` is one scope that restricts nothing, named for what it is, because a grant
needs a named scope and a department's name is a company's own; see
`A_GRANT_NEEDS_A_NAMED_SCOPE_AND_A_FRESH_INSTALL_HAD_NONE`. `PACKS` is the joiner's pack.
`vocabulary` is every capability the product declares, each with the sentence its declaring
module already wrote, read from those modules rather than listed a second time; see
`THE_VOCABULARY_IS_READ_FROM_WHERE_EACH_CAPABILITY_IS_DECLARED`.

Task ids: M41.2.7, M41.2.8
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.agents.catalogue import CATALOGUE
from brain.audit.ledger import SUBJECT_KINDS
from brain.audit.view import AUDIT_NOUN
from brain.console.reads import Plane, member_plane_capability, plane_capability
from brain.console.screens import SCREENS
from brain.core.department import ScopeRecord
from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.demo import DEMO_PREFIX
from brain.identity.first_administrator import GRANTED_AT_APPOINTMENT
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.packs import CapabilityPack
from brain.identity.roles import Role
from brain.member.shell import MEMBER_SCREENS

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

#: Why the seed command is not where the starter set is applied.
A_FURNISHED_SYSTEM_AND_A_DEMONSTRATION_HAVE_OPPOSITE_PRECONDITIONS: Final = (
    "`brain.seed` refuses a database holding rows it does not own, because a demonstration "
    "belongs in an empty one. The starter set belongs in the database a client is about to "
    "use, which holds the first administrator before anything else is furnished, so a seed "
    "that also applied it would refuse exactly when it was needed. That is the second reason "
    "and the first is M41.2.8: a client who wanted the six roles would have to load Northwind "
    "Facilities to get them. The applying half belongs on the install plan, where "
    "`brain.deployment.installer.Step` already requires a step that writes to say when it has "
    "nothing left to do."
)

#: The module whose install plan the starter set belongs on, and the field that makes it
#: applicable once. Named rather than described, so a test can fail when either goes away
#: instead of a paragraph quietly naming somewhere that no longer exists.
APPLIED_BY = ("brain.deployment.installer", "already_done")

#: Why the starter set is applied once rather than by a migration.
A_MIGRATION_THAT_INSERTS_ROWS_TAKES_THEM_BACK_ON_THE_NEXT_UPGRADE: Final = (
    "Putting the starter set in a migration would mean an install could not forget it, and "
    "would also mean a client who deletes an agent they do not want finds it back after the "
    "next upgrade, with no honest way to tell that apart from a repair. It is applied once, "
    "at install, and after that it is theirs."
)

#: Why a furnished install holds exactly one scope, and why it is not a department.
A_GRANT_NEEDS_A_NAMED_SCOPE_AND_A_FRESH_INSTALL_HAD_NONE: Final = (
    "brain.govern_routes.grant resolves the scope a grant is written over by its slug against "
    "gate.scope, and answers a slug nothing matches with the same refusal as a slug out of "
    "reach. On an install holding no scope row that refusal was every answer, so nobody could "
    "grant anything over anything, a first administrator holding approve:grant everywhere "
    "included. One scope that restricts nothing is the product's: it is the unrestricted "
    "predicate given the name the Scopes screen shows. A department is not furnished, because "
    "its name is a company's own and is written when somebody creates it."
)

#: Why the registry's vocabulary is read out of other modules rather than listed here.
THE_VOCABULARY_IS_READ_FROM_WHERE_EACH_CAPABILITY_IS_DECLARED: Final = (
    "Every capability this product checks is already declared somewhere a test holds: the "
    "console and member screens with a sentence each, the planes, the audit kinds, the grants "
    "first run makes, and the packs. A list of them here would be a second copy, and "
    "brain.identity.first_administrator.ADMINISTRATION is already held equal to a scan of the "
    "source, so it would be the third. Each capability is described by the sentence its "
    "declaring module wrote, and one no module describes is described from its grammar, which "
    "says what the gate checks and nothing it does not."
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


#: The one scope a new install is furnished with. See
#: `A_GRANT_NEEDS_A_NAMED_SCOPE_AND_A_FRESH_INSTALL_HAD_NONE`.
COMPANY_SCOPE: Final = ScopeRecord(
    slug="company",
    scope=Scope.unrestricted(),
    is_department=False,
    label="The whole company",
)

#: The scopes a new install starts with, which is that one.
SCOPES: Final[tuple[ScopeRecord, ...]] = (COMPANY_SCOPE,)


@dataclass(frozen=True)
class Declared:
    """One capability the product declares, and the words its registry row carries.

    `description` is required for the reason `gate.capability_registry` requires one: an
    undescribed permission is one nobody can review, and the review is what the registry is for.
    """

    capability: Capability
    description: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            msg = f"{self.capability.value} is declared with no description"
            raise ValueError(msg)


#: What a reader sees of a thing at each plane, in words. Keyed by the enum and held equal to it
#: by a test, so a fourth plane cannot arrive with nothing to say what it shows.
PLANE_MEANING: Final[Mapping[Plane, str]] = MappingProxyType(
    {
        Plane.EXISTENCE: (
            "that a thing is there: a name in a list, and nothing of how it is set up or what is "
            "inside it."
        ),
        Plane.CONFIGURATION: (
            "how a thing is set up: a leash, a schedule, a ceiling or a binding, and not what is "
            "inside it."
        ),
        Plane.CONTENT: "what is inside a thing: the records, documents and answers themselves.",
    }
)

#: How each verb reads at the start of a description built from a capability's grammar. Held
#: equal to `brain.core.entitlement.VERBS` by a test.
VERB_WORDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "read": "Reads",
        "write": "Changes",
        "invoke": "Runs",
        "approve": "Approves",
        "admin": "Administers",
    }
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


def _words(name: str) -> str:
    return name.replace("_", " ")


def described_by_grammar(capability: Capability) -> str:
    """What a capability no module describes says, read off `verb:noun[.field]` and no further.

    The floor rather than the aim: it says what the gate checks, which is true of every
    capability, and nothing about what the holder may do with it, which only the module that
    checks it could say. See `THE_VOCABULARY_IS_READ_FROM_WHERE_EACH_CAPABILITY_IS_DECLARED`.
    """
    noun, _, field = capability.value.partition(":")[2].partition(".")
    verb = VERB_WORDS[capability.verb]
    if field:
        return f"{verb} the {_words(field)} field of {_words(noun)}."
    return f"{verb} {_words(noun)}."


def declared_sentences() -> tuple[tuple[Capability, str], ...]:
    """Every capability a module declares together with a sentence of its own, in that order.

    The console's screens and the member surface's, each by its title and purpose; the planes of
    both surfaces, by what each plane shows; and one audit read per subject kind the ledger
    records, by what it reads.
    """
    said: list[tuple[Capability, str]] = [
        (one.read.requires, f"The {one.title} screen: {one.purpose}") for one in SCREENS
    ]
    said.extend(
        (member.read.requires, f"The {member.title} screen: {member.purpose}")
        for member in MEMBER_SCREENS
    )
    for plane in Plane:
        said.append((plane_capability(plane), f"Shows in the console {PLANE_MEANING[plane]}"))
        said.append(
            (
                member_plane_capability(plane),
                f"Shows in a person's own workspace {PLANE_MEANING[plane]}",
            )
        )
    said.extend(
        (
            Capability(value=f"read:{AUDIT_NOUN}.{kind}"),
            f"Reads the audit entries about {_words(kind)} subjects.",
        )
        for kind in sorted(SUBJECT_KINDS)
    )
    said.extend(checked_elsewhere())
    return tuple(said)


def checked_elsewhere() -> tuple[tuple[Capability, str], ...]:
    """The capabilities code checks that no screen, plane or audit kind declares (M1.7.1).

    Each is the declaring module's own constant, imported where it is used, so a renamed value
    moves here with it. Until these were listed, each was required by a served path and absent
    from the registry an install is furnished with, so the Capabilities screen never named it.
    Imported inside the function because several of these modules sit above this one.
    """
    from brain.agents.lifecycle import AGENT_PUBLICATION_CAPABILITY
    from brain.audit.reads import READ_LOG_CAPABILITY
    from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
    from brain.core.redaction import OPAQUE_CAPABILITY
    from brain.gate.model_lane import PASSAGE_POLICY
    from brain.knowledge.verification import VERIFIER_CAPABILITY
    from brain.knowledge.visibility import PROMOTION_CAPABILITY
    from brain.ops.feedback import FLAG_CAPABILITY
    from brain.ops.jobs import DEAD_LETTER_CAPABILITY
    from brain.tools.run_skill import SCRIPT_CAPABILITY

    # Described by grammar, as the starter pack's own copies of the same reads already are.
    passage_fields = tuple(
        (rule.required_capability, described_by_grammar(rule.required_capability))
        for rule in PASSAGE_POLICY.rules
    )
    return (
        *passage_fields,
        (AGENT_PUBLICATION_CAPABILITY, "Approves publishing an agent to a wider audience."),
        (PROMOTION_CAPABILITY, "Approves promoting a knowledge item to a wider audience."),
        (SCRIPT_CAPABILITY, "Runs an approved skill's script in its sandbox."),
        (READ_LOG_CAPABILITY, "Reads other people's entries in the audit read log."),
        (BROWSE_SURFACE, "Reads a declared browser surface."),
        (ACT_ON_SURFACE_CAPABILITY, "Acts on a declared browser surface."),
        (DEAD_LETTER_CAPABILITY, "Reads somebody else's dead-lettered jobs."),
        (VERIFIER_CAPABILITY, "Shows who verified a knowledge item on its badge."),
        (OPAQUE_CAPABILITY, "Reads what an opaque tool returns, which no field policy classifies."),
        (FLAG_CAPABILITY, "Flags an answer as wrong."),
    )


def vocabulary(
    described: Iterable[tuple[Capability, str]] | None = None,
    granted: Iterable[str] = GRANTED_AT_APPOINTMENT,
    packs: Sequence[CapabilityPack] = PACKS,
) -> tuple[Declared, ...]:
    """Every capability the product declares, once each, in capability order, with its words.

    `described` defaults to `declared_sentences`. A capability first run grants or a furnished
    pack holds that nothing there describes is described by `described_by_grammar`; one that is
    described keeps its own sentence alone, so a screen's read never carries its grammar beside
    its purpose. A capability declared twice with two sentences carries both, in the order given.

    Takes its inputs for the reason `starter_gaps` does: a vocabulary that could only be built
    from the real tree could not be handed a capability declared twice or declared by nothing.
    """
    said: dict[str, list[str]] = {}
    for capability, sentence in declared_sentences() if described is None else described:
        sentences = said.setdefault(capability.value, [])
        if sentence not in sentences:
            sentences.append(sentence)
    for value in (*granted, *(one.value for pack in packs for one in pack.capabilities)):
        if value not in said:
            said[value] = [described_by_grammar(Capability(value=value))]
    return tuple(
        Declared(capability=Capability(value=value), description=" ".join(said[value]))
        for value in sorted(said)
    )


def starter_gaps(
    templates: Sequence[str] | None = None,
    packs: Sequence[CapabilityPack] = PACKS,
    defaults: Sequence[Default] = DEFAULTS,
    scopes: Sequence[ScopeRecord] = SCOPES,
) -> tuple[str, ...]:
    """Everything about the starter set that would make it the wrong delivery.

    Five checks. The first is M41.2.8 and the rest are the ways a furnished system stops
    being a fact about the product. The fifth arrived with the furnished scope: a scope the
    product writes may restrict nothing, because any clause it carried would name a department,
    a person or a record of some company, and no install's parts are the product's to name.

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
    for record in scopes:
        if record.slug.startswith(DEMO_PREFIX):
            findings.append(f"scope {record.slug!r} carries the demo's prefix")
        if not record.scope.is_unrestricted():
            findings.append(
                f"scope {record.slug!r} restricts something, so the product would be naming a "
                "part of a company it has never met"
            )

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
