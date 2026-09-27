"""Finishing an agent install: `complete` is called, and the version, instance and agent are
written.

`brain.agents.install` holds what an install is and `tests/e2e/test_wave_three_installed_agent.py`
installs the catalogue through it in memory. This file holds the end of that flow on a database:
the rows `brain.agents.install_store.StoredAgentInstalls.finish` writes read back through the
readers the console already uses, a second finish writes nothing, and a version on file with another
body is refused before anything is written. The first half needs no server; **the second skips when
there is no server**, and CI always has one.

Task ids: M13.3.6, M13.3.7, M38.2.2.4
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import select

from brain.agent_routes import install_for, install_of, manifest_of, record_of
from brain.agents import catalogue
from brain.agents.install import (
    InstallDraft,
    TemplateCatalogue,
    begin,
    complete,
    provide,
)
from brain.agents.install_store import (
    InstallStoreError,
    StoredAgentInstalls,
    agent_values,
    instance_values,
    version_values,
)
from brain.agents.model import AgentViewer
from brain.agents.template import SYSTEM_PUBLISHER, SignedManifest, TemplateError, publish
from brain.app import Settings
from brain.session import make_session_factory
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.startup import build_registry
from tests.e2e.test_wave_three_installed_agent import (
    AUDIENCE,
    INSTALLER,
    OFFERED_TO,
    PLACEHOLDER_ANSWERS,
    SIGNING_KEY,
    NoRows,
    serving,
)
from tests.fixtures.company import NOW
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_memory_store import through_0061

MANIFEST = catalogue.internal_helpdesk()


def a_draft(key: str = SIGNING_KEY) -> InstallDraft:
    """The helpdesk opened and answered as an installer does it, signed with `key`."""
    signed = publish(MANIFEST, key=key, signed_by=SYSTEM_PUBLISHER, at=NOW)
    shelf = TemplateCatalogue()
    shelf.offer(signed, audience=OFFERED_TO)
    viewer = AgentViewer(principal_id=INSTALLER, departments=frozenset({"maintenance"}))
    draft = begin(
        shelf.open_for(MANIFEST.identity.template_id, viewer),
        instance_id=MANIFEST.identity.template_id,
        installer=INSTALLER,
    )
    for placeholder in MANIFEST.placeholders:
        if placeholder.required:
            draft = provide(draft, placeholder.key, PLACEHOLDER_ANSWERS[placeholder.key])
    return draft


def tools() -> Any:
    return build_registry(source=Settings(env="development").tool_source, records=NoRows())


def finishing(store: StoredAgentInstalls, draft: InstallDraft) -> Callable[[], Awaitable[Any]]:
    return lambda: store.finish(
        draft,
        key=SIGNING_KEY,
        audience=AUDIENCE,
        registry=serving(MANIFEST.connectors),
        tools=tools(),
        at=NOW,
    )


# ------------------------------------------------------------------ without a server
def test_the_rows_read_back_through_the_consoles_own_readers_as_the_installation() -> None:
    """The version as a signed manifest, the agent as `record_of` builds it, and the instance as
    `install_of` materialises it.

    Delete this and an install could be written in a shape the console reads as no agent, or as an
    agent with no lineage."""
    draft = a_draft()
    installed = complete(
        draft,
        key=SIGNING_KEY,
        audience=AUDIENCE,
        registry=serving(MANIFEST.connectors),
        tools=tools(),
        at=NOW,
    )
    signed = draft.offer.signed
    version = version_values(signed)
    rebuilt = SignedManifest(
        manifest=manifest_of(version["document"]),
        content_digest=version["content_digest"],
        signature=version["signature"],
        signed_by=version["signed_by"],
        signed_at=version["signed_at"],
    )
    assert rebuilt == signed

    record = record_of(AgentRow(**agent_values(installed.record)))
    assert record == installed.record

    shown = install_of(
        TemplateInstanceRow(**instance_values(installed)), TemplateVersionRow(**version), record
    )
    assert shown is not None
    assert (shown.template_id, shown.template_version) == (
        MANIFEST.identity.template_id,
        MANIFEST.identity.version,
    )


def test_a_draft_the_domain_refuses_opens_no_connection() -> None:
    """Signed with another key: `complete` refuses before the store is asked for a session.

    Delete this and a manifest nobody on this install signed could reach the database first."""

    def no_session() -> Any:
        msg = "the store opened a session for a draft the domain refuses"
        raise AssertionError(msg)

    store = StoredAgentInstalls(no_session)  # type: ignore[arg-type]
    with pytest.raises(TemplateError, match="not made by this installation's key"):
        run(finishing(store, a_draft(key="somebody-elses-key")))


# ------------------------------------------------------------------ with a server
def counts(url: str) -> tuple[int, int, int]:
    [(versions, instances, agents)] = sql(
        url,
        "SELECT (SELECT count(*) FROM agent.template_version),"
        " (SELECT count(*) FROM agent.template_instance), (SELECT count(*) FROM agent.agent)",
    )
    return versions, instances, agents


def test_an_install_writes_the_three_rows_the_console_reads_and_a_second_writes_none() -> None:
    """As the application role. The agent reads back selectable and published to the installer's
    chosen audience, its install joins its version, and a second finish of the same draft writes
    nothing and says so.

    Delete this and `install.complete` could go back to having no caller that reaches a table."""
    with through_0061("brain_agent_install_store") as url:

        async def go() -> tuple[Any, Any, Any, Any]:
            built = app_engine(url)
            try:
                sessions = make_session_factory(built)
                store = StoredAgentInstalls(sessions)
                first = await finishing(store, a_draft())()
                second = await finishing(store, a_draft())()
                async with sessions() as session:
                    row = (
                        await session.execute(
                            select(AgentRow).where(AgentRow.id == MANIFEST.identity.template_id)
                        )
                    ).scalar_one()
                    joined = (await session.execute(install_for(row.id))).one()
                return first, second, record_of(row), joined
            finally:
                await built.dispose()

        first, second, record, joined = run(go)
        written = counts(url)

    assert (first.created, second.created) == (True, False)
    assert written == (1, 1, 1)
    assert record == first.installation.record
    assert record.is_selectable
    assert record.audience == AUDIENCE
    assert install_of(joined[0], joined[1], record) is not None


def test_a_version_on_file_with_another_body_is_refused_and_nothing_is_written() -> None:
    """The same template and version already on file under a different signature.

    Delete this and a republish under a number somebody already installed would be pinned to by a
    new instance while the old ones pin the body they were installed from."""
    with through_0061("brain_agent_install_forged") as url:
        values = version_values(a_draft().offer.signed)
        sql(
            url,
            "INSERT INTO agent.template_version (template_id, version, content_digest, signature,"
            " signed_by, signed_at, document) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
            values["template_id"],
            values["version"],
            values["content_digest"],
            "f" * 64,
            values["signed_by"],
            values["signed_at"],
            json.dumps(values["document"]),
        )

        async def go() -> None:
            built = app_engine(url)
            try:
                await finishing(StoredAgentInstalls(make_session_factory(built)), a_draft())()
            finally:
                await built.dispose()

        with pytest.raises(InstallStoreError, match="on file with another body"):
            run(go)
        written = counts(url)

    assert written == (1, 0, 0)
