"""Which rungs of the ladder can be called now, and the reason each of the others says.

Task ids: M27.8.8, M5.1.2
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.install import value_of
from brain.models.adapter import Completion, SdkDriver
from brain.models.assembly import (
    HOSTED_PROFILE,
    LOCAL_PROFILE,
    MODEL_PROFILES,
    TOLD,
    LadderRung,
    RungSkip,
    assemble,
    local_only,
    skip_reason,
)
from brain.models.driver import DriverRequest, ModelDriver
from brain.models.routing import (
    NoCompliantRoute,
    ResidencyClass,
    ResidencyRequirement,
    SkipReason,
    Tier,
)
from brain.models.wire import LOCAL_PROVIDER
from brain.setup_wizard import LOCAL_ONLY
from brain.setup_wizard import MODEL_PROFILES as WIZARD_PROFILES


def _answer(request: DriverRequest) -> Completion:
    return Completion(text="ok", finish_reason="stop")


def drivers(*providers: str) -> dict[str, ModelDriver]:
    return {one: SdkDriver(provider=one, transport=_answer) for one in providers}


def rung(
    provider: str = "anthropic",
    *,
    tier: Tier = Tier.MAIN,
    position: int = 0,
    enabled: bool = True,
) -> LadderRung:
    return LadderRung(
        rung_id=f"00000000-0000-0000-0000-{position:012d}",
        tier=tier,
        position=position,
        deployment_id=f"{provider}-{tier.value}-{position}",
        provider=provider,
        model=f"{provider}-model",
        attempts=1,
        timeout_seconds=12.0,
        max_concurrency=4,
        enabled=enabled,
    )


def reason(one: LadderRung, **overrides: object) -> RungSkip | None:
    arguments: dict[str, object] = {
        "profile": HOSTED_PROFILE,
        "switched_off": frozenset(),
        "held": frozenset({"anthropic", "openai", "moonshot"}),
        "drivers": drivers("anthropic", "openai", "moonshot", LOCAL_PROVIDER),
    }
    arguments.update(overrides)
    return skip_reason(one, **arguments)  # type: ignore[arg-type]


def test_the_profiles_are_the_wizards_and_the_install_default_keeps_text_local() -> None:
    """Held against the setup wizard's own list and the declared default rather than against
    this module's constants, so a renamed profile fails here.

    Delete this and `hosted` can be spelled differently in two places, and every install that
    chose it in the wizard reads as local and answers nothing."""
    assert MODEL_PROFILES == WIZARD_PROFILES
    assert LOCAL_PROFILE == LOCAL_ONLY
    assert value_of("INSTALL_MODEL_PROFILE", env={}, saved={}) == LOCAL_PROFILE
    assert local_only(value_of("INSTALL_MODEL_PROFILE", env={}, saved={}))


def test_a_hosted_rung_answers_on_a_hosted_install_that_holds_its_key_and_has_it_switched_on() -> (
    None
):
    """The positive case every refusal below is a sibling of. Delete this and an assembly that
    leaves every rung out passes all of them."""
    assert reason(rung("anthropic")) is None
    assert reason(rung(LOCAL_PROVIDER)) is None


def test_a_local_profile_keeps_every_hosted_rung_out_and_anything_unrecognised_is_local() -> None:
    """The profile is the decision to let text leave the client's hardware at all. Delete this
    and an install that never chose to send text anywhere sends it to the first hosted rung."""
    for profile in (LOCAL_PROFILE, "", "Hosted", "hosted-please", "cloud"):
        assert reason(rung("anthropic"), profile=profile) is RungSkip.LOCAL_PROFILE
        assert reason(rung(LOCAL_PROVIDER), profile=profile) is None
    assert reason(rung("anthropic"), profile=" hosted ") is None


def test_a_switched_off_provider_is_left_out_and_nobody_else_is() -> None:
    """Delete this and the Models screen's switch is a row nothing reads."""
    off = frozenset({"anthropic"})
    assert reason(rung("anthropic"), switched_off=off) is RungSkip.SWITCHED_OFF
    assert reason(rung("openai"), switched_off=off) is None


def test_a_hosted_provider_with_no_key_held_is_left_out_and_the_local_server_needs_none() -> None:
    """Delete this and a keyless rung reaches the chain and fails as an authentication error on
    somebody's question, which is the failure `seed_chain` names."""
    assert reason(rung("moonshot"), held=frozenset({"anthropic"})) is RungSkip.NO_KEY
    assert reason(rung(LOCAL_PROVIDER), held=frozenset()) is None


