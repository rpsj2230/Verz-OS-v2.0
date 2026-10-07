"""Install acceptance checks for the two ways an agent's run reads a skill: its instructions and its
script.

Both go through `POST /answer`'s own function with an agent installed from a template the check
signs, so what is proved is the path a person's question takes: the agent's offered skills read at
the asker's reach, the registry the application builds with the skill tools in it
(`brain.tools.startup.build_registry`), the runtime's loop (`brain.gate.runtime`) and the caller
that binds the run's agent and offered skills (`brain.api_routes.RunToolCaller`). The model is the
check's stand-in, answering in the process with a script of replies and keeping every request it is
sent, as `brain.ops.acceptance_checks_skill_runs` does.

**Progressive disclosure is read where the model receives it (M12.2.8).** The first request carries
the skill's name and description and not its body; the body arrives in the request that follows the
model's ask for it, by the tool, and a skill the library approved and nobody assigned to the agent
is refused when asked for by name, with the one sentence every unavailable tool gets, and its body
is in no request. Rejected: reading the ledger's `skill_uses`, which records that a card was offered
and not what the model was shown.

**A script runs only through the one tool, and only as approved (M12.2.9, M12.4.11).** The
sandbox is the install's own where `INSTALL_SERVICES` names it, and where it names none the check
answers from a transport in the process, as `brain.ops.acceptance_checks_skill_packages` does for
the runner alone, so the two leaves are held (`docs/proof-sweep-holds.json`) until the install runs
a sandbox of its own and the check has talked to it. What the check shows either way is the
product's path: the tool is registered and no second path runs a script, the approved bytes are
sent once and the model is handed what the script printed, and the same run over a library that
hands back other bytes sends the sandbox nothing and the model only the refusal.

Task ids: M12.2.8, M12.2.9, M12.4.11
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_routing import StandIns
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    import httpx

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 700

SCRIPT_PATH: Final = "scripts/check.py"

NOT_ANSWERED: Final = "a question asked through an agent holding the skill tools was not run"
NO_CARD: Final = "an agent's first request did not show the model the skill it is assigned"
BODY_BEFORE_ASKED: Final = "a skill's instructions were sent to the model before it asked for them"
NO_BODY_ON_ASKING: Final = (
    "a model that asked for an assigned skill's instructions was not sent them"
)
UNASSIGNED_READ: Final = "a model that asked for a skill nobody assigned to its agent was sent it"
NO_TOOL_REGISTERED: Final = "the application's registry holds no tool for a skill's instructions"
TWO_EXECUTION_TOOLS: Final = "the registry holds more than one way to run a skill's script"
NO_SCRIPT_TOOL: Final = "the registry built over a sandbox holds no tool that runs a script"
SCRIPT_NEVER_SENT: Final = (
    "an agent's run that asked for its skill's script sent the sandbox no run"
)
SCRIPT_SENT_MORE_THAN_ONCE: Final = "a script an agent's run asked for once was sent more than once"
OUTPUT_NOT_HANDED_BACK: Final = "what an approved script printed was not handed to the model"
CHANGED_SCRIPT_RAN: Final = (
    "a script whose bytes were not the approved ones was sent to the sandbox"
)
CHANGED_SCRIPT_OUTPUT: Final = "a model was handed the output of a script that was not as approved"


@dataclass
class _Scripted(StandIns):
    """The stand-in model, replying from a script and keeping the messages of every request."""

    replies: list[str] = field(default_factory=list)
    shown: list[str] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import httpx

        body = json.loads(request.content)
        model = str(body.get("model", ""))
        self.asked[(request.url.host, model)] += 1
        self.shown.append(
            "\n".join(str(one.get("content", "")) for one in body.get("messages", []))
        )
        said = self.replies.pop(0) if self.replies else '{"answer": "done"}'
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-acceptance",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": said},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 8},
            },
        )


def _asks(tool: str, arguments: dict[str, str]) -> str:
    """One model reply asking for a tool, in the runtime's own one-object form."""
    return json.dumps({"tool": tool, "arguments": arguments})


@dataclass
class _Stage:
    """What both checks stand on: a reader, an administrator, an agent and the scripted model."""

    reader: str
    question: str
    admin: str
    responder: _Scripted
    app: Any
    agent: str = ""


