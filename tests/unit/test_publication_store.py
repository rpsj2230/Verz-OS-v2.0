"""An agent's publish history, computed on read from its stored versions (M20.4.6).

The pure half holds `publication_history` to `record_publish` over consecutive versions with the
publish's own stamps left out. The database half writes two signed versions of one agent and its
drafts' acts as the superuser, reads the history back through `StoredPublications` as the
application role, and holds what is served to `record_publish` over the two stored documents.

Task ids: M20.4.6
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.agents.template import BLANK_MANIFEST, publish
from brain.builder.publish import (
    STAMPED_PATHS,
    PublishDecision,
    PublishedVersion,
    publication_history,
    record_publish,
)
from brain.gate.injection import AutonomyTier
from tests.unit.test_acceptance import at_head

AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
KEY = "cd" * 32
AGENT = "agent_history"


def versions() -> tuple[Any, Any]:
    """Two signed versions of one hand-built agent: the second changes only the persona."""
    identity = BLANK_MANIFEST.identity.model_copy(update={"template_id": AGENT, "version": 1})
    first = BLANK_MANIFEST.model_copy(update={"identity": identity, "persona": "Answer once."})
    second = first.model_copy(
        update={
            "identity": identity.model_copy(update={"version": 2, "published_by": "u_editor"}),
            "persona": "Answer once, briefly.",
        }
    )
    return (
        publish(first, key=KEY, signed_by="u_builder", at=AT),
        publish(second, key=KEY, signed_by="u_editor", at=AT + timedelta(days=1)),
    )


def unstamped(document: dict[str, Any]) -> dict[str, Any]:
    return {path: value for path, value in document.items() if path not in STAMPED_PATHS}


def expected(first: Any, second: Any) -> Any:
    return record_publish(
        agent_id=AGENT,
        actor_id=second.signed_by,
        at=second.signed_at,
        before=unstamped(first.manifest.document()),
        after=unstamped(second.manifest.document()),
        decision=PublishDecision(
            agent_id=AGENT, rung=AutonomyTier.SHADOW, approvers=1, widenings=(), refusals=()
        ),
        approvers=("u_approver",),
    )


def test_the_history_of_a_second_publish_is_record_publish_over_the_two_versions() -> None:
    """**The served diff is `record_publish` over the two stored versions, and nothing else.**
    The first publish names every path it set, the second only the persona, and neither names the
    version or publisher stamps the publish writes itself. Delete this and the history can drift
    from the function the ledger's own diff uses, or report a version bump as an author's change."""
    first, second = versions()
    history = publication_history(
        AGENT,
        [
            PublishedVersion(
                version=one.manifest.identity.version,
                published_by=one.signed_by,
                published_at=one.signed_at,
                document=one.manifest.document(),
            )
            for one in (second, first)
        ],
        {2: ["u_approver"]},
    )

    assert [one.actor_id for one in history] == ["u_builder", "u_editor"]
    assert history[1] == expected(first, second)
    assert history[1].paths == ("persona",)
    assert not set(STAMPED_PATHS) & set(history[0].paths)
    assert "persona" in history[0].paths


@pytest.mark.needs_db
def test_the_stored_history_is_record_publish_over_the_two_stored_versions() -> None:
    """The same, read off PostgreSQL: two versions and the acts of the two drafts that published
    them, written as the superuser, read back as the application role. The second's approver is the
    person whose `approved` act sits on the draft whose `published` act carries its signing instant.
    Delete this and the store can match a version to the wrong draft, or read nothing, while the
    pure test stays green."""
    from brain.builder.publication_store import StoredPublications
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_session_factory
    from tests.fixtures.scratch_postgres import sql

    first, second = versions()
    with at_head("brain_publication_store") as url:
        for one in (first, second):
            sql(
                url,
                "INSERT INTO agent.template_version (template_id, version, content_digest,"
                " signature, signed_by, signed_at, document) VALUES (%s, %s, %s, %s, %s, %s,"
                " %s::jsonb)",
                AGENT,
                one.manifest.identity.version,
                one.content_digest,
                one.signature,
                one.signed_by,
                one.signed_at,
                json.dumps(one.manifest.document()),
            )
        drafts = (
            ("00000000-0000-0000-0000-000000000001", first, ()),
            ("00000000-0000-0000-0000-000000000002", second, ("u_approver",)),
        )
        for draft_id, one, approvers in drafts:
            sql(
                url,
                "INSERT INTO agent.manifest_draft (id, agent_id, kind, owner_id) VALUES"
                " (%s, %s, 'new', %s)",
                draft_id,
                AGENT,
                one.signed_by,
            )
            sql(
                url,
                "INSERT INTO agent.manifest_revision (draft_id, number, body, saved_by)"
                " VALUES (%s, 1, '{}'::jsonb, %s)",
                draft_id,
                one.signed_by,
            )
            for act, actor in (
                ("published", one.signed_by),
                *(("approved", approver) for approver in approvers),
            ):
                sql(
                    url,
                    "INSERT INTO agent.manifest_act (draft_id, revision, act, actor_id, at)"
                    " VALUES (%s, 1, %s, %s, %s)",
                    draft_id,
                    act,
                    actor,
                    one.signed_at,
                )

        async def read() -> Any:
            engine = make_app_engine(normalise_database_url(url))
            try:
                return await StoredPublications(make_session_factory(engine)).history(AGENT)
            finally:
                await engine.dispose()

        history = asyncio.run(read())

    assert len(history) == 2
    assert history[1] == expected(first, second)