def test_a_provider_with_no_driver_is_told_which_of_the_two_things_is_missing() -> None:
    """A hosted provider this product has no transport for, and the local server with no usable
    address, are two different things to fix. Delete this and both read the same."""
    none = drivers()
    assert reason(rung("somebody_else"), drivers=none) is RungSkip.NO_TRANSPORT
    assert reason(rung(LOCAL_PROVIDER), drivers=none) is RungSkip.NO_INFERENCE_SERVER


def test_the_reasons_are_judged_in_the_order_of_consent() -> None:
    """A rung failing every test is told the first. Delete this and a local install is told to
    put a key in for a provider its profile forbids, which is the wrong thing to do first."""
    everything_wrong = {
        "profile": LOCAL_PROFILE,
        "switched_off": frozenset({"anthropic"}),
        "held": frozenset(),
        "drivers": drivers(),
    }
    assert reason(rung("anthropic"), **everything_wrong) is RungSkip.LOCAL_PROFILE
    everything_wrong["profile"] = HOSTED_PROFILE
    assert reason(rung("anthropic"), **everything_wrong) is RungSkip.SWITCHED_OFF
    everything_wrong["switched_off"] = frozenset()
    assert reason(rung("anthropic"), **everything_wrong) is RungSkip.NO_TRANSPORT
    everything_wrong["drivers"] = drivers("anthropic")
    assert reason(rung("anthropic"), **everything_wrong) is RungSkip.NO_KEY


def test_every_reason_has_a_sentence_saying_what_to_do() -> None:
    """Delete this and a reason added to the enum reaches the screen as a KeyError."""
    assert set(TOLD) == set(RungSkip)
    assert all(len(one.split()) >= 8 for one in TOLD.values())


def test_assembly_splits_the_ladder_and_keeps_a_disabled_rung_for_the_chain_to_skip() -> None:
    """A disabled rung is the chain's to skip as disabled, so positions stay the edited ladder's.

    Delete this and a disabled rung can be reported as left out for a reason that is not true,
    or the answering chain can lose it and renumber what the attempt rows reconstruct."""
    ladder = (
        rung("anthropic", position=0, enabled=False),
        rung("moonshot", position=1),
        rung("openai", position=2),
    )
    built = assemble(
        ladder,
        profile=HOSTED_PROFILE,
        switched_off=frozenset(),
        held=frozenset({"anthropic", "openai"}),
        drivers=drivers("anthropic", "openai", "moonshot"),
    )

    assert [one.provider for one in built.answering] == ["anthropic", "openai"]
    assert [(one.rung.provider, one.reason) for one in built.skipped] == [
        ("moonshot", RungSkip.NO_KEY)
    ]
    selection = built.chain.select(Tier.MAIN)
    assert [one.deployment.provider for one in selection.rungs] == ["openai"]
    assert [one.reason for one in selection.skipped] == [SkipReason.DISABLED]
    assert [one.deployment.provider for one in built.for_provider("openai").rungs] == ["openai"]
    assert built.rung("openai-main-2", Tier.MAIN).rung_id.endswith("2")
    with pytest.raises(ValueError, match="not an answering rung"):
        built.rung("openai-main-2", Tier.HEAVY)


def test_an_assembled_rung_promises_no_residency_so_a_constrained_request_is_refused() -> None:
    """The rows record no region, so no assembled rung can satisfy a residency constraint.

    Delete this and a rung built as region-pinned from a row that says nothing about a region
    carries a regulated question somewhere nobody documented."""
    built = assemble(
        (rung("anthropic"),),
        profile=HOSTED_PROFILE,
        switched_off=frozenset(),
        held=frozenset({"anthropic"}),
        drivers=drivers("anthropic"),
    )
    (only,) = built.chain.rungs
    assert only.deployment.residency_class is ResidencyClass.GLOBAL

    constrained = ResidencyRequirement(allowed_regions=frozenset({"eu-west-1"}))
    with pytest.raises(NoCompliantRoute):
        built.chain.select(Tier.MAIN, residency=constrained).require()
    assert built.chain.select(Tier.MAIN, now=datetime(2019, 1, 1, tzinfo=UTC)).rungs == (only,)