async def _stand(
    h: Harness,
    replies: list[str],
    capabilities: tuple[str, ...],
    scoped: tuple[tuple[str, Scope], ...] = (),
) -> _Stage:
    """A member of acceptance_a with a document, holding `capabilities` company-wide, a skills
    administrator, and the application over a scripted model, as `skill_runs` builds its own."""
    from brain.ops.acceptance_checks_skills import _administrator, _everywhere
    from brain.ops.acceptance_models import (
        STAND_IN,
        a_reader_with_a_document,
        askable,
        asking_app,
        models_for,
        pinned,
    )
    from brain.ops.acceptance_routing import (
        ANSWERS,
        constrained,
        roster_over,
        stand_in_drivers,
        step,
    )

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    for one, scope in (*_everywhere(*capabilities), *scoped):
        await h.grant(reader, one, scope)
    admin = await _administrator(h, "skilltools")
    responder = _Scripted(replies=replies)
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS),))
    app = await asking_app(h, models)
    app.state.agent_roster = roster_over(h)
    return _Stage(
        reader=reader, question=paired.question, admin=admin, responder=responder, app=app
    )


async def _approved(h: Harness, admin: str, package: Any) -> Any:
    """A package added to the library as its administrator would and approved by a second
    reviewer's act in the store, as `acceptance_checks_skills` does it."""
    from brain.console.skill_library import added
    from brain.ops.acceptance_checks_skill_packages import _approved_in_store
    from brain.ops.acceptance_checks_skills import _store

    reach = await h.reach(admin)
    made = added(package, by=admin, at=h.now)
    await _store(h, made, reach)
    return await _approved_in_store(h, admin, made.digest)


async def _agent(
    h: Harness, stage: _Stage, skills: Any, capabilities: tuple[str, ...], tools: tuple[str, ...]
) -> None:
    """An agent of acceptance_a over everything, assigned `skills`, allowed `tools`."""
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_workspace import installed_agent

    stage.agent = await installed_agent(
        h,
        stage.admin,
        skills=tuple((one.imported.skill.name, one.digest) for one in skills),
        capabilities=(*KNOWLEDGE_READS, *capabilities),
        allowed_tools=tools,
        scope=Scope.unrestricted(),
        suffix="_skilltools",
    )


async def _asked(h: Harness, stage: _Stage, n: int) -> None:
    from brain.ops.acceptance_routing import asking

    await asking(h, stage.app, stage.reader, stage.question, n, agent=stage.agent)


def _registry(h: Harness, scripts: Any = None, website: Any = None) -> Any:
    """The application's registry over the check's own rows, with the skill tools in it."""
    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.skill_tools import SkillTools
    from brain.tools.startup import build_registry

    return build_registry(
        source=h.settings.tool_source,
        records=SessionRowSource(h.sessions),
        skills=SkillTools(scripts=scripts),
        website=website,
    )


# ------------------------------------------------ 1. instructions on demand (M12.2.8)
@check(
    leaves=("M12.2.8",),
    sentence=(
        "A member of acceptance_a asks through an agent assigned an approved skill: the model's "
        "first request carries the skill's name and description and not its body, the body "
        "reaches it in the request after it asks for the skill by name, and a skill the library "
        "approved and nobody assigned to the agent is refused when asked for and in no request."
    ),
)
async def a_skills_body_reaches_a_model_only_when_it_asks_for_it(h: Harness) -> None:
    from brain.console.skill_library import read_package
    from brain.ops.acceptance_checks_skills import _named, _skill_md
    from brain.tools.skill_tools import INSTRUCTIONS_CAPABILITY, INSTRUCTIONS_TOOL
    from brain.tools.skills import SkillError

    assigned_name, other_name = _named(h, "disclosed"), _named(h, "withheld")
    stage = await _stand(
        h,
        [
            _asks(INSTRUCTIONS_TOOL, {"skill": assigned_name}),
            _asks(INSTRUCTIONS_TOOL, {"skill": other_name}),
            '{"answer": "done"}',
        ],
        (INSTRUCTIONS_CAPABILITY.value,),
    )
    registry = _registry(h)
    if not registry.has(INSTRUCTIONS_TOOL):
        raise CheckFailedError(NO_TOOL_REGISTERED)
    stage.app.state.tools = registry
    marker = h.word()
    kept = []
    for name, body in (
        (assigned_name, f"Check the expiry then say {marker}."),
        (other_name, h.word()),
    ):
        package = read_package("SKILL.md", _skill_md(name, body=(body,)))
        kept.append(await _approved(h, stage.admin, package))
    assigned, other = kept
    await _agent(h, stage, [assigned], (INSTRUCTIONS_CAPABILITY.value,), (INSTRUCTIONS_TOOL,))
    try:
        await _asked(h, stage, 1)
    except SkillError:
        raise CheckFailedError(NOT_ANSWERED) from None

    shown = stage.responder.shown
    if len(shown) < 3:
        raise CheckFailedError(NOT_ANSWERED)
    card = assigned.imported.skill
    if card.name not in shown[0] or card.description not in shown[0]:
        raise CheckFailedError(NO_CARD)
    if marker in shown[0]:
        raise CheckFailedError(BODY_BEFORE_ASKED)
    if marker not in shown[1]:
        raise CheckFailedError(NO_BODY_ON_ASKING)
    unread = other.imported.skill.body.strip()
    if any(unread in one for one in shown):
        raise CheckFailedError(UNASSIGNED_READ)


