"""The weekly fit, kept and promoted: the install's own candidate pairs fitted into a weight table,
each fit kept as a setting, and the one in force named by another.

`brain.resolution.calibration` holds the arithmetic (the expectation-maximisation, the export
document, drift, the promote rule) and nothing ran it: the `resolution_calibration` control was
recorded as invoked by nothing. This is what runs it and where its result lives.

**A fit is fitted on the pairs the online scan compares.** `query.pattern_query` counts the
blocked candidate pairs of `er.observation` by which features agreed, each feature's column being
`cascade.SQL_PREDICATES` for it, so the fit measures exactly the agreements the score sums, over
the population the online path sees. A pair leaves the database as a pattern and a count and
nothing else (`calibration.PatternCount`).

**Each fit is a setting, and the one in force is named by a setting (decision (f)).** The owner
decided the weight export lives where a setting names it. The exports volume is mounted only into
the offline matcher, so a fit kept there would need a mount on every service of every compose
file, which an install running a stored compose copy does not receive from a release; the
deploy-anywhere rule refuses that. So each fit is one `ops.setting` row under `FITS_NAMESPACE`
holding `WeightExport.to_document()`, and `IN_FORCE_KEY` names the version the online scorer
loads. The volume stays the offline matcher's, for its DuckDB export. See
`A_FIT_IS_A_SETTING_ROW`.

**The weights stay off the request path.** This module imports `calibration`, and its readers are
the worker's matching run and the review screen's weights section, neither of which
`tests/invariants/test_no_ml_on_the_request_path.py` counts as the request path; that invariant
still walks the gate and the online resolution modules and finds no fitted model.

**A fit is never in force until a person promotes it, and a promote is in their name.**
`promote_fit` writes the reviewer onto the export (`calibration.promote` refuses a band-crossing
candidate with no reviewer, and every promote here names one) and moves `IN_FORCE_KEY`, in one
transaction attributed to the reviewer, so 0059's trigger puts each write on the ledger naming
them, as a merge's entry names its reviewer. Rejected: promoting a fit automatically when nothing
crosses a band. `calibration.promote` allows it, and the owner's rule for this install is that a
reviewer approves new weights; a fit that moved nothing is one press.

**Nothing here is read by the general settings routes.** Settings are read by namespace, and no
module reads `FITS_NAMESPACE` or `IN_FORCE_NAMESPACE` but this one, which is reached by the
worker's run and by `brain.resolution_routes` behind `admin:entity_merge`; a test holds that
against the source. See `ONLY_THE_REVIEWER_AND_THE_WORKER_READ_THE_FITS`.

Task ids: M14.3.5, M14.4.2, M14.4.4, M14.8.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.setting_store import put, read_namespace
from brain.resolution.calibration import (
    PatternCount,
    WeightExport,
    due,
    export,
    from_document,
    promote,
    train,
)
from brain.resolution.canonical import ResolutionError, SourceRef
from brain.resolution.cascade import DECLARED_WEIGHTS, Feature, WeightTable
from brain.resolution.query import PATTERN_PREFIX, pattern_query
from brain.tables.audit import attributed_to
from brain.tables.config import SettingType

#: Why a fit is kept as a setting row and not as a file in the exports volume.
A_FIT_IS_A_SETTING_ROW: Final = (
    "The owner decided a weight export lives where a setting names it. The exports volume is "
    "mounted only into the offline matcher, and keeping fits there would need a mount on every "
    "service of every compose file, which an install running a stored compose copy does not "
    "receive from a release. A setting row reaches every install the day it upgrades."
)

#: Why no other module reads the fits.
ONLY_THE_REVIEWER_AND_THE_WORKER_READ_THE_FITS: Final = (
    "A fit says how much each kind of agreement counts towards joining two records, and the "
    "screen that shows it is behind the reviewer's capability. The settings routes read their "
    "own namespaces by name, so the fits stay out of them as long as no other module names "
    "these two namespaces, which a test holds against the source."
)

#: Why a feature no candidate pair agrees on is carried rather than fitted.
A_FEATURE_NOTHING_AGREES_ON_IS_CARRIED_AND_NOT_FITTED: Final = (
    "A feature that never agrees on this install has no data behind it, and fitting it adds two "
    "parameters nothing constrains. Fitting every feature would make the identifiability rule "
    "refuse every install whose sources keep fewer kinds of key than the cascade compares, which "
    "is every install today. So only what agrees is fitted, and the rest keep the weight in force "
    "and are named as carried, so nobody reads a carried weight as a measured one."
)

#: Why the reviewers' decisions can stop a fit being kept.
A_FIT_THE_REVIEWERS_DISAGREE_WITH_IS_NOT_KEPT: Final = (
    "The pairs people merged and kept apart are this install's labelled sample. A fit that ranks "
    "the pairs people kept apart above the ones they merged has learnt the opposite of what the "
    "people who know these clients decided, however well it converged, so it is not kept and the "
    "weights in force stay."
)

#: Every fit, one row each, keyed by its version.
FITS_NAMESPACE: Final = "resolution_fits"
#: The version the online scorer loads. Absent means the declared weights.
IN_FORCE_NAMESPACE: Final = "resolution_weights"
IN_FORCE_KEY: Final = f"{IN_FORCE_NAMESPACE}.in_force"

#: Who the weekly fit is attributed to: a job, in the ledger's identifier grammar.
CALIBRATION_ACTOR: Final = "job.resolution_calibration"
#: The reach a job's writes are attributed at: none.
JOB_REACH: Final = "0" * 32

#: A settings row's description is the product's sentence for it.
FIT_DESCRIPTION: Final = (
    "A fitted weight table for entity resolution, kept until a person promotes it."
)
IN_FORCE_DESCRIPTION: Final = "Which fitted weight table entity resolution scores with."

#: What a run says when the last fit is under a week old.
NOT_DUE: Final = "the last fit is less than a week old, so nothing was fitted"
#: What a run says when it kept a fit.
KEPT: Final = "a new fit is kept and waits for a reviewer to promote it"


def version_at(now: datetime) -> str:
    """A fit's version and reference: the job and the instant, in the reference grammar."""
    return f"fit_{now:%Y%m%dt%H%M%S}"


