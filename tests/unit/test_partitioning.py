"""The metadata ledger's partition scheme is derived, and these are the derivations (M36.1.1.2,
M36.1.1.3).

Every number in `brain.ops.partitioning` comes from somewhere else, and the whole value of the
module is that a reader can follow each one back. These tests are that path made executable:
the interval against the allowance, the allowance against the backup window, the settling
window against what the interval left, the premake against a restore, and the control column
against the row `brain.ops.telemetry` actually produces.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.partitioning import (
    CONTROL_COLUMN,
    HORIZON_RESOLUTION_DAYS,
    LEDGER_PARTMAN_SETTINGS,
    LEDGER_SPEC,
    MAX_OVER_RETENTION_DAYS,
    PARTITION_INTERVAL,
    PREMAKE,
    REMOVAL,
    SETTLE_DAYS,
    Interval,
    PartitioningError,
    PartitionSpec,
    Removal,
    interval_refusals,
    largest_safe_interval,
    longest_days,
    over_retention_days,
    partitions_over_the_window,
    partman_interval,
    partman_settings,
    premake_for,
    shortest_days,
    spec_gaps,
)
from brain.ops.retention import BACKUP_RETENTION_DAYS, DataClass
from brain.ops.telemetry import (
    LEDGER_RETENTION_DAYS,
    Ingress,
    RequestStatus,
    RequestTelemetry,
)


def _ledger_row() -> dict[str, object]:
    """A real ledger row, built through `RequestTelemetry` rather than typed out here.

    A dictionary written in this file would agree with whatever the control column happens to
    say, which is the trap CLAUDE.md records about tests satisfied by their own docstrings. The
    row has to come from the producer.
    """
    record = RequestTelemetry(
        ingress=Ingress(
            trace_id="a" * 32,
            traffic_class=TrafficClass.HUMAN_INTERACTIVE,
            received_at=datetime(2026, 9, 8, tzinfo=UTC),
        ),
        principal="staff-1",
        entitlement_hash="b" * 32,
        lane=Lane.ANSWER,
        cache_hit=False,
        status=RequestStatus.ANSWERED,
    )
    return dict(record.ledger_row())


def _spec(**overrides: object) -> PartitionSpec:
    """The declared spec with fields replaced, so a test changes one thing and not six."""
    base: dict[str, object] = {
        "data_class": LEDGER_SPEC.data_class,
        "control": LEDGER_SPEC.control,
        "interval": LEDGER_SPEC.interval,
        "premake": LEDGER_SPEC.premake,
        "settle_days": LEDGER_SPEC.settle_days,
        "removal": LEDGER_SPEC.removal,
        "because": LEDGER_SPEC.because,
    }
    base.update(overrides)
    return PartitionSpec(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------------ the allowance
def test_the_over_retention_allowance_is_the_backup_window_and_not_a_figure_of_its_own():
    """Delete this and `MAX_OVER_RETENTION_DAYS` becomes a number somebody chose, which is the
    one thing this module exists to prevent. Asserted against the other module's value so a
    change to either side fails here rather than drifting quietly."""
    assert MAX_OVER_RETENTION_DAYS == BACKUP_RETENTION_DAYS


def test_over_retention_is_one_day_less_than_the_longest_a_period_can_be():
    """Delete this and the cost of a coarser interval stops being arithmetic. A daily partition
    costs nothing because its oldest and newest rows are the same day, and every other interval
    costs exactly the days between them."""
    assert over_retention_days(Interval.DAILY) == 0
    assert over_retention_days(Interval.WEEKLY) == 6
    assert over_retention_days(Interval.MONTHLY) == longest_days(Interval.MONTHLY) - 1


def test_the_longest_and_shortest_a_period_can_be_are_different_questions():
    """Delete this and somebody collapses the two into one figure, which is safe for neither:
    over-retention needs the longest a period can be and the premake needs the shortest, and a
    single average is wrong for both in opposite directions."""
    for interval in Interval:
        assert shortest_days(interval) <= longest_days(interval)
    assert shortest_days(Interval.MONTHLY) != longest_days(Interval.MONTHLY)


# -------------------------------------------------------------------------- the interval
def test_the_declared_interval_is_the_one_the_derivation_returns():
    """Delete this and `PARTITION_INTERVAL` becomes a member typed out, which would survive a
    change to the backup window or to the allowance without anything noticing. It is monthly
    today, and it is monthly because the walk says so rather than because M36.1.1.2 does."""
    assert PARTITION_INTERVAL is largest_safe_interval()
    assert PARTITION_INTERVAL is Interval.MONTHLY


def test_a_coarser_interval_is_refused_by_the_allowance_and_the_refusal_names_it():
    """Delete this and quarterly partitions look admissible. They keep the oldest row ninety-one
    days past its horizon against an allowance of thirty-five, which is the ledger over-retaining
    by longer than a deleted row already survives in the backups."""
    refusals = interval_refusals(Interval.QUARTERLY)
    assert refusals
    assert str(MAX_OVER_RETENTION_DAYS) in refusals[0]
    assert interval_refusals(Interval.YEARLY)


def test_a_smaller_allowance_chooses_a_shorter_interval():
    """Delete this and nothing shows the choice is a derivation rather than a lookup that
    returns monthly. Halve the allowance and the answer moves, which is what makes the module
    correct on a server whose backup window is not thirty-five days."""
    assert largest_safe_interval(allowance_days=6) is Interval.WEEKLY
    assert largest_safe_interval(allowance_days=0) is Interval.DAILY


def test_an_interval_finer_than_the_retention_policys_resolution_is_refused():
    """Delete this and the floor stops being checked at all. No shipped interval is finer than
    a day today, so this is the only way the branch is ever reached: a policy whose finest
    window is a week has nothing for a daily partition to align to."""
    refusals = interval_refusals(Interval.DAILY, resolution_days=7)
    assert refusals
    assert "finer than the retention policy can express" in refusals[0]


def test_an_interval_longer_than_the_window_it_cuts_is_refused():
    """Delete this and a scheme that produces one partition reads as a partitioned table. It is
    unreachable against the ledger's five-year window, so a shorter window is the only way to
    see the branch, and a shorter window is exactly what a second table would have."""
    refusals = interval_refusals(Interval.YEARLY, allowance_days=400, window_days=30)
    assert refusals
    assert "the table is one partition" in refusals[0]


def test_the_declared_interval_is_refused_by_nothing():
    """Delete this and a change to the allowance or the window could leave the module declaring
    an interval its own arithmetic rejects, with every other test still green because they all
    pass their own bounds in."""
    assert interval_refusals(PARTITION_INTERVAL) == ()


def test_no_admissible_interval_is_a_refusal_rather_than_a_default():
    """Delete this and the derivation could quietly return the first candidate when none fits.
    A default here would be a partition scheme nobody chose applied to the longest-lived table
    in the estate."""
    with pytest.raises(PartitioningError, match="no interval in"):
        largest_safe_interval((Interval.YEARLY,), allowance_days=0)


# --------------------------------------------------------------------------- the archive
def test_the_settling_window_is_what_the_interval_left_of_the_allowance():
    """Delete this and the alignment cost and the archive cost become two budgets, each
    defensible alone and adding to a total nobody costed. They are one allowance and this is the
    equality that says so."""
    assert SETTLE_DAYS + over_retention_days(PARTITION_INTERVAL) == MAX_OVER_RETENTION_DAYS
    assert SETTLE_DAYS >= 0


def test_a_delete_over_the_live_table_is_refused_and_says_what_it_costs():
    """Delete this and the cheapest change looks available. A delete is the operation
    partitioning exists to avoid, and the refusal has to name the reason or somebody reads it
    as a preference."""
    refusals = removal_refusals_for(Removal.DELETE_IN_PLACE)
    assert refusals
    assert "rewrites every row" in refusals[0]


def test_an_archive_kept_indefinitely_is_refused_as_a_per_row_override():
    """Delete this and "detach and archive" is read the way it usually is, as a table kept
    forever. A detached partition still holds metadata-ledger rows, so keeping it past the
    horizon is the per-row override `brain.ops.retention` refuses to have a field for."""
    refusals = removal_refusals_for(Removal.DETACH_AND_KEEP)
    assert refusals
    assert str(LEDGER_RETENTION_DAYS) in refusals[0]


def test_the_declared_removal_is_the_one_nothing_refuses():
    """Delete this and the module could declare a removal its own check rejects, which is the
    same shape of drift as an interval that fails its own bounds."""
    assert removal_refusals_for(REMOVAL) == ()
    assert REMOVAL is Removal.DETACH_THEN_DROP


def removal_refusals_for(removal: Removal) -> tuple[str, ...]:
    """Imported through a helper so the three tests above read as one question asked of three
    values rather than as three imports."""
    from brain.ops.partitioning import removal_refusals

    return removal_refusals(removal)


# --------------------------------------------------------------------------- the premake
def test_the_premake_covers_a_restore_from_the_oldest_backup():
    """Delete this and the premake becomes "a few, to be safe". The failure it defends is an
    insert after a restore finding no partition for its row, on the one table that has to hold
    a row for the request that went wrong."""
    assert PREMAKE * shortest_days(PARTITION_INTERVAL) >= BACKUP_RETENTION_DAYS
    assert premake_for(PARTITION_INTERVAL) == PREMAKE


def test_a_longer_restore_window_needs_more_premade_partitions():
    """Delete this and `premake_for` could ignore its argument and return a constant, which
    every other assertion here would still pass."""
    assert premake_for(Interval.MONTHLY, restore_window_days=365) > premake_for(Interval.MONTHLY)
    assert premake_for(Interval.YEARLY) == 2


def test_the_current_period_is_not_counted_towards_the_restore_window():
    """Delete this and the extra partition looks like padding. The current period is already
    partly elapsed, so it may cover almost none of the future, which is why the count is a
    ceiling division plus one rather than a ceiling division."""
    assert premake_for(Interval.DAILY, restore_window_days=0) == 1


def test_a_negative_restore_window_is_refused():
    """Delete this and a negative window produces a premake of one through the ceiling
    division, so a nonsense input answers as though it were a valid one."""
    with pytest.raises(PartitioningError, match="not a window"):
        premake_for(Interval.MONTHLY, restore_window_days=-1)


def test_the_partition_count_includes_the_premade_ones():
    """Delete this and the count an operator sizes a catalogue against is short by the premake,
    which is small here and is the whole difference for a daily interval."""
    window = partitions_over_the_window(Interval.MONTHLY)
    assert window > LEDGER_RETENTION_DAYS / shortest_days(Interval.MONTHLY)
    assert window == 69


def test_a_window_of_no_days_holds_no_partitions_and_is_refused():
    """Delete this and asking about a table nothing is retained from returns a count, which
    reads as a scheme for a table that has none."""
    with pytest.raises(PartitioningError, match="holds no partitions"):
        partitions_over_the_window(Interval.MONTHLY, window_days=0)


# ------------------------------------------------------------------------------ the spec
def test_the_control_column_is_a_key_of_the_row_the_ledger_actually_writes():
    """Delete this and `CONTROL_COLUMN` is a string that agrees with itself. It is checked
    against what `RequestTelemetry.ledger_row` produces, so renaming the field in
    `brain.ops.telemetry` fails here instead of producing a table every insert misses."""
    assert CONTROL_COLUMN in _ledger_row()


def test_the_declared_ledger_scheme_disagrees_with_the_retention_policy_nowhere():
    """Delete this and the scheme and the policy can drift apart. This is the one assertion that
    covers all six findings at once for the values actually shipped."""
    assert spec_gaps(LEDGER_SPEC, row=_ledger_row()) == ()


def test_a_class_with_no_clock_has_no_boundary_to_align_a_partition_to():
    """Delete this and a scheme over a class kept while its record exists reads as valid. There
    is no date for a partition to be cut on, and the finding has to stop rather than go on to
    report an interval against a window that does not exist."""
    findings = spec_gaps(_spec(data_class=DataClass.BUSINESS_RECORD))
    assert len(findings) == 1
    assert "no boundary for a partition" in findings[0]


def test_a_settling_window_that_overruns_the_allowance_is_a_finding():
    """Delete this and the archive can be extended one week at a time with the interval's own
    share of the allowance already spent, which is how a five-year window becomes five years and
    two months with every individual step looking reasonable."""
    findings = spec_gaps(_spec(settle_days=SETTLE_DAYS + 1))
    assert any("against an allowance" in one for one in findings)


def test_a_scheme_that_premakes_too_few_partitions_is_a_finding():
    """Delete this and a premake of one passes, which works every day until the first restore
    from an old backup and then refuses every write."""
    findings = spec_gaps(_spec(premake=1))
    assert any("premade partition" in one for one in findings)


def test_a_scheme_routing_on_a_column_the_row_does_not_hold_is_a_finding():
    """Delete this and the control column is only ever checked against the row it was written
    from. A scheme routing on a column the ledger does not write is a table every insert fails
    against, and nothing else here would say so."""
    findings = spec_gaps(_spec(control="written_at"), row=_ledger_row())
    assert any("would fail to find a partition" in one for one in findings)


def test_a_scheme_with_no_row_to_check_against_still_reports_the_other_findings():
    """Delete this and `row` stops being optional in practice, because a caller without one
    would get a false clean result rather than the five findings that do not need it."""
    assert spec_gaps(_spec(control="written_at")) == ()
    assert spec_gaps(_spec(control="written_at", premake=1)) != ()


def test_a_scheme_with_a_refused_removal_is_a_finding():
    """Delete this and the removal on the spec is decoration: `REMOVAL` is checked on its own
    above, and nothing would notice a spec declaring a different one."""
    findings = spec_gaps(_spec(removal=Removal.DELETE_IN_PLACE))
    assert any("is not how a ledger partition is removed" in one for one in findings)


def test_a_scheme_with_a_refused_interval_is_a_finding():
    """Delete this and the interval on the spec is decoration in the same way, and a spec
    declaring yearly partitions of a five-year window would pass every other check here."""
    findings = spec_gaps(_spec(interval=Interval.YEARLY))
    assert any("past the horizon" in one for one in findings)


# -------------------------------------------------------------------------- the validators
def test_a_scheme_with_no_control_column_cannot_be_built():
    """Delete this and a blank control column becomes a table that routes every row to nowhere,
    discovered on the first insert. Both spellings of blank, because a string field checked with
    a bare falsiness test passes a space."""
    for blank in ("", " "):
        with pytest.raises(PartitioningError, match="no control column"):
            _spec(control=blank)


def test_a_scheme_that_states_no_reason_cannot_be_built():
    """Delete this and the scheme joins every other partition scheme nobody can explain, which
    is the one that gets widened the first time a query is slow."""
    for blank in ("", " "):
        with pytest.raises(PartitioningError, match="states no reason"):
            _spec(because=blank)


def test_a_scheme_that_premakes_nothing_cannot_be_built():
    """Delete this and zero premade partitions is constructible. It accepts writes until the
    period rolls and then refuses them, which presents as an outage at midnight on the first of
    a month rather than as a configuration mistake."""
    with pytest.raises(PartitioningError, match="premakes 0 partition"):
        _spec(premake=0)


def test_a_scheme_with_a_negative_settling_window_cannot_be_built():
    """Delete this and a negative settle is constructible, which reads in the arithmetic as an
    archive that is dropped before it is detached."""
    with pytest.raises(PartitioningError, match="which is not a window"):
        _spec(settle_days=-1)


# ------------------------------------------------------------------------ what a migration gets
def test_the_partman_settings_repeat_only_numbers_the_derivation_produced():
    """Delete this and the settings a migration will be written from can drift from the
    derivation above, which would put a premake and a retention in a migration that no longer
    match the module that argued for them."""
    assert LEDGER_PARTMAN_SETTINGS["p_control"] == CONTROL_COLUMN
    assert LEDGER_PARTMAN_SETTINGS["p_premake"] == PREMAKE
    assert LEDGER_PARTMAN_SETTINGS["settle_days"] == SETTLE_DAYS
    assert LEDGER_PARTMAN_SETTINGS["retention"] == f"{LEDGER_RETENTION_DAYS} days"
    assert LEDGER_PARTMAN_SETTINGS["p_interval"] == partman_interval(PARTITION_INTERVAL)
    assert LEDGER_PARTMAN_SETTINGS["p_interval"] == "1 month"


def test_a_scheme_on_any_other_interval_still_names_a_period_postgres_can_parse():
    """Delete this and the settings can be built by string surgery on the interval's own name
    again. A mutation proved that: substituting it survived every test here, because
    `"monthly".removesuffix("ly")` is `"month"` and monthly is the only interval the module
    declares. The same substitution gives a daily scheme `"1 dai"`, which Postgres cannot parse,
    and asking for a daily scheme is the only way anything sees it."""
    daily = partman_settings(_spec(interval=Interval.DAILY, premake=premake_for(Interval.DAILY)))
    assert daily["p_interval"] == "1 day"
    quarterly = _spec(interval=Interval.QUARTERLY, premake=premake_for(Interval.QUARTERLY))
    assert partman_settings(quarterly)["p_interval"] == "3 months"


def test_the_settings_carry_the_specs_own_figures_and_not_the_declared_schemes():
    """Delete this and `partman_settings` can read the module's constants rather than the spec
    it was handed, which would make every call return the ledger's settings whatever was asked
    for and would hide the interval substitution again."""
    other = _spec(interval=Interval.WEEKLY, premake=premake_for(Interval.WEEKLY), settle_days=1)
    settings = partman_settings(other, retention_days=90)
    assert settings["p_interval"] == "1 week"
    assert settings["p_premake"] == premake_for(Interval.WEEKLY)
    assert settings["settle_days"] == 1
    assert settings["retention"] == "90 days"


def test_every_interval_names_a_period_postgres_can_parse():
    """Delete this and the period comes back from string surgery on the member name, which is
    what it did: `"daily".removesuffix("ly")` is `"dai"`, so a daily scheme would have been
    configured with a period nothing can read. It was invisible because monthly is the only
    interval the module declares and the surgery happens to work for that one."""
    assert partman_interval(Interval.DAILY) == "1 day"
    assert partman_interval(Interval.QUARTERLY) == "3 months"
    for interval in Interval:
        assert interval.value not in partman_interval(interval)


def test_the_detached_table_is_kept_so_that_something_can_settle_it():
    """Delete this and `retention_keep_table` could flip to false, which would make pg_partman
    drop the partition as it detaches it. That is a defensible scheme and it is not this one:
    M36.1.1.3 asks for an archive step, and the settling window is only meaningful if the table
    survives the detach."""
    assert LEDGER_PARTMAN_SETTINGS["retention_keep_table"] is True
    assert SETTLE_DAYS > 0


def test_the_policy_resolution_is_a_day_because_a_horizon_is_counted_in_days():
    """Delete this and the floor becomes an arbitrary one. `brain.ops.retention.Horizon.days` is
    a whole number of days, so a day is the finest window the policy can express and there is
    nothing below it to align to."""
    assert HORIZON_RESOLUTION_DAYS == 1
    assert LEDGER_SPEC.data_class is DataClass.METADATA_LEDGER
