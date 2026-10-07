"""The one place a `ToolRegistry` is built, and the reason it did not exist until now.

`brain.tools.registry` refuses a tool with a name that breaks the grammar, a service tool
that is unscoped, a handler whose result the redactor cannot read, and two tools with the
same description. `ToolRegistry.freeze` says in its own docstring that it is "called at
startup". None of that ran anywhere, because until this module no code outside the tests
ever constructed a registry: `RowTool` existed, its `definition` and `reader` existed, and
nothing put the two together.

**That is the failure this repository keeps finding rather than a missing feature.** The
deploy that reported success and deployed nothing, the RLS sweep that had never run, the
document of record carrying a stale count: each was a mechanism that was correct, tested,
and never called. A registry that no process builds is a set of rules that has never
refused anything, and the first tool to break one of them would break it in production
against a registry assembled by whoever needed one that afternoon.

**So there is exactly one builder and the application calls it.** Not a helper the routes
may call if they need tools, and not a module-level singleton: `build_registry` returns a
frozen registry, `brain.app` puts it on `app.state` during startup, and a second registry
built later would have to be built deliberately by somebody who could see they were doing
it. The singleton is rejected for the reason the registry's own docstring rejects one, that
one test's registration would be visible to the next.

**Freezing at startup is the point, not tidiness.** `freeze` runs the checks that can only
be made once every tool is present, and it raises. A process that comes up with a broken
catalogue is a process answering questions from a tool set nobody validated, and the
alternative to raising is a warning at boot, which is a warning nobody reads after the
first week.

**Every install registers one built-in row tool, and that is honest rather than embarrassing.**
`knowledge.columns.PRICE_LIST` is the only classification the product ships for everybody,
so the price list is the only entity every install has a row tool for. The value here is not
the count; it is that the count is produced by a builder that runs every rule, so the next
tool is registered through a door rather than beside one.

**And two document tools, since 2026-09-14, for the same reason the price list is built in.**
The document plane is the product's own rather than a source's, so
`brain.knowledge.document_tools` registers `knowledge.search_documents` and
`knowledge.read_document` on every install, through the same door as the row tools because they
read through the same row source. Before they existed no template naming `knowledge.read` or
`knowledge.search` had anything to bind to, and the gate refused every one of them. See
`THE_DOCUMENT_PLANE_IS_REGISTERED_WHEREVER_ROWS_ARE`, and that module's docstring for the limit
of reading chunks through a row source, which fails closed.

**A source may bring the classifications of its own entities, and they are registered only
where that source is read.** The demo is the first. Until 2026-09-14 nothing classified its
clients, jobs and invoices, so the console answered nobody's question about the seeded
company, which `tests/e2e/test_wave_one_console_question.py` measured. The classifications
now live in `brain.demo`, written from the columns its records store, and
`SOURCE_ROW_ENTITIES` files them under `brain.demo.DEMO_SOURCE`: an install configured with
`BRAIN_TOOL_SOURCE=demo` registers them beside the built-ins, and an install reading any other
system registers none of them. See
`A_SOURCES_OWN_ENTITIES_ARE_REGISTERED_ONLY_WHERE_THAT_SOURCE_IS_READ`.

Three other shapes were considered and rejected.

- **Widening `BUILT_IN_ROW_ENTITIES`**, which is one line. The demo's `client` would then be
  every install's: `contract_value`, `account_manager` and `since` classified by the product,
  governing whatever a client's own system calls a client. That is one company's schema in the
  template, and the company being invented does not make it anybody else's.
- **Registering the demo's entities under its own source on every install with a database.**
  The seeded rows would answer with nothing configured, and every real install would carry
  three tools that read nothing, answer `/records/client` for anybody holding a client grant
  with an empty page where it used to say the entity is not here, and name the demo's source
  in the scope statement of their answers.
- **Deciding at startup, from the database, whether the demo is loaded.** It needs no setting,
  and it makes what the application serves depend on which rows exist, so a stray row
  registers a tool; `brain.gate.fast_lane` refuses that shape for rules, for the same reason.
  It would also need a read before the registry is built, which is `brain.app`'s ordering to
  change rather than this module's.

**`classification_for` takes the source, and the answer lane gives it one (M15.4.2).** Until
2026-09-28 it was keyed on the entity alone, which was sound only while no two owners classified
one entity: the day a second source classified `contact`, the answer lane would have redacted the
first source's contacts by the second's rules, withholding every field only the first classified,
so connecting a second source stopped the first answering. With `source=` it answers that source's
own classification or a built-in, and `brain.api_routes.source_field_policies` hands the lane one
policy per source and entity. Without `source=` it answers as before, the first owner's, for the
callers that name only an entity (`/records/{entity}`, `/classifications/{entity}`), which is a
limit still standing for those screens and is why `test_every_entity_is_classified_by_one_owner`
now holds each source to one classification per entity rather than the product to one per entity.

**A shipped connector's classifications are registered on every install, beside the tool source's.**
A connector's entities are filed in `SOURCE_ROW_ENTITIES` under its name, and `build_registry`
registers them under that name whatever `BRAIN_TOOL_SOURCE` says, because a connector is connected
from the console at run time and the registry is built once, at start. The demo is filed there too
and is not a connector, so it is still registered only where the demo is read. They are not read off
the connector's own declaration, because `brain.connectors.declaration` is on the scheduled sync's
path and imports nothing from `brain.knowledge`, which `tests/invariants/test_minimal_index.py`
holds.

**A connector's write a model may ask for is registered beside the row tool that reads its
record (M13.7.6).** `brain.tools.proposed_writes` registers each write a connector declares a
preparer for, with a handler that refuses every call, so an agent's catalogue can offer it and a
run can hold its call for a person; the only way it is sent is the approved action the worker
carries out. Without a row source none is registered, for the reason no row tool is.

**The row source is injected and there is no default.** `RowTool.reader` binds to a
`RowSource`, and a builder that supplied its own would be a second path to data with its
own idea of what may be seen, which is exactly what `channels.adapter.ChannelAdapter`
refuses by having no `query` method. A caller with no source registers no row tools rather
than registering tools that read from nowhere, because a tool that is present and cannot
answer is worse than one that is absent: the catalogue offers it, the model picks it, and
the person is told the system has no data on a subject it has plenty of.

**So the application registers no row tools today, and the reason is a real mismatch rather
than an oversight.** `RowSource.rows` is synchronous and `brain.session` builds an
`AsyncEngine`, so nothing can implement the protocol against the pool the application
already has. There are exactly three ways out and none is a small edit:

- Make the row plane async, which changes `RowSource`, `read_rows` and every caller.
- Run the sync reader in a worker thread the way `lifespan` already runs migrations, which
  works and needs a second, synchronous engine.
- Give the application a sync engine beside the async one.

The last two both add a connection pool, and `docker-compose.yml` sizes PgBouncer at
`DEFAULT_POOL_SIZE=20` against `max_connections=100`. Picking one at the same time as wiring
the registry would be changing the deployed resource profile inside a commit about something
else, so the sizing was left for its own measurement. `build_registry` takes the source as a
parameter precisely so that whichever is chosen is one call site.

**That measurement has now been taken, and it says the pool is not what should decide this.**
On the live database, 2026-09-07: `max_connections` is 100 and `pg_stat_activity` showed 9
connections in use. Ninety-one are spare, so a second pool of five or ten is comfortably
affordable and the resource objection to the last two options does not hold.

What that leaves is the engineering question on its own, and the answer is the first option.
The application is async from the socket to the session; the row plane is the only synchronous
island in it. Keeping that island means a second connection pool *and* a thread per concurrent
row query, both of them permanent, to avoid changing five call sites: `RowSource`, `read_rows`,
`RowTool.reader`, `fast_lane.respond` and this builder. A second pool added to preserve a sync
island is the kind of decision that looks cheap on the day and is never removed.

It is not done here for a reason that is about sequencing rather than doubt. `read_rows` is
where the permission predicate is compiled, so it is the single module in this system where a
mistake is a disclosure, and it deserves a change of its own with its own mutation pass rather
than one folded into a measurement. Whoever takes it should know the resource question is
settled and the refactor is five call sites.

What this module does fix is the thing that was actually broken: a registry now exists, one
builder makes it, the application calls that builder at startup, and every rule runs on the
way in. Registering the first real tool is a `records=` argument, not an afternoon.

Task ids: M12.1.5, M15.4.2, M12.4.4, M11.7.8, M13.7.6
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from brain import demo
from brain.chat.attachments import attachment_definition, attachment_reader
from brain.core.field_policy import FieldPolicy
from brain.gate.caches import CachedEmbedding
from brain.knowledge.columns import PRICE_LIST, TableClassification
from brain.knowledge.connector_figures import LiveFigures, figure_tools
from brain.knowledge.connector_rows import CONNECTOR_ROW_DESCRIPTIONS, CONNECTOR_ROW_ENTITIES
from brain.knowledge.document_tools import (
    KNOWLEDGE_PIN,
    KnowledgeCaches,
    QuestionEmbedder,
    RecordStore,
    knowledge_tools,
)
from brain.knowledge.embed_policy import embedding_revision
from brain.knowledge.rows import RowSource, RowTool
from brain.ops.connector_catalogue import Derived, declarations
from brain.tools.proposed_writes import register_proposed_writes
from brain.tools.registry import ResultContract, ToolRegistry
from brain.tools.skill_tools import SkillTools, register_skill_tools
from brain.tools.website_check import WebsiteCheckTool, register_website_check

#: Why the document plane is registered on every install that has rows, whatever it reads.
THE_DOCUMENT_PLANE_IS_REGISTERED_WHEREVER_ROWS_ARE: Final = (
    "The document plane is the product's own and not a system an install is pointed at, so its "
    "tools are not per source: the argument that makes the price list a built-in makes "
    "knowledge one too. It reads through the same row source the row tools do, because that is "
    "the only database handle this builder is given, so it is registered exactly when they are "
    "and never beside a source that cannot answer. Ten catalogue templates name knowledge.read "
    "or knowledge.search, and with no tool to bind them every one of them was an agent the gate "
    "refused to start."
)

#: Why an entity a source brings is registered for that source and for no other.
A_SOURCES_OWN_ENTITIES_ARE_REGISTERED_ONLY_WHERE_THAT_SOURCE_IS_READ: Final = (
    "An entity a source brings is classified by that source's columns, and those columns are "
    "a fact about one system rather than about the product. Registered on every install, they "
    "would govern another system's records of the same name and put tools that read nothing "
    "into installs that never asked for them. Registered where the source is read, they exist "
    "exactly where their rows can, and which source an install reads is configuration a person "
    "sets, BRAIN_TOOL_SOURCE, like any other system it is pointed at."
)

#: The description each built-in row tool carries into the catalogue.
#:
#: Written here rather than at the construction site because `ToolRegistry.validate` refuses
#: two tools that share one, folded and stripped of punctuation, and the refusal is a
#: property of a pair. Keeping the descriptions in one mapping means the collision is visible
#: while it is being written rather than at the freeze that follows.
ROW_TOOL_DESCRIPTIONS: Final[dict[str, str]] = {
    "price_list": (
        "Read rows from the price list: SKU, product name, sell price, and the cost and "
        "margin columns for callers entitled to them"
    ),
}

#: Every entity the application ships a row tool for on every install, with the
#: classification that governs it. One entry today. A second is one line here and no change
#: anywhere else, which is the shape a registry is supposed to have. An entity only one
#: system carries does not belong here: see `SOURCE_ROW_ENTITIES`.
BUILT_IN_ROW_ENTITIES: Final = (PRICE_LIST,)

#: The entities a source brings for itself, by the source's name, each with the classification
#: governing it. Registered only by an install that reads that source. See
#: `A_SOURCES_OWN_ENTITIES_ARE_REGISTERED_ONLY_WHERE_THAT_SOURCE_IS_READ`.
#:
#: Read-only, because a registration added at run time would be visible to every registry
#: built afterwards in the same process, which is the singleton the module docstring rejects
#: arriving through a dictionary.
SOURCE_ROW_ENTITIES: Final[Mapping[str, tuple[TableClassification, ...]]] = Derived(
    lambda _: {demo.DEMO_SOURCE: demo.row_classifications(), **CONNECTOR_ROW_ENTITIES}
)

#: The catalogue descriptions for those entities, by source and then entity. Beside the
#: classifications rather than inside them for the reason `ROW_TOOL_DESCRIPTIONS` gives: a
#: description is catalogue text whose collisions are a property of the whole registry.
SOURCE_ROW_DESCRIPTIONS: Final[Mapping[str, Mapping[str, str]]] = Derived(
    lambda _: {demo.DEMO_SOURCE: demo.ROW_TOOL_DESCRIPTIONS, **CONNECTOR_ROW_DESCRIPTIONS}
)


def source_row_entities() -> Mapping[str, tuple[TableClassification, ...]]:
    """Every source's own classifications, by source, read at call time."""
    return SOURCE_ROW_ENTITIES