def _instant_of(version: str, fallback: datetime) -> datetime:
    """When a fit was made, read off its version."""
    try:
        made = datetime.strptime(version, "fit_%Y%m%dt%H%M%S")
    except ValueError:
        return fallback
    return made.replace(tzinfo=fallback.tzinfo)


def _key(version: str) -> str:
    return f"{FITS_NAMESPACE}.{version}"


async def extract(
    sessions: async_sessionmaker[AsyncSession], *, touching: Sequence[SourceRef] = ()
) -> tuple[PatternCount, ...]:
    """The candidate pairs' agreement patterns and how many showed each (M14.4.2)."""
    query = pattern_query(table="er.observation", touching=touching)
    async with sessions() as session:
        rows = (await session.execute(text(query.sql), dict(query.params))).mappings().all()
    return tuple(
        PatternCount(
            pattern=frozenset(one for one in query.features if row[f"{PATTERN_PREFIX}{one.value}"]),
            pairs=int(row["pairs"]),
        )
        for row in rows
    )


def fitted(counts: Sequence[PatternCount], *, now: datetime, previous: WeightTable) -> WeightExport:
    """The patterns fitted and exported, or `calibration`'s refusal of a fit it would not stand
    behind: too few patterns, not converged, or labels inverted.

    **Only the features some candidate pair agreed on are fitted**, and the rest carry the weight
    in force and are named as carried (`WeightExport.fitted`). A feature no pair on this install
    ever agrees on, a registration number where no source keeps one, has no data to fit: asking
    the fit for it adds two parameters nothing constrains, and the identifiability rule would then
    refuse every install whose sources keep fewer kinds of key than the cascade can compare. See
    `A_FEATURE_NOTHING_AGREES_ON_IS_CARRIED_AND_NOT_FITTED`.
    """
    present = tuple(sorted({one for row in counts for one in row.pattern}, key=str))
    if not present:
        msg = "no candidate pair agreed on anything, so there is nothing to fit"
        raise ResolutionError(msg)
    version = version_at(now)
    measured = export(train(counts, features=present), ref=version, version=version)
    weights = {one: previous.weight_for(one) for one in Feature}
    weights.update(measured.weights)
    return WeightExport(
        ref=version,
        version=version,
        weights=MappingProxyType(weights),
        pairs=measured.pairs,
        iterations=measured.iterations,
        fitted=frozenset() if len(present) == len(Feature) else frozenset(present),
    )


async def _attribute(session: AsyncSession, actor: str, ent_hash: str, trace_id: str) -> None:
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


async def keep(
    sessions: async_sessionmaker[AsyncSession],
    fit: WeightExport,
    *,
    by: str = CALIBRATION_ACTOR,
    trace_id: str = "resolution-calibration",
) -> None:
    """Keep one fit as its setting row. It is not in force until somebody promotes it."""
    async with sessions() as session, session.begin():
        await _attribute(session, by, JOB_REACH, trace_id)
        await put(
            session,
            _key(fit.version),
            value_type=SettingType.JSON,
            value=fit.to_document(),
            description=FIT_DESCRIPTION,
            updated_by=by,
        )


async def kept_fits(sessions: async_sessionmaker[AsyncSession]) -> dict[str, WeightExport]:
    """Every fit kept, by version."""
    async with sessions() as session:
        states = await read_namespace(session, FITS_NAMESPACE)
    found = {}
    for state in states.values():
        one = from_document(state.value)
        found[one.version] = one
    return found


async def in_force_version(sessions: async_sessionmaker[AsyncSession]) -> str | None:
    """The version the scorer loads, or None while the declared weights are in force."""
    async with sessions() as session:
        states = await read_namespace(session, IN_FORCE_NAMESPACE)
    state = states.get(IN_FORCE_KEY)
    return None if state is None else str(state.value)


