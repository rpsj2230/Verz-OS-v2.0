"""What one run of a draft costs, and when that is more than its department allows (M20.5.2).

Task ids: M20.5.2
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.agents.template import ManifestAuthority, ManifestIdentity, TemplateManifest
from brain.builder.publish import PublishedVersion, publication_history
from brain.builder.run_cost import (
    RUN_LANE,
    cost_hold,
    cost_of_document,
    rehearsed_run_cost,
    run_cost,
)
from brain.models.routing import Tier
from brain.ops.spend import CostInputs, estimate

AT = datetime(2019, 3, 4, 12, tzinfo=UTC)


def _naming(tools: int, tier: Tier) -> TemplateManifest:
    """A manifest at `tier` allowing `tools` tools, which is everything the price reads."""
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=f"priced_{tools}", version=1, published_by="system", display_name="Priced"
        ),
        persona="Answers.",
        tier=tier,
        authority=ManifestAuthority(allowed_tools=tuple(f"thing{n}.read" for n in range(tools))),
    )


MANY = _naming(5, Tier.MAIN)
FEW = _naming(1, Tier.MAIN)


def test_a_run_is_priced_by_the_estimator_a_real_run_is_admitted_by() -> None:
    """The figure is `brain.ops.spend.estimate` over the agent's tier and tool count, in the lane a
    person waits in, with nothing of this module's own in it.

    Delete this and the cost shown is a second cost model that disagrees with the pre-flight by
    whatever its author chose."""
    priced = run_cost(Tier.MAIN, 3)

    assert priced == estimate(CostInputs(lane=RUN_LANE, tier=Tier.MAIN, tool_calls=3))


def test_a_run_that_may_call_more_tools_costs_more_and_a_cheaper_tier_costs_less() -> None:
    """The two inputs the gate prices: tools allowed, and the tier the agent answers at.

    Delete this and an agent can be given more tools or a dearer model with the cost standing
    still, which is a hold that never fires."""
    assert run_cost(Tier.MAIN, 5).minor > run_cost(Tier.MAIN, 1).minor
    assert run_cost(Tier.HEAVY, 2).minor > run_cost(Tier.SMALL, 2).minor


def test_a_manifests_run_is_priced_from_its_tier_and_the_tools_it_names() -> None:
    """A manifest naming five tools costs more per run than one naming one, at the same tier.

    Delete this and the figure reads something other than the manifest it is shown beside."""
    assert rehearsed_run_cost(MANY) == run_cost(MANY.tier, len(MANY.authority.allowed_tools))
    assert rehearsed_run_cost(MANY).minor > rehearsed_run_cost(FEW).minor


def test_a_stored_version_prices_at_the_same_figure_the_gate_compared() -> None:
    """The publish record reads a cost from the stored version's flat document and gets the figure
    the gate priced from the manifest, so a version shows what it was held against years later.

    Delete this and the record and the gate can price one version differently."""
    assert cost_of_document(MANY.document()) == rehearsed_run_cost(MANY).minor
    assert cost_of_document(FEW.document()) == rehearsed_run_cost(FEW).minor


@pytest.mark.parametrize(
    "document",
    [{}, {"tier": "main"}, {"tier": "enormous", "authority.allowed_tools": []}, {"tier": 3}],
)
def test_a_document_that_cannot_be_priced_has_no_cost_and_not_a_cost_of_nothing(
    document: dict[str, object],
) -> None:
    """Missing or unreadable inputs give none, because nought is a cost and an unpriced version is
    not a free one.

    Delete this and the record shows a free run for a version nobody could price."""
    assert cost_of_document(document) is None


def test_a_run_costing_more_than_the_ceiling_is_held_and_one_at_or_below_it_is_not() -> None:
    """Strictly greater holds: one over, at and under the ceiling.

    Delete this and the comparison drifts to at-or-above, holding the agent whose cost the
    department chose as its limit."""
    cost = rehearsed_run_cost(MANY).minor

    assert cost_hold(MANY, department="web", ceiling_minor=cost - 1) is not None
    assert cost_hold(MANY, department="web", ceiling_minor=cost) is None
    assert cost_hold(MANY, department="web", ceiling_minor=cost + 1) is None


def test_a_hold_names_the_department_the_cost_and_the_ceiling() -> None:
    """The hold carries the three facts a person is told, and nothing about another department.

    Delete this and the hold is a bare yes."""
    held = cost_hold(MANY, department="web", ceiling_minor=1)

    assert held is not None
    assert (held.department, held.ceiling_minor) == ("web", 1)
    assert held.cost_minor == rehearsed_run_cost(MANY).minor


def test_no_department_or_no_ceiling_is_no_hold() -> None:
    """An agent that belongs to no department has no ceiling to exceed, and a department that set
    none has said nothing about a run.

    Delete this and every publish is held on an install nobody configured, a gate people learn to
    wave through."""
    assert cost_hold(MANY, department=None, ceiling_minor=1) is None
    assert cost_hold(MANY, department="", ceiling_minor=1) is None
    assert cost_hold(MANY, department="web", ceiling_minor=None) is None


def test_the_history_carries_each_versions_cost_read_from_its_document() -> None:
    """The publish history reads a cost off every stored version, so the record shows it without a
    column beside the version, and a version with no tier shows none.

    Delete this and the record the leaf asks for shows no cost."""
    versions = [
        PublishedVersion(version=1, published_by="u_a", published_at=AT, document=MANY.document()),
        PublishedVersion(
            version=2, published_by="u_a", published_at=AT, document={"persona": "Answer."}
        ),
    ]

    history = publication_history("an_agent", versions, {})

    assert [one.cost_minor for one in history] == [rehearsed_run_cost(MANY).minor, None]