def connector_row_sources() -> tuple[str, ...]:
    """Every connector with classifications filed here, which `build_registry` registers.

    The connectors and no other source, so the demo's entities stay where the demo is read: see
    `A_SOURCES_OWN_ENTITIES_ARE_REGISTERED_ONLY_WHERE_THAT_SOURCE_IS_READ`. The connectors are
    `brain.ops.connector_catalogue.declarations`, so one reviewed on this install (M11.7.8) has
    its row tools in the next registry built.
    """
    found = declarations()
    return tuple(sorted(name for name in source_row_entities() if name in found))


def row_entities_for(source: str) -> tuple[TableClassification, ...]:
    """Every entity an install reading `source` has a row tool for: the built-ins, then its own.

    The one place the source decides what is registered. `build_registry` reads nothing else,
    so an entity cannot be registered for a source that does not bring it by any route other
    than editing `SOURCE_ROW_ENTITIES`, which is a decision somebody can see being made.
    """
    return (*BUILT_IN_ROW_ENTITIES, *source_row_entities().get(source, ()))


def every_row_classification() -> tuple[TableClassification, ...]:
    """Every classification the product knows, whichever install it is registered on.

    What `classification_for` searches when it is given no source. Exposed so a test can hold
    each source to one classification per entity.
    """
    return (
        *BUILT_IN_ROW_ENTITIES,
        *(one for owned in source_row_entities().values() for one in owned),
    )


