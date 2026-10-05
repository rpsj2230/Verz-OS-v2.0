"""The install acceptance checks for building an agent: from scratch, by hand, and on a canvas.

`brain.agent_builder_routes` is the New agent and Edit as a draft flow, and every check here asks
it, as a reserved builder of acceptance_a, through its own route functions, the way the console
does. The template signing key is the check's own, for the reason
`brain.ops.acceptance_checks_templates.THE_WORKER_HOLDS_NO_SIGNING_KEY` gives: the worker is given
none, so what is proved is the route's behaviour over a key it can verify, and everything is
written inside the check's transaction and rolled back.

**A hand-built agent takes the template path (M13.2.7, M13.1.1).** A new draft starts from the
blank template, and the agent its publish makes is a signed template version and an instance
pinned to it, exactly as an installed template is: one code path, which is what the blank
template is for. The agent's row carries what the work breakdown names for it: its persona,
scope, model tier and visibility level, read back from the database.

**Who last set each field is the instance's, path by path (M13.2.4).** The agent's instructions
are changed through the prompts route by a second reserved administrator, and the instance must
then say that person set the persona and nobody set the paths they did not touch.

**An authored list is intent and not authorisation (M20.1.5).** A builder who holds nothing of a
capability names it in a draft that passes its check; publishing it on that builder's word alone
makes no agent and waits for a second person, because the ceiling is derived on the server from
what the publish would reach, and the list is what was asked for.

**The canvas draws five kinds of step and nothing else (M20.2.2, M20.2.3, M20.2.4).** A drawing
over the draft's own tool comes back as a SKILL.md calling it. A step of a kind outside the five,
a code step, and a branch whose condition is not a scope predicate are each refused.

**The form is the manifest's schema, served to a builder only (M20.1.2).** What the route serves is
a JSON Schema whose sections are the manifest's own fields, and a reader who may not build is told
nothing exists. That `react-jsonschema-form` draws it is the console's page test's to prove.

**A template installs in one press, and the long way stays open (M13.9.4); without a key it says
so (M13.8.18).** One press with nothing but the digest it confirmed makes an agent under the
template's own name, and the same template starts a builder draft carrying its words for anybody
who wants to change them. On a process with no signing key the gallery says installing is
unavailable, installing changes nothing, and no setting this product reads can hold a key.

Task ids: M13.2.7, M13.1.1, M13.2.4, M20.1.5, M20.2.2, M20.2.3, M20.2.4, M20.1.2, M13.9.4, M13.8.18
Task ids: M20.4.6
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_templates import _asking, _copy, _gallery, _request
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 402

#: The tool a check's draft is allowed, which every install with a database registers.
KNOWLEDGE_VERB: Final = "knowledge.search"
KNOWLEDGE_READ: Final = "read:knowledge"

NOT_FROM_BLANK: Final = "a new agent draft did not start from the blank template"
NOT_THE_TEMPLATE_PATH: Final = "a hand-built agent was not kept as a signed version and a pin"
NOT_PUBLISHED: Final = "a draft reaching nothing was not published on its author's word"
ROW_INCOMPLETE: Final = "an agent's row does not carry its persona, scope, tier and level"
NOT_EDITED: Final = "an agent's instructions could not be changed through the prompts route"
OWNER_NOT_RECORDED: Final = "the person who changed an agent's instructions is not recorded"
OWNER_TOO_WIDE: Final = "a path nobody changed was recorded as set by the person who changed one"
INTENT_PUBLISHED: Final = "a capability a builder only named was published on their word alone"
NO_SKILL: Final = "a drawing over a draft's own tool did not become a SKILL.md calling it"
FIVE_KINDS: Final = "a drawing with a step outside the five kinds was not refused"
CODE_ADMITTED: Final = "a drawing with a code step was not refused"
NOT_A_SCOPE: Final = "a branch on a condition that is not a scope predicate was not refused"
NOT_THE_SCHEMA: Final = "the builder's form is not the manifest's schema"
FORM_TO_ANYBODY: Final = "the builder's form was served to a reader who may not build"
NOT_ONE_PRESS: Final = "a template did not install in one press under its own name"
NO_LONG_WAY: Final = "a template could not be opened in the builder to change its defaults"
NOT_SAID_UNAVAILABLE: Final = "the gallery did not say installing is unavailable without a key"
INSTALLED_WITHOUT_A_KEY: Final = "a template was installed on a process with no signing key"
A_KEY_SETTING: Final = "a setting this product reads could hold a template signing key"

#: The persona a check's hand-built agent is given, and the one its editor changes it to.
PERSONA: Final = "Answers an install acceptance check about the knowledge library and nobody else."
EDITED: Final = "Answers an install acceptance check, briefly, and nobody else."


async def _builder(h: Harness, role: str, *extra: tuple[str, Scope]) -> str:
    """A reserved principal of acceptance_a who may open the gallery and build in acceptance_a."""
    from brain.agent_routes import TEMPLATE_SCREEN
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY
    from brain.console.reads import plane_capability_for
    from brain.console.screens import screen

    read = screen(TEMPLATE_SCREEN).read
    made = h.principal(A, role)
    await h.person(
        made,
        department=A,
        grants=(
            (read.requires.value, Scope.unrestricted()),
            (plane_capability_for(read, read.plane).value, Scope.unrestricted()),
            (AGENT_INSTALL_CAPABILITY.value, Scope.department(A)),
            *extra,
        ),
    )
    return made


def _body(answered: Any) -> dict[str, Any]:
    """A route's JSON body, whichever way it answered."""
    if hasattr(answered, "body"):
        return cast(dict[str, Any], json.loads(bytes(answered.body)))
    return cast(dict[str, Any], answered.model_dump(mode="json"))


