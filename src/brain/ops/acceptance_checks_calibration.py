"""The weekly fit, proved on an install: the install's own candidate pairs fitted, the fit shown
to a reviewer as drift, promoted in their name, and read by the online scorer by its name.

The check plants record pairs the way a sync leaves them, registers them with the registry the
worker runs, and fits them with the weekly job's own functions (`calibration_store.extract`,
`fitted`, `keep`) over the check's own records only, so the fit does not depend on what else the
install holds. The weights routes in `brain.resolution_routes` are then called as a reviewer and as
somebody without the reviewer's capability. Everything is inside the check's transaction.

**The pairs come from a source declared for the check.** A fit needs more distinct agreement
patterns than it has parameters, and the shipped sources keep only a name and a domain, which on
a fresh install gives too few; a source that keeps a registration number, a domain, a country and
a postcode is declared for the check only, and the fit, the screen and the promote are the
product's, unchanged.

**The labelled sample is not planted.** Whether a fit agrees with the pairs people decided is read
from every decided review item on the install, which a check cannot hold still; that rule is
`tests/unit/test_calibration_store.py`'s to prove.

Task ids: M14.3.5, M14.4.2, M14.4.4, M14.8.3
"""

from __future__ import annotations

import secrets
from itertools import combinations
from types import MappingProxyType
from typing import Final

from sqlalchemy import insert, text

from brain.connectors.resolves import ResolvesAs
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_review import _app, _reader, _request
from brain.ops.acceptance_run import Harness
from brain.resolution.calibration_store import extract, fitted, keep, weights_in_force
from brain.resolution.canonical import EntityType, SourceRef
from brain.resolution.cascade import Feature
from brain.resolution.registry_store import StoredRegistry
from brain.resolution.sources import resolved_entities
from brain.tables.projection import ProjectedRecordRow

#: Where this module's check sits on the acceptance page.
CHECK_ORDER: Final = 438

#: The check-only source. See the module docstring.
SOURCE: Final = ("hubspot", "acceptance_calibration_company")
KEYS: Final = ("uen", "domain", "country", "postcode")

NOT_FITTED: Final = "the install's candidate pairs were not fitted into weights"
NO_DRIFT_SHOWN: Final = "the waiting fit was not shown to a reviewer as drift in words"
SHOWN_WITHOUT_AUTHORITY: Final = (
    "the weights were shown to somebody without the reviewer's capability"
)
NOT_PROMOTED: Final = (
    "a reviewer's promote did not put the fit in force in their name, or the scorer did not read "
    "it by its name"
)


def _declared() -> MappingProxyType[tuple[str, str], ResolvesAs]:
    return MappingProxyType(
        {
            **resolved_entities(),
            SOURCE: ResolvesAs(
                entity=SOURCE[1],
                entity_type=EntityType.COMPANY,
                fields={one: one for one in ("name", *KEYS)},
            ),
        }
    )


def _plan(word: str) -> list[dict[str, str]]:
    """Record pairs agreeing on every subset of the keys, with the same name or another one."""
    records: list[dict[str, str]] = []
    n = 0
    for size in range(len(KEYS) + 1):
        for subset in combinations(KEYS, size):
            for same_name in (True, False):
                if not same_name and not {"uen", "domain"} & set(subset):
                    continue
                n += 1
                base = {
                    "uen": f"2019{n:05d}K",
                    "domain": f"d{n}.{word.lower()}.example",
                    "country": f"c{n}x",
                    "postcode": f"p{n}x",
                }
                first = {"name": f"Northwind {word} {n:03d}"}
                second = {
                    "name": first["name"] if same_name else f"Fabrikam {n:03d} {word} Holdings"
                }
                for key in KEYS:
                    first[key] = base[key]
                    second[key] = base[key] if key in subset else f"other{n}{key}x"
                records += [first, second]
    return records


@check(
    leaves=("M14.3.5", "M14.4.2", "M14.4.4", "M14.8.3"),
    sentence=(
        "Record pairs from a source declared for the check are fitted by the weekly job into "
        "weights; a reviewer sees the fit's drift in words and promotes it in their name, "
        "somebody without the reviewer's capability is refused, and the scorer then reads it."
    ),
)
async def a_fit_is_shown_as_drift_promoted_by_name_and_scored_with(h: Harness) -> None:
    from brain.core.errors import Absent
    from brain.resolution_routes import (
        ENTITY_MERGE_CAPABILITY,
        PromoteAsked,
        promote_weights,
        weights_view,
    )

    word = h.word()
    refs = []
    for fields in _plan(word):
        source_id = f"acceptance-{h.run}-{secrets.token_hex(6)}"
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=SOURCE[0],
                entity=SOURCE[1],
                source_id=source_id,
                last_seen_at=h.now,
                fields=fields,
            ),
        )
        refs.append(SourceRef(source=SOURCE[0], entity=SOURCE[1], source_id=source_id))
    await StoredRegistry(h.sessions, declared=_declared()).register(
        refs, pepper=secrets.token_hex(32), now=h.now, by=h.actor
    )
    fit = fitted(
        await extract(h.sessions, touching=refs),
        now=h.now,
        previous=await weights_in_force(h.sessions),
    )
    if Feature.UEN not in fit.fitted or fit.weights[Feature.UEN] <= 0:
        raise CheckFailedError(NOT_FITTED)
    await keep(h.sessions, fit, by=h.actor)

    await h.found_departments()
    reviewer = await _reader(h, "weights", ENTITY_MERGE_CAPABILITY.value)
    nobody = await _reader(h, "nobody")
    app = _app(h)
    shown = await weights_view(_request(app), reviewer)
    if (
        shown.candidate != fit.version
        or not shown.lines
        or any(any(ch.isdigit() for ch in line) for line in shown.lines)
    ):
        raise CheckFailedError(NO_DRIFT_SHOWN)
    try:
        await weights_view(_request(app), nobody)
    except Absent:
        pass
    else:
        raise CheckFailedError(SHOWN_WITHOUT_AUTHORITY)

    promoted = await promote_weights(_request(app), PromoteAsked(version=fit.version), reviewer)
    reviewer_id = reviewer.caller.principal.id
    entries = await h.execute(
        text(
            "SELECT count(*) FROM obs.audit_entry WHERE action = 'setting' AND actor_id = :who"
        ).bindparams(who=reviewer_id)
    )
    scored_with = await weights_in_force(h.sessions)
    if (
        getattr(promoted, "in_force", None) != fit.version
        or entries.scalar_one() < 1
        or scored_with.calibration_ref != fit.ref
    ):
        raise CheckFailedError(NOT_PROMOTED)