def classification_for(entity: str, *, source: str | None = None) -> TableClassification | None:
    """The column classification governing this entity, or None if nothing classifies it.

    Here rather than in whatever needs it, because the lists above are the one place that
    decides which entities this application classifies, and a second index built from them
    elsewhere is a second answer to the same question the first time somebody adds an entity
    to only one of them.

    None rather than a refusal, and the caller decides what an unclassified entity means. For
    `brain.api_routes` it means the same 404 an ungranted entity gets, which is the record
    rule applied one level up: a caller who could tell "there is no such entity here" from
    "you may not reach it" could map the installation by asking.

    With `source`, that source's own classification or a built-in, and nothing another source
    brought (M15.4.2). Without it, the first owner's, which is a limit: see the module docstring.
    """
    known = every_row_classification() if source is None else row_entities_for(source)
    return next((c for c in known if c.entity == entity), None)


def field_policy_for(entity: str, *, source: str | None) -> FieldPolicy:
    """The field policy an action on `entity` is decided under, for the leash's mask check.

    The read classification `classification_for` finds, and the fields `source`'s write grants
    declare their tools write (`brain.connectors.declaration.written_fields`). A grant field that
    contradicts a read rule is a `PolicyConflictError` here rather than either one winning. With
    nothing classifying the entity, the empty policy, which withholds every field.
    """
    from brain.connectors.declaration import written_fields

    found = classification_for(entity, source=source)
    read = () if found is None else found.policy().rules
    written = () if source is None else written_fields(source, entity)
    return FieldPolicy(rules=(*read, *written))


