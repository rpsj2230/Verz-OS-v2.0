"""The entity registry's acceptance checks: registered, passing on a real schema, and able to fail.

Task ids: M14.1.1, M14.1.2, M14.1.3, M14.1.4, M14.1.6, M14.2.1, M14.2.2, M14.2.3, M14.2.4
Task ids: M14.6.1, M14.7.3
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_registry"
ENTITIES = "two_records_each_become_an_entity_with_names_keys_and_link"
NAMES = "a_name_is_keyed_the_same_however_it_is_written"
BLOCKED = "a_join_key_this_install_blocks_is_never_kept"
CLEAR = "no_registry_table_holds_a_join_key_in_the_clear"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_registry_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in page order. Delete this and a check can drop out of
    the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [ENTITIES, NAMES, BLOCKED, CLEAR]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_registry_checks_pass_and_nothing_is_left_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Delete this and the
    registry can stop writing entities with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_registry") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {
        ENTITIES: (PASSED, ""),
        NAMES: (PASSED, ""),
        BLOCKED: (PASSED, ""),
        CLEAR: (PASSED, ""),
    }
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, name: str, label: str, setup: Any) -> Any:
    """Apply one break, run one check against PostgreSQL at head, and return its outcome."""
    setup(monkeypatch)
    with at_head(f"brain_acceptance_registry_{label}") as url:
        outcome = run_checks(url, (mine()[name],))
    return outcome[name]


def _wrong_type(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store
    from brain.resolution.canonical import CanonicalEntity, EntityType

    kept = CanonicalEntity

    def as_a_person(**fields: Any) -> Any:
        return kept(**{**fields, "entity_type": EntityType.PERSON})

    monkeypatch.setattr(store, "CanonicalEntity", as_a_person)


def _local_id_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store

    monkeypatch.setattr(store, "update", lambda table: _Inert())


class _Inert:
    """An UPDATE that changes nothing, for a break that leaves `local_id` empty."""

    def where(self, *args: Any) -> Any:
        from sqlalchemy import text

        return _Values(text("SELECT 1"))


class _Values:
    def __init__(self, statement: Any) -> None:
        self.statement = statement

    def values(self, **values: Any) -> Any:
        return self.statement


def _alias_folded(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store
    from brain.resolution.canonical import Alias

    kept = Alias

    def folded(**fields: Any) -> Any:
        return kept(**{**fields, "name": str(fields["name"]).lower()})

    monkeypatch.setattr(store, "Alias", folded)


def _key_of_another_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store
    from brain.resolution.canonical import Identifier, IdentifierKind

    kept = Identifier

    def as_a_uen(**fields: Any) -> Any:
        return kept(**{**fields, "kind": IdentifierKind.UEN})

    monkeypatch.setattr(store, "Identifier", as_a_uen)


def _view_unforwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.ops.acceptance_checks_registry as module

    kept = module._one

    async def misread(h: Any, sql: str, ref: Any) -> Any:
        if "er.resolved_alias" in sql:
            return [("ent_nothing",)]
        return await kept(h, sql, ref)

    monkeypatch.setattr(module, "_one", misread)


def _unfolded(name: str) -> Any:
    def setup(monkeypatch: pytest.MonkeyPatch) -> None:
        import brain.resolution.entities as entities
        from brain.resolution.normalise import NameVerdict, NormalisedName
        from brain.resolution.normalise import normalise_name as kept

        def raw(observed: str) -> NormalisedName:
            made = kept(observed)
            key = {
                "case": observed.strip(),
                "punctuation": " ".join(observed.lower().split()),
                "suffix": " ".join(observed.lower().replace(",", "").replace(".", "").split()),
                "accent": made.key.replace("cafe", "café") if "é" in observed else made.key,
            }[name]
            return NormalisedName(
                observed=made.observed,
                collapsed=made.collapsed,
                key=key,
                removed=made.removed,
                verdict=NameVerdict.USABLE,
                fold=made.fold,
                reason=made.reason,
            )

        monkeypatch.setattr(entities, "normalise_name", raw)

    return setup


def _blocks_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store

    monkeypatch.setattr(store, "without_blocked", lambda observation, blocked: (observation, 0))


def _blocks_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution.registry_store as store
    from brain.resolution.cascade import Observation

    def none_kept(observation: Any, blocked: Any) -> Any:
        return (
            Observation(record=observation.record, name=observation.name),
            len(observation.identifiers),
        )

    monkeypatch.setattr(store, "without_blocked", none_kept)


def _domain_in_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.connectors.resolves import ResolvesAs

    kept = ResolvesAs.renamed

    def with_the_domain(self: ResolvesAs, fields: Any) -> Any:
        renamed = kept(self, fields)
        return {**renamed, "name": f"{renamed['name']} {fields.get('domain', '')}"}

    monkeypatch.setattr(ResolvesAs, "renamed", with_the_domain)


BREAKS: dict[str, tuple[str, Any, str]] = {
    "wrong_type": (ENTITIES, _wrong_type, "NOT_AN_ENTITY"),
    "local_id_untouched": (ENTITIES, _local_id_untouched, "NOT_LINKED"),
    "alias_folded": (ENTITIES, _alias_folded, "NO_ALIAS"),
    "key_of_another_kind": (ENTITIES, _key_of_another_kind, "NO_KEY"),
    "view_unforwarded": (ENTITIES, _view_unforwarded, "NOT_RESOLVED"),
    "case_kept": (NAMES, _unfolded("case"), "NOT_FOLDED"),
    "punctuation_kept": (NAMES, _unfolded("punctuation"), "PUNCTUATION_KEPT"),
    "suffix_kept": (NAMES, _unfolded("suffix"), "SUFFIX_KEPT"),
    "accent_kept": (NAMES, _unfolded("accent"), "ACCENT_KEPT"),
    "blocks_ignored": (BLOCKED, _blocks_ignored, "BLOCK_IGNORED"),
    "blocks_everything": (BLOCKED, _blocks_everything, "BLOCK_TOO_WIDE"),
    "domain_in_a_name": (CLEAR, _domain_in_a_name, "IN_THE_CLEAR"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_registry_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing its check with its own sentence: an entity of the
    wrong type, a record whose local id is never set, an alias that is not the observed name,
    a key of another kind, a resolved view that names another entity (M14.1.1 to M14.1.6); a
    name keyed apart by case, punctuation, a legal form or an accent (M14.2.1 to M14.2.4); a
    blocklist that blocks nothing or everything (M14.6.1); and a join key's value written beside
    a name (M14.7.3). Delete this and any of these checks can pass with its
    property gone."""
    import brain.ops.acceptance_checks_registry as module

    name, setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, name, broken, setup) == (FAILED, getattr(module, reason))
