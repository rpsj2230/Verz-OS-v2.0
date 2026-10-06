"""The agent builder's acceptance checks: registered, passing on a real schema, and able to fail.

Task ids: M13.2.7, M13.1.1, M13.2.4, M20.1.5, M20.2.2, M20.2.3, M20.2.4, M20.1.2, M13.9.4, M13.8.18
Task ids: M20.4.6
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_builder"
HAND_BUILT = "a_hand_built_agent_takes_the_template_path_and_records_setters"
CANVAS = "an_authored_list_is_intent_and_the_canvas_draws_five_kinds_only"
GALLERY = "the_form_is_the_manifest_and_a_template_installs_in_one_press"
HISTORY = "a_second_publish_is_recorded_with_exactly_the_paths_it_changed"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_builder_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in page order. Delete this and a check can drop out of
    the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [HAND_BUILT, CANVAS, GALLERY, HISTORY]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_builder_checks_pass_and_nothing_is_left_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Delete this and the
    builder can stop making agents with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_builder") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {
        HAND_BUILT: (PASSED, ""),
        CANVAS: (PASSED, ""),
        GALLERY: (PASSED, ""),
        HISTORY: (PASSED, ""),
    }
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, name: str, label: str, setup: Any) -> Any:
    """Apply one break, run one check against PostgreSQL at head, and return its outcome."""
    setup(monkeypatch)
    with at_head(f"brain_acceptance_builder_{label}") as url:
        outcome = run_checks(url, (mine()[name],))
    return outcome[name]


def _start_from_a_template(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.agents.catalogue import business_analyst
    from brain.builder.agent_drafts import seed as seed_of

    monkeypatch.setattr(
        routes, "blank_seed", lambda agent_id: seed_of(business_analyst(), agent_id)
    )


def _signed_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    kept = routes._signed

    def elsewhere(revision: Any, *, agent_id: str, **rest: Any) -> Any:
        return kept(revision, agent_id=f"{agent_id}_elsewhere", **rest)

    monkeypatch.setattr(routes, "_signed", elsewhere)


def _row_without_its_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.draft_store as draft_store
    from brain.agents.install_store import agent_values as kept

    monkeypatch.setattr(
        draft_store, "agent_values", lambda record: {**kept(record), "persona": "Something else."}
    )


def _setter_unrecorded(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.prompt_routes as routes
    from brain.agents.template import set_field as kept

    def anonymous(instance: Any, path: str, value: Any, *, by: str, at: Any) -> Any:
        del by
        return kept(instance, path, value, by="u_somebody_else", at=at)

    monkeypatch.setattr(routes, "set_field", anonymous)


def _setter_of_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.prompt_routes as routes
    from brain.agents.template import set_field as kept

    def everything(instance: Any, path: str, value: Any, *, by: str, at: Any) -> Any:
        widened = kept(instance, path, value, by=by, at=at)
        return kept(widened, "identity.summary", "", by=by, at=at)

    monkeypatch.setattr(routes, "set_field", everything)


def _publish_on_a_word(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "second_people_needed", lambda *args, **kwargs: 0)


def _skill_without_its_call(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.procedure import skill_markdown as kept

    monkeypatch.setattr(
        routes,
        "skill_markdown",
        lambda *args, **kwargs: kept(*args, **kwargs).replace("call `", "use `"),
    )


def _lenient(kinds: frozenset[str], scope: bool = False) -> Any:
    """A drawing reader that drops steps of `kinds` and, if `scope`, reads any predicate as one."""

    def setup(monkeypatch: pytest.MonkeyPatch) -> None:
        import brain.agent_builder_routes as routes
        import brain.builder.procedure as procedure
        from brain.builder.procedure import read_drawing as kept
        from brain.core.scope import Clause, Op, Scope

        if scope:
            monkeypatch.setattr(
                procedure,
                "_predicate",
                lambda value, step: (
                    None
                    if value is None
                    else Scope(clauses=(Clause(field="department", op=Op.EQ, value="x"),))
                ),
            )

        def reading(payload: Any, *, drawable_tools: Any) -> Any:
            nodes = [one for one in payload["nodes"] if one.get("kind") not in kinds]
            kept_ids = {one["id"] for one in nodes}
            edges = [
                one for one in payload["edges"] if one["from"] in kept_ids and one["to"] in kept_ids
            ]
            if len(nodes) != len(payload["nodes"]):
                edges.append({"from": "start", "to": "done", "way": "next"})
            return kept({"nodes": nodes, "edges": edges}, drawable_tools=drawable_tools)

        monkeypatch.setattr(routes, "read_drawing", reading)

    return setup


def _stale_form(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.form import form_document as kept

    monkeypatch.setattr(
        routes, "form_document", lambda *a: {**kept(), "sections": kept()["sections"][:-1]}
    )


def _form_for_anybody(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "_builds", lambda asked: None)


def _renamed_on_install(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes
    from brain.agents.creation import install_draft as kept

    monkeypatch.setattr(
        routes,
        "install_draft",
        lambda signed, **rest: kept(signed, **{**rest, "display_name": "Something else"}),
    )


def _opened_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.agent_drafts import blank_seed

    monkeypatch.setattr(routes, "seed", lambda template, agent_id: blank_seed(agent_id))


def _never_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes

    monkeypatch.setattr(routes, "version_unavailable", lambda signed, key: None)


def _a_key_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.settings as settings

    class WithAKey(settings.Settings):
        template_signing_key: str = ""

    monkeypatch.setattr(settings, "Settings", WithAKey)


def _one_publish_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.publication_store as store
    from brain.builder.publish import publication_history as kept

    monkeypatch.setattr(store, "publication_history", lambda *args: kept(*args)[-1:])


def _stamps_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.publish as publish

    monkeypatch.setattr(publish, "STAMPED_PATHS", ())


def _published_by_somebody(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    import brain.builder.publication_store as store
    from brain.builder.publish import publication_history as kept

    monkeypatch.setattr(
        store,
        "publication_history",
        lambda *args: tuple(
            dataclasses.replace(one, actor_id="u_somebody_else") for one in kept(*args)
        ),
    )


BREAKS: dict[str, tuple[str, Any, str]] = {
    "one_publish_kept": (HISTORY, _one_publish_kept, "NO_HISTORY"),
    "stamps_counted": (HISTORY, _stamps_counted, "WRONG_PATHS"),
    "published_by_somebody": (HISTORY, _published_by_somebody, "NOT_WHO"),
    "from_a_template": (HAND_BUILT, _start_from_a_template, "NOT_FROM_BLANK"),
    "signed_elsewhere": (HAND_BUILT, _signed_elsewhere, "NOT_THE_TEMPLATE_PATH"),
    "row_without_persona": (HAND_BUILT, _row_without_its_persona, "ROW_INCOMPLETE"),
    "setter_unrecorded": (HAND_BUILT, _setter_unrecorded, "OWNER_NOT_RECORDED"),
    "setter_of_everything": (HAND_BUILT, _setter_of_everything, "OWNER_TOO_WIDE"),
    "publish_on_a_word": (CANVAS, _publish_on_a_word, "INTENT_PUBLISHED"),
    "skill_without_call": (CANVAS, _skill_without_its_call, "NO_SKILL"),
    "a_sixth_kind": (CANVAS, _lenient(frozenset({"loop"})), "FIVE_KINDS"),
    "a_code_step": (CANVAS, _lenient(frozenset({"code"})), "CODE_ADMITTED"),
    "any_condition": (CANVAS, _lenient(frozenset(), scope=True), "NOT_A_SCOPE"),
    "stale_form": (GALLERY, _stale_form, "NOT_THE_SCHEMA"),
    "form_for_anybody": (GALLERY, _form_for_anybody, "FORM_TO_ANYBODY"),
    "renamed_on_install": (GALLERY, _renamed_on_install, "NOT_ONE_PRESS"),
    "opened_blank": (GALLERY, _opened_blank, "NO_LONG_WAY"),
    "never_unavailable": (GALLERY, _never_unavailable, "NOT_SAID_UNAVAILABLE"),
    "a_key_setting": (GALLERY, _a_key_setting, "A_KEY_SETTING"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_builder_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing its check with its own sentence:
    a new draft that does not start blank and an agent kept off the template path (M13.2.7), a
    row that does not carry its persona (M13.1.1), an edit recorded against somebody else or
    against paths it did not touch (M13.2.4), a named capability published on the author's word
    (M20.1.5), a drawing that does not become its SKILL.md (M20.2.2), a sixth kind and a condition
    that is not a scope predicate admitted (M20.2.3), a code step admitted (M20.2.4), a form that
    is not the manifest's schema or is served to anybody (M20.1.2), a one-press install under
    another name or a template that opens blank (M13.9.4), and a gallery that never says it cannot
    install or a setting that could hold the key (M13.8.18), and a publish history that drops a
    publish, counts the publish's own stamps as changes or names another publisher (M20.4.6).
    Delete this and any of these checks can pass with its property gone."""
    import brain.ops.acceptance_checks_builder as module

    name, setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, name, broken, setup) == (FAILED, getattr(module, reason))