def description_for(source: str, entity: str) -> str:
    """The catalogue text for one row tool an install reading `source` registers.

    Raises `KeyError` for an entity nobody wrote a description for, at startup, which is where
    `build_registry` has always failed for that mistake.
    """
    return {**ROW_TOOL_DESCRIPTIONS, **SOURCE_ROW_DESCRIPTIONS.get(source, {})}[entity]


def question_embedder(
    env: Mapping[str, str] | None = None, *, cache: RecordStore[CachedEmbedding] | None = None
) -> QuestionEmbedder | None:
    """How this process embeds a question, or None when the install has declared no weights.

    None is an install whose knowledge search is text search, which is every install until its
    owner sets `INSTALL_EMBEDDING_REVISION`; see
    `brain.knowledge.embed_policy.AN_UNDECLARED_REVISION_IS_AN_INSTALL_WITH_NO_VECTOR_LEG`.

    **A declared revision with an address that is not one stops the start**, through
    `make_client`'s refusal naming `INSTALL_MODEL_ENDPOINT`. The worker builds its client lazily
    and keeps starting, because a worker runs controls that have nothing to do with embedding;
    this process would otherwise answer every knowledge search degraded over a value somebody
    typed, and the sentence saying why would be in no response a person reads. Imported here
    rather than at the top so a process with no declared revision never builds an HTTP client.
    """
    revision = embedding_revision(env)
    if revision is None:
        return None
    from brain.ops.inference_client import make_client

    return QuestionEmbedder(service=make_client(env=env), revision=revision, cache=cache)