def _document(
    agent_id: str,
    *,
    persona: str,
    capabilities: Sequence[str] = (),
    tools: Sequence[str] = (),
) -> dict[str, Any]:
    """A whole manifest document, as the builder's form submits one."""
    from brain.agents.template import BLANK_MANIFEST

    document: dict[str, Any] = BLANK_MANIFEST.model_dump(mode="json")
    document["identity"] = {
        **document["identity"],
        "template_id": agent_id,
        "display_name": "Acceptance check agent",
    }
    document["persona"] = persona
    document["authority"] = {
        **document["authority"],
        "scope": Scope.department(A).model_dump(mode="json"),
        "capabilities": [{"value": one} for one in capabilities],
        "allowed_tools": list(tools),
    }
    return document


async def _draft(h: Harness, app: FastAPI, builder: str, template_id: str | None = None) -> Any:
    from brain.agent_builder_routes import DraftStartAsked, start_agent_draft

    answered = await start_agent_draft(
        _request(app), DraftStartAsked(template_id=template_id), await _asking(h, builder)
    )
    if answered.status_code != 201 and template_id is None:
        raise CheckFailedError(NOT_FROM_BLANK)
    if answered.status_code != 201:
        raise CheckFailedError(NO_LONG_WAY)
    return _body(answered)


async def _saved_and_checked(
    h: Harness, app: FastAPI, builder: str, draft: Mapping[str, Any], document: dict[str, Any]
) -> int:
    from brain.agent_builder_routes import (
        DraftRevisionAsked,
        DraftSaveAsked,
        check_agent_draft,
        save_agent_draft,
    )

    asking = await _asking(h, builder)
    saved = _body(
        await save_agent_draft(
            _request(app),
            draft["draft_id"],
            DraftSaveAsked(document=document, base=draft["revision"]),
            asking,
        )
    )
    revision = int(saved["revision"])
    await check_agent_draft(
        _request(app), draft["draft_id"], DraftRevisionAsked(revision=revision), asking
    )
    return revision


async def _publish(
    h: Harness, app: FastAPI, builder: str, draft_id: str, revision: int
) -> tuple[int, dict[str, Any]]:
    from brain.agent_builder_routes import DraftPublishAsked, publish_agent_draft

    answered = await publish_agent_draft(
        _request(app),
        draft_id,
        DraftPublishAsked(revision=revision, for_department=True),
        await _asking(h, builder),
    )
    return answered.status_code, _body(answered)