# ----------------------------------------- 2. a script runs only as approved (M12.2.9, M12.4.11)
@check(
    leaves=("M12.2.9", "M12.4.11"),
    sentence=(
        "An agent assigned an approved skill carrying a script asks for it through the one "
        "execution tool: the sandbox, the install's own where it runs one and the process's where "
        "it does not, is sent the approved bytes once and the model is handed what they printed; "
        "over a library handing back other bytes the sandbox is sent nothing, the model no output."
    ),
)
async def a_skills_script_runs_through_the_one_tool_and_only_as_approved(h: Harness) -> None:
    import httpx

    from brain.console.skill_library import read_package
    from brain.ops.acceptance_checks_skill_packages import _zip_of
    from brain.ops.acceptance_checks_skills import _named, _skill_md
    from brain.ops.overlays import OverlayError, components_switched_on, switched_on_here
    from brain.ops.sandbox import AnswerStatus, RunAnswer, sandbox_address
    from brain.ops.skill_store import StoredSkills
    from brain.tools.registry import SKILL_SCRIPT_OBJECT
    from brain.tools.run_skill import SCRIPT_CAPABILITY, assert_single_execution_path
    from brain.tools.skill_tools import ScriptSandbox
    from brain.tools.skills import execution_tool

    name = _named(h, "scripted")
    printed = h.word()
    script = f"print({printed!r})\n".encode()
    declared = _skill_md(name, extra=(f"scripts: [{SCRIPT_PATH}]",))
    package = read_package(f"{name}.zip", _zip_of({"SKILL.md": declared, SCRIPT_PATH: script}))
    request = {"skill": name, "script": SCRIPT_PATH}
    read_output = f"read:{SKILL_SCRIPT_OBJECT}"
    stage = await _stand(
        h,
        [_asks(execution_tool(), request), '{"answer": "done"}'],
        (SCRIPT_CAPABILITY.value, read_output),
    )
    kept = await _approved(h, stage.admin, package)
    store = StoredSkills(h.sessions)

    try:
        address = sandbox_address(
            h.settings.sandbox_url, components_switched_on(switched_on_here())
        )
    except OverlayError:
        address = None
    sent: list[dict[str, Any]] = []

    def stand_in(call: httpx.Request) -> httpx.Response:
        body = json.loads(call.content)
        sent.append(body)
        return httpx.Response(
            200,
            json=RunAnswer(
                run_id=str(body["run_id"]),
                status=AnswerStatus.COMPLETED,
                exit_code=0,
                output=printed + chr(10),
                elapsed_seconds=0.01,
            ).to_json(),
        )

    client = (
        httpx.Client()
        if address is not None
        else httpx.Client(transport=httpx.MockTransport(stand_in))
    )
    h.removes(client.close)

    def over(files: dict[str, bytes] | None) -> ScriptSandbox:
        async def read(digest: str) -> dict[str, bytes]:
            return await store.script_bytes(digest) if files is None else dict(files)

        return ScriptSandbox(
            address=address or "http://sandbox.invalid:3100", client=client, script_bytes=read
        )

    registry = _registry(h, over(None))
    if not registry.has(execution_tool()):
        raise CheckFailedError(NO_SCRIPT_TOOL)
    try:
        assert_single_execution_path(registry)
    except Exception:
        raise CheckFailedError(TWO_EXECUTION_TOOLS) from None
    stage.app.state.tools = registry
    await _agent(
        h,
        stage,
        [kept],
        (SCRIPT_CAPABILITY.value, read_output),
        (execution_tool(),),
    )
    await _asked(h, stage, 1)
    shown = stage.responder.shown
    if len(shown) < 2 or printed not in shown[1]:
        raise CheckFailedError(OUTPUT_NOT_HANDED_BACK)
    if address is None:
        if not sent:
            raise CheckFailedError(SCRIPT_NEVER_SENT)
        if len(sent) > 1:
            raise CheckFailedError(SCRIPT_SENT_MORE_THAN_ONCE)

    # The same run over a library that hands back other bytes: nothing is run, nothing is shown.
    sent.clear()
    stage.responder.shown.clear()
    stage.responder.replies[:] = [_asks(execution_tool(), request), '{"answer": "done"}']
    stage.app.state.tools = _registry(h, over({SCRIPT_PATH: script + b"import os\n"}))
    await _asked(h, stage, 2)
    if sent:
        raise CheckFailedError(CHANGED_SCRIPT_RAN)
    if any(printed in one for one in stage.responder.shown[1:]):
        raise CheckFailedError(CHANGED_SCRIPT_OUTPUT)