async def weights_in_force(sessions: async_sessionmaker[AsyncSession]) -> WeightTable:
    """The table the online scorer sums: the promoted fit, or the declared weights."""
    version = await in_force_version(sessions)
    if version is None:
        return DECLARED_WEIGHTS
    fit = (await kept_fits(sessions)).get(version)
    if fit is None:
        msg = (
            f"the weights in force name {version!r} and no fit by that version is kept, so the "
            "scorer would sum a table nobody can read; the run stops rather than guessing"
        )
        raise ResolutionError(msg)
    return fit.to_weight_table()


async def candidate(sessions: async_sessionmaker[AsyncSession]) -> WeightExport | None:
    """The newest fit made after the one in force, which is what a reviewer is asked about.

    Versions sort in the order they were made, so a fit older than the one in force is history
    rather than a candidate, and None means there is nothing new to review.
    """
    fits = await kept_fits(sessions)
    current = await in_force_version(sessions)
    newer = sorted(one for one in fits if current is None or one > current)
    return fits[newer[-1]] if newer else None


async def promote_fit(
    sessions: async_sessionmaker[AsyncSession],
    version: str,
    *,
    reviewer_id: str,
    ent_hash: str,
    trace_id: str,
) -> WeightTable:
    """Put one kept fit in force on a reviewer's word, in one transaction in their name."""
    fit = (await kept_fits(sessions)).get(version)
    if fit is None:
        msg = f"no fit by version {version!r} is kept"
        raise ResolutionError(msg)
    reviewed = replace(fit, reviewed_by=reviewer_id)
    table = promote(await weights_in_force(sessions), reviewed)
    async with sessions() as session, session.begin():
        await _attribute(session, reviewer_id, ent_hash, trace_id)
        await put(
            session,
            _key(version),
            value_type=SettingType.JSON,
            value=reviewed.to_document(),
            description=FIT_DESCRIPTION,
            updated_by=reviewer_id,
        )
        await put(
            session,
            IN_FORCE_KEY,
            value_type=SettingType.STRING,
            value=version,
            description=IN_FORCE_DESCRIPTION,
            updated_by=reviewer_id,
        )
    return table


async def labelled(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[tuple[frozenset[Feature], bool], ...]:
    """The pairs reviewers decided, each as the features that agreed and whether it was merged.

    The agreements are read off the item's own evidence, where a positive weight is a feature
    that agreed, so the labelled sample is the evidence the reviewer was shown.
    """
    from sqlalchemy import select

    from brain.tables.resolution_review import ReviewItemRow, ReviewState

    async with sessions() as session:
        rows = (
            await session.execute(
                select(ReviewItemRow.state, ReviewItemRow.evidence).where(
                    ReviewItemRow.state != ReviewState.OPEN.value
                )
            )
        ).all()
    return tuple(
        (
            frozenset(Feature(one["field"]) for one in evidence if float(one["weight"]) > 0),
            state == ReviewState.MERGED.value,
        )
        for state, evidence in rows
    )


def agrees_with_reviewers(
    fit: WeightExport, sample: Sequence[tuple[frozenset[Feature], bool]]
) -> bool | None:
    """Whether the fit ranks the pairs people merged above the pairs they kept apart (M14.8.3).

    Every merged pair against every rejected one: the fit agrees when more of those comparisons
    score the merged pair higher than lower. None when people have not yet decided both ways,
    because a sample with one label cannot say anything about ranking. See
    `A_FIT_THE_REVIEWERS_DISAGREE_WITH_IS_NOT_KEPT`.
    """
    merged = [sum(fit.weights[one] for one in pattern) for pattern, was in sample if was]
    apart = [sum(fit.weights[one] for one in pattern) for pattern, was in sample if not was]
    if not merged or not apart:
        return None
    above = sum(1 for one in merged for other in apart if one > other)
    below = sum(1 for one in merged for other in apart if one < other)
    return above >= below


@dataclass(frozen=True)
class Calibrated:
    """What one weekly run did, in words. Never a figure about a pair."""

    said: str

    def summary(self) -> str:
        return self.said


async def calibrate(sessions: async_sessionmaker[AsyncSession], *, now: datetime) -> Calibrated:
    """One weekly run: fit the install's candidate pairs and keep the fit, unless one is recent.

    A fit `calibration` refuses is reported in its own words and nothing is kept: a small install
    has too few candidate pairs to identify the model, and saying so is the answer.
    """
    fits = await kept_fits(sessions)
    if fits and not due(_instant_of(max(fits), now), now):
        return Calibrated(NOT_DUE)
    try:
        fit = fitted(await extract(sessions), now=now, previous=await weights_in_force(sessions))
    except ResolutionError as refused:
        return Calibrated(f"no fit was kept: {refused}")
    if agrees_with_reviewers(fit, await labelled(sessions)) is False:
        return Calibrated(f"no fit was kept: {A_FIT_THE_REVIEWERS_DISAGREE_WITH_IS_NOT_KEPT}")
    await keep(sessions, fit)
    return Calibrated(KEPT)


def run_calibration_now(
    database_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> Calibrated:
    """`calibrate`, from a thread with no event loop of its own, as the worker's login."""
    from brain.session import make_app_engine, make_session_factory

    async def once() -> Calibrated:
        engine = make_app_engine(database_url)
        try:
            return await calibrate(make_session_factory(engine), now=now)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)