# ------------------------------------------------- M13.2.7, M13.1.1, M13.2.4 a hand-built agent
@check(
    leaves=("M13.2.7", "M13.1.1", "M13.2.4"),
    sentence=(
        "A builder of acceptance_a starts a new agent from the blank template and publishes it on "
        "their own word: it is kept as a signed version and a pin, as a template install is, and "
        "its row carries its persona, scope, tier and level; a second administrator changes its "
        "instructions and the instance records them as the persona's setter and of nothing else."
    ),
)
async def a_hand_built_agent_takes_the_template_path_and_records_setters(h: Harness) -> None:
    from brain.console.workspace import Tab, tab
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.features import PROMPT_EDITING, switch
    from brain.prompt_routes import (
        INSTRUCTIONS_AUTHORITY,
        PERSONA_PATH,
        InstructionsEdit,
        edit_instructions,
    )
    from brain.tables.agent import AgentRow
    from brain.tables.audit import attributed_to
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    builder = await _builder(h, "builder")
    app = _gallery(h, secrets.token_hex(32))
    draft = await _draft(h, app, builder)
    if draft["document"]["identity"]["display_name"] != "New agent" or draft["kind"] != "new":
        raise CheckFailedError(NOT_FROM_BLANK)
    agent_id = str(draft["agent_id"])
    revision = await _saved_and_checked(
        h, app, builder, draft, _document(agent_id, persona=PERSONA)
    )
    status, _ = await _publish(h, app, builder, draft["draft_id"], revision)
    if status != 201:
        raise CheckFailedError(NOT_PUBLISHED)

    version = (
        await h.execute(
            select(TemplateVersionRow.template_id).where(TemplateVersionRow.template_id == agent_id)
        )
    ).scalar_one_or_none()
    instance = (
        await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent_id))
    ).scalar_one_or_none()
    if version is None or instance is None or instance.template_id != agent_id:
        raise CheckFailedError(NOT_THE_TEMPLATE_PATH)
    row = (await h.execute(select(AgentRow).where(AgentRow.id == agent_id))).scalar_one()
    if (
        row.persona != PERSONA
        or row.scope != Scope.department(A).model_dump(mode="json")
        or not row.tier
        or row.visibility != "department"
    ):
        raise CheckFailedError(ROW_INCOMPLETE)

    read = tab(Tab.SETTINGS).read
    from brain.console.reads import plane_capability_for

    editor = h.principal(A, "editor")
    await h.person(
        editor,
        department=A,
        grants=(
            (INSTRUCTIONS_AUTHORITY.value, Scope.department(A)),
            (read.requires.value, Scope.unrestricted()),
            (plane_capability_for(read, read.plane).value, Scope.unrestricted()),
        ),
    )
    # The switch is a setting, and its ledger entry names the check's own reach and trace.
    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, PROMPT_EDITING, on=True, by=h.actor)
        await session.commit()
    try:
        await edit_instructions(
            _request(app),
            agent_id,
            InstructionsEdit(instructions=EDITED, expected_hash=instance.effective_hash),
            await _asking(h, editor),
        )
    except Exception as refused:
        raise CheckFailedError(NOT_EDITED) from refused
    owners = (
        await h.execute(
            select(TemplateInstanceRow.field_owners).where(TemplateInstanceRow.id == agent_id)
        )
    ).scalar_one()
    if owners.get(PERSONA_PATH, {}).get("set_by") != editor:
        raise CheckFailedError(OWNER_NOT_RECORDED)
    if any(one.get("set_by") == editor for path, one in owners.items() if path != PERSONA_PATH):
        raise CheckFailedError(OWNER_TOO_WIDE)


