"""The install checks for a template draft, a template's schema and overview, and an agent offered
beyond its level, each passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.8.15, M13.8.17, M13.8.19
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_templates_audience"
DRAFT = "a_template_draft_is_installable_only_once_its_author_publishes"
SCHEMA = "a_template_keeps_its_schema_and_its_overview_is_for_people"
OFFERED = "an_agent_offered_beyond_its_level_is_found_and_reaches_no_more"
WRITTEN = (
    "agent.template_draft",
    "agent.audience_extra",
    "agent.template_version",
    "agent.template_instance",
    "agent.agent",
)


def test_the_module_declares_one_check_per_leaf() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (DRAFT, ("M13.8.15", "M27.11.7")),
        (SCHEMA, ("M13.8.17",)),
        (OFFERED, ("M13.8.19",)),
    ]
    assert checks_in(MODULE) == [DRAFT, SCHEMA, OFFERED]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_templates_audience") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and no draft, version, offer or agent is
    left. Delete this and a check that can never pass on a real schema, or that leaves a published
    template on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_draft_published_with_items_undecided_fails_the_draft_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publish gate removed. Delete this and M13.8.15 closes on a template that leaves the
    install with values nobody decided about."""
    from brain.agents import authoring, template_draft_store

    real = authoring.publish_authored
    monkeypatch.setattr(
        template_draft_store,
        "publish_authored",
        lambda draft, **kwargs: real(_decided_anyway(draft), **kwargs),
    )
    assert "undecided" in _failed(install, DRAFT)


def _decided_anyway(draft: Any) -> Any:
    from datetime import UTC, datetime

    from brain.agents.authoring import AuthoredDraft, Decision, Disposition

    one = Decision(disposition=Disposition.ACCEPT, by=draft.author_id, at=datetime.now(UTC))
    return AuthoredDraft(
        author_id=draft.author_id,
        manifest=draft.manifest,
        decisions={item.item_id: one for item in draft.report.items},
    )


@pytest.mark.needs_db
def test_a_draft_anybody_may_read_fails_the_draft_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The author-only read removed. Delete this and M13.8.15 closes on drafts any colleague can
    open before anybody has looked for what is in them."""
    from brain.agents import template_draft_store
    from brain.tables.template_draft import TemplateDraftRow

    async def anybody(session: Any, draft_id: Any, by: str, **_lock: Any) -> Any:
        return await session.get(TemplateDraftRow, draft_id)

    monkeypatch.setattr(template_draft_store, "_row", anybody)
    assert "somebody other than its author" in _failed(install, DRAFT)


@pytest.mark.needs_db
def test_a_second_schema_that_does_not_sign_its_overview_fails_the_schema_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The overview left out of the digest. Delete this and M13.8.17 closes on an overview anybody
    can repoint on a published template."""
    from brain.agents import template

    real = template.content_digest

    def ignoring(manifest: Any, *, schema_version: int = 1, overview_path: str = "") -> str:
        return real(manifest, schema_version=schema_version, overview_path="")

    monkeypatch.setattr(template, "content_digest", ignoring)
    outcome, _ = run_module(install, SCHEMA)[SCHEMA]
    assert outcome == FAILED


@pytest.mark.needs_db
def test_an_offer_that_widens_the_audience_predicate_fails_the_offered_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`audience_scope` reading the added departments. Delete this and M13.8.19 closes on an offer
    that quietly becomes a narrowing predicate for the run."""
    from brain.agents import model

    real = model.audience_scope

    def widened(audience: Any) -> Any:
        from brain.core.scope import Clause, Op, Scope

        base = real(audience)
        if not audience.extra_departments:
            return base
        return Scope(
            clauses=(
                *base.clauses,
                Clause(field="department", op=Op.EQ, value=audience.extra_departments[0]),
            )
        )

    monkeypatch.setattr(model, "audience_scope", widened)
    assert "predicate" in _failed(install, OFFERED)