# ------------------------------------------------ 3. a run checks a website (M12.4.4)
class _Recording:
    """The install's HTTPS prober, keeping the host of every hop it makes."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.hosts: list[str] = []

    async def probe(self, target: Any, *, timeout_seconds: float) -> Any:
        self.hosts.append(str(target.host))
        return await self.inner.probe(target, timeout_seconds=timeout_seconds)


#: The one public site the check asks about. Reserved by RFC 2606 for documentation and answered
#: by its registry, so asking it reaches nobody; the check asks for no other.
THE_SITE: Final = "example.com"

#: A host the asker holds no grant for, which the check names and the run must not contact.
THE_OTHER_SITE: Final = "example.org"

THE_SITE_COULD_NOT_BE_REACHED: Final = (
    "this install could not reach the documentation site the check asks about, so a website "
    "check could not be shown to work from here"
)
NOTHING_WAS_FOUND_OUT: Final = (
    "a run that asked for a website check was handed no status, certificate or time"
)
THE_OTHER_SITE_WAS_CONTACTED: Final = "a run's website check contacted a host outside its reach"
THE_BROWSER_WAS_OPENED: Final = "a website check opened a browser nobody asked for"
THE_BROWSER_WAS_PRETENDED: Final = (
    "a website check asked to inspect a page, where no browser runs, did not say so"
)


def _website_transport() -> tuple[Any, Any]:
    """The install's own resolver and HTTPS prober, as `brain.app` builds the website check with.

    A function so a test hands the check a site that answers without a network: the database half
    of the tests never opens a socket, and CI is not asked to reach the documentation site.
    """
    from brain.ops.webhook_delivery import SystemResolver
    from brain.ops.website_probe import HttpsProber

    return SystemResolver(), HttpsProber()


@check(
    leaves=("M12.4.4",),
    sentence=(
        "A member of acceptance_a granted the website check for one public documentation site asks "
        "through an agent allowed the tool: the run is handed that site's status, redirects, "
        "certificate days and response time read over HTTPS, no browser is opened for it, an "
        "address outside the grant is contacted by nobody, and a page to be inspected where no "
        "browser runs is said not to be available."
    ),
)
async def a_run_checks_a_website_and_is_handed_what_it_found(h: Harness) -> None:
    from brain.core.scope import Clause, Op
    from brain.tools.website_check import (
        HOST_FIELD,
        WEBSITE_CHECK_CAPABILITY,
        WEBSITE_CHECK_TOOL,
        WebsiteCheckTool,
    )

    site = f"https://{THE_SITE}/"
    scope = Scope(clauses=(Clause(field=HOST_FIELD, op=Op.IN, value=(THE_SITE,)),))
    stage = await _stand(
        h,
        [
            _asks(WEBSITE_CHECK_TOOL, {"address": site}),
            _asks(WEBSITE_CHECK_TOOL, {"address": f"https://{THE_OTHER_SITE}/"}),
            json.dumps(
                {
                    "tool": WEBSITE_CHECK_TOOL,
                    "arguments": {"address": site, "inspect_rendered_page": True},
                }
            ),
            '{"answer": "done"}',
        ],
        (),
        scoped=((WEBSITE_CHECK_CAPABILITY.value, scope),),
    )
    resolver, transport = _website_transport()
    prober = _Recording(transport)
    registry = _registry(h, website=WebsiteCheckTool(resolver=resolver, prober=prober))
    stage.app.state.tools = registry
    await _agent(h, stage, [], (WEBSITE_CHECK_CAPABILITY.value,), (WEBSITE_CHECK_TOOL,))
    await _asked(h, stage, 1)

    shown = stage.responder.shown
    if len(shown) < 4:
        raise CheckFailedError(NOT_ANSWERED)
    first = shown[1]
    if '"outcome": "unreachable"' in first:
        raise CheckNotRunError(THE_SITE_COULD_NOT_BE_REACHED)
    for field_read in ('"status": 200', '"certificate_expires_in_days": ', '"response_seconds": '):
        if field_read not in first:
            raise CheckFailedError(NOTHING_WAS_FOUND_OUT)
    if '"browser": "not_asked"' not in first:
        raise CheckFailedError(THE_BROWSER_WAS_OPENED)
    if THE_OTHER_SITE in prober.hosts or set(prober.hosts) != {THE_SITE}:
        raise CheckFailedError(THE_OTHER_SITE_WAS_CONTACTED)
    if '"browser": "not_available"' not in shown[3]:
        raise CheckFailedError(THE_BROWSER_WAS_PRETENDED)