# --------------------------------------------- M20.1.5 and M20.2.x intent, and the canvas
@check(
    leaves=("M20.1.5", "M20.2.2", "M20.2.3", "M20.2.4"),
    sentence=(
        "A builder of acceptance_a who holds no read of the knowledge library names it in a "
        "draft, and publishing it alone makes no agent; on the canvas a drawing over the draft's "
        "own tool becomes a SKILL.md calling it, while a step outside the five kinds, a code step "
        "and a branch on anything but a scope predicate are each refused."
    ),
)
async def an_authored_list_is_intent_and_the_canvas_draws_five_kinds_only(h: Harness) -> None:
    from brain.agent_builder_routes import REFUSED, ProcedureAsked, draw_agent_procedure
    from brain.core.errors import Absent
    from brain.tables.agent import AgentRow

    builder = await _builder(h, "author")
    app = _gallery(h, secrets.token_hex(32))
    draft = await _draft(h, app, builder)
    agent_id = str(draft["agent_id"])
    revision = await _saved_and_checked(
        h,
        app,
        builder,
        draft,
        _document(
            agent_id, persona=PERSONA, capabilities=(KNOWLEDGE_READ,), tools=(KNOWLEDGE_VERB,)
        ),
    )
    await _publish(h, app, builder, draft["draft_id"], revision)
    made = (await h.execute(select(AgentRow.id).where(AgentRow.id == agent_id))).first()
    if made is not None:
        raise CheckFailedError(INTENT_PUBLISHED)

    # The canvas offers the registered tools the draft's verbs bind to; asked as somebody who
    # reaches the library, so the binding has something to bind to.
    drawer = await _builder(h, "drawer", (KNOWLEDGE_READ, Scope.department(A)))
    canvas = await _draft(h, app, drawer)
    await _saved_and_checked(
        h,
        app,
        drawer,
        canvas,
        _document(
            str(canvas["agent_id"]),
            persona=PERSONA,
            capabilities=(KNOWLEDGE_READ,),
            tools=(KNOWLEDGE_VERB,),
        ),
    )

    async def drawn(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Any:
        try:
            return _body(
                await draw_agent_procedure(
                    _request(app),
                    canvas["draft_id"],
                    ProcedureAsked(
                        drawing={"nodes": nodes, "edges": edges},
                        name="look-it-up",
                        description="Use when somebody asks the check a question.",
                    ),
                    await _asking(h, drawer),
                )
            )
        except Absent:
            return None

    tool = "knowledge.search_documents"
    line = [
        {"from": "start", "to": "look", "way": "next"},
        {"from": "look", "to": "done", "way": "next"},
    ]
    good = await drawn(
        [
            {"id": "start", "kind": "start"},
            {"id": "look", "kind": "tool_call", "tool": tool},
            {"id": "done", "kind": "finish"},
        ],
        line,
    )
    if not isinstance(good, dict) or f"call `{tool}`" not in str(good.get("skill", "")):
        raise CheckFailedError(NO_SKILL)

    def refused(answered: Any) -> bool:
        # The route's own refusal: a 409 saying it refused, and never a step that was missing
        # for some other reason, which would read as the canvas refusing what it never saw.
        return isinstance(answered, dict) and answered.get("outcome") == REFUSED

    if not refused(
        await drawn(
            [
                {"id": "start", "kind": "start"},
                {"id": "look", "kind": "loop", "tool": tool},
                {"id": "done", "kind": "finish"},
            ],
            line,
        )
    ):
        raise CheckFailedError(FIVE_KINDS)
    if not refused(
        await drawn(
            [
                {"id": "start", "kind": "start"},
                {"id": "look", "kind": "code", "tool": tool},
                {"id": "done", "kind": "finish"},
            ],
            line,
        )
    ):
        raise CheckFailedError(CODE_ADMITTED)
    if not refused(
        await drawn(
            [
                {"id": "start", "kind": "start"},
                {"id": "fork", "kind": "branch", "predicate": {"expression": "amount > 100"}},
                {"id": "look", "kind": "tool_call", "tool": tool},
                {"id": "done", "kind": "finish"},
            ],
            [
                {"from": "start", "to": "fork", "way": "next"},
                {"from": "fork", "to": "look", "way": "holds"},
                {"from": "fork", "to": "done", "way": "otherwise"},
                {"from": "look", "to": "done", "way": "next"},
            ],
        )
    ):
        raise CheckFailedError(NOT_A_SCOPE)


# ------------------------------------------------------ M20.1.2, M13.9.4, M13.8.18 the gallery
@check(
    leaves=("M20.1.2", "M13.9.4", "M13.8.18"),
    sentence=(
        "A builder of acceptance_a is served a form that is the manifest's schema, and a reader "
        "who may not build is not; a template installs in one press under its own name and opens "
        "in the builder with its words; without a signing key the gallery says installing is "
        "unavailable, installs nothing, and no setting this product reads can hold a key."
    ),
)
async def the_form_is_the_manifest_and_a_template_installs_in_one_press(h: Harness) -> None:
    from brain.agent_builder_routes import builder_form
    from brain.agent_lifecycle_routes import NO_SIGNING_KEY_HERE, template_version
    from brain.agents.catalogue import business_analyst
    from brain.agents.install_store import version_values
    from brain.agents.template import TemplateManifest, publish
    from brain.builder.form import form_document
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_templates import _install
    from brain.settings import Settings
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateVersionRow

    builder = await _builder(h, "gallery")
    # The served form against the generator run over the manifest's schema as it is now: a form
    # kept by hand, or cut from an older schema, differs from it.
    form = _body(await builder_form(await _asking(h, builder)))
    if not form.get("sections") or form != form_document(TemplateManifest.model_json_schema()):
        raise CheckFailedError(NOT_THE_SCHEMA)
    stranger = h.principal(A, "stranger")
    await h.person(stranger, department=A, grants=())
    try:
        await builder_form(await _asking(h, stranger))
    except Absent:
        pass
    else:
        raise CheckFailedError(FORM_TO_ANYBODY)

    key = secrets.token_hex(32)
    app = _gallery(h, key)
    shipped = business_analyst()
    signed = publish(
        _copy(shipped, f"acceptance_{h.run}_one_press"), key=key, signed_by=builder, at=h.now
    )
    await h.execute(
        *h.attributed(builder), insert(TemplateVersionRow).values(**version_values(signed))
    )
    made = await _install(h, app, builder, signed)
    name = (
        await h.execute(
            select(AgentRow.display_name).where(AgentRow.id == made["agent"]["agent_id"])
        )
    ).scalar_one_or_none()
    if name != shipped.identity.display_name:
        raise CheckFailedError(NOT_ONE_PRESS)
    opened = await _draft(h, app, builder, shipped.identity.template_id)
    if opened["document"].get("persona") != shipped.persona:
        raise CheckFailedError(NO_LONG_WAY)

    keyless = _gallery(h, "")
    view = await template_version(
        _request(keyless),
        signed.manifest.identity.template_id,
        signed.manifest.identity.version,
        await _asking(h, builder),
    )
    if view.unavailable != NO_SIGNING_KEY_HERE:
        raise CheckFailedError(NOT_SAID_UNAVAILABLE)
    before = (await h.execute(select(AgentRow.id))).all()
    try:
        await _install(h, keyless, builder, signed)
    except CheckFailedError:
        pass
    else:
        raise CheckFailedError(INSTALLED_WITHOUT_A_KEY)
    if (await h.execute(select(AgentRow.id))).all() != before:
        raise CheckFailedError(INSTALLED_WITHOUT_A_KEY)
    if any("template" in name and "key" in name for name in Settings.model_fields):
        raise CheckFailedError(A_KEY_SETTING)


# --------------------------------------------------------------- M20.4.6 the publish record
NO_HISTORY: Final = "an agent's publish history did not list both of its publishes"
WRONG_PATHS: Final = "a second publish was recorded with paths other than the one it changed"
NOT_WHO: Final = "a publish was recorded under somebody other than its publisher"


@check(
    leaves=("M20.4.6",),
    sentence=(
        "A builder of acceptance_a publishes a new agent, then changes only its instructions as "
        "a draft and publishes again: the agent's publish history lists both, each with who and "
        "when, and the second names exactly the instructions as what changed."
    ),
)
async def a_second_publish_is_recorded_with_exactly_the_paths_it_changed(h: Harness) -> None:
    from brain.agent_builder_routes import agent_publications, edit_agent_as_draft

    builder = await _builder(h, "publisher")
    app = _gallery(h, secrets.token_hex(32))
    draft = await _draft(h, app, builder)
    agent_id = str(draft["agent_id"])
    first = await _saved_and_checked(h, app, builder, draft, _document(agent_id, persona=PERSONA))
    if (await _publish(h, app, builder, draft["draft_id"], first))[0] != 201:
        raise CheckFailedError(NOT_PUBLISHED)
    edit = _body(await edit_agent_as_draft(_request(app), agent_id, await _asking(h, builder)))
    changed = {**edit["document"], "persona": EDITED}
    second = await _saved_and_checked(h, app, builder, edit, changed)
    if (await _publish(h, app, builder, edit["draft_id"], second))[0] != 201:
        raise CheckFailedError(NOT_PUBLISHED)

    history = (
        await agent_publications(_request(app), agent_id, await _asking(h, builder))
    ).publications
    if len(history) != 2:
        raise CheckFailedError(NO_HISTORY)
    if history[1].paths != ["persona"]:
        raise CheckFailedError(WRONG_PATHS)
    if any(one.published_by != builder for one in history):
        raise CheckFailedError(NOT_WHO)