def build_registry(
    *,
    source: str,
    records: RowSource | None = None,
    sources: Iterable[str] | None = None,
    figures: LiveFigures | None = None,
    website: WebsiteCheckTool | None = None,
    caches: KnowledgeCaches | None = None,
    skills: SkillTools | None = None,
) -> ToolRegistry:
    """Every tool this application offers, checked and frozen (M12.1.5).

    `source` names the system the rows came from and is required. `RowTool` refuses an empty
    one already, with the argument that two sources' record ids collide by coincidence of
    integers; passing it through rather than defaulting keeps that refusal reachable instead
    of satisfying it with a placeholder nobody chose. It also decides which entities beyond
    the built-ins are registered: see `row_entities_for`.

    `records` may be absent, and then no row tool is registered at all. See the module
    docstring: a tool that is present and cannot answer tells a person the system has no
    data on a subject it has plenty of, which is worse than the tool being missing, because
    a missing tool is a gap somebody notices and an empty answer is a fact somebody believes.

    `sources` are the other sources whose own entities are registered beside `source`'s, each
    under its own name and each classified by its own rules (M15.4.2); None means every shipped
    connector that brings classifications (`connector_row_sources`). The built-ins are registered
    once, under `source`, because the price list is the product's and not any system's.

    `figures` is how a connected source's figures are read live for a range a tool names
    (`brain.knowledge.connector_figures`, M11.7.1). With it and a row source, every shipped source
    declaring a report gets its figure tool beside its row tool; without it none does, for the
    reason a row tool is not registered without a row source.

    `website` is the website check bound to its transport (`brain.ops.website_probe`). Absent,
    the check is not registered, for the reason a row tool is not registered without a row
    source: a tool in the catalogue that cannot reach a site would tell a person it is down.

    `skills` binds the two tools a run reads a skill with (`brain.tools.skill_tools`): the
    instructions of an offered skill, and its scripts where the install runs a sandbox. Absent,
    neither is registered, for the reason the website check is not.

    Returns frozen. A caller receiving an unfrozen registry could register into it after the
    whole-registry checks had run, which is the same as not running them.
    """
    registry = ToolRegistry()
    others = connector_row_sources() if sources is None else tuple(sources)
    owned = source_row_entities()
    pairs = [(source, one) for one in row_entities_for(source)] + [
        (other, one)
        for other in dict.fromkeys(others)
        if other != source
        for one in owned.get(other, ())
    ]

    if records is not None:
        for owner, classification in pairs:
            tool = RowTool(
                source=owner,
                classification=classification,
                description=description_for(owner, classification.entity),
            )
            registry.register(
                tool.definition(),
                tool.reader(records),
                # The reader returns a `TypedResult[RowRecord]`, which is what the redactor
                # reads. Declared rather than inferred, so a handler changed to return a
                # dictionary fails at registration instead of at the first redaction.
                result_contract=ResultContract.TYPED,
                scope=tool.scope,
            )
        # A connected source's figures for a range a tool names, where its reads can be made.
        if figures is not None:
            classified = {name: owned.get(name, ()) for name in dict.fromkeys(others)}
            for figure in figure_tools(classified):
                registry.register(
                    figure.definition(),
                    figure.reader(records, figures),
                    result_contract=ResultContract.TYPED,
                    scope=figure.scope,
                )
        # The document plane, for every source. See
        # `THE_DOCUMENT_PLANE_IS_REGISTERED_WHEREVER_ROWS_ARE`.
        embedder = question_embedder(cache=None if caches is None else caches.embeddings)
        retrievals = None if caches is None else caches.retrievals
        for definition, handler in knowledge_tools(records, embedder, retrievals):
            registry.register(
                definition,
                handler,
                result_contract=ResultContract.TYPED,
                scope=KNOWLEDGE_PIN,
            )
        # A file a person attached to their own conversation, read at their reach (M12.3.6).
        registry.register(
            attachment_definition(),
            attachment_reader(records),
            result_contract=ResultContract.TYPED,
            scope=KNOWLEDGE_PIN,
        )
        # A connector's write a model may ask for, beside the row tool that reads its record. It
        # can never be called: see `brain.tools.proposed_writes`.
        register_proposed_writes(registry, declarations())

    # The website check, where the caller handed it a transport (M12.4.4). Not tied to a row
    # source: it reads a site, not a table.
    if website is not None:
        register_website_check(registry, website)

    # A skill's instructions on request, and its scripts through the one execution tool where
    # there is a sandbox (M12.2.8, M12.2.9). Not tied to a row source either.
    if skills is not None:
        register_skill_tools(registry, skills)

    return registry.freeze()
