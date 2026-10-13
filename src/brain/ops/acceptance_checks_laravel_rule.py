"""The install acceptance check for the Laravel view rule: one department for every record.

The owner decided on needs item 138 (2026-10-13, option A) that each client record is visible to one
department for now: a view's rule is one equality on a field the view keeps, the index stores that
value on every record the view keeps, and a rule naming several departments is refused where it is
typed, with a sentence saying why, rather than saved and then showing nobody anything.

**What is run is the connect form's own build and the index's own storage.** The settings are the
form's fresh example, built through `brain.connectors.laravel.built_from_the_console` for a
department of acceptance_a, which must keep each view under that one department; the same
settings with a list in either rule must be refused naming that rule and saying why; and one
record is stored through `brain.ops.connector_sync.stored_fields` under the rule, which must hold
the department as the one value, while a record whose own field names another department is
refused rather than stored under it. Nothing is connected, read or written, and no database is
asked.

Task ids: M11.9.16, M11.9.17
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1520

# What the check says, one sentence for each way the property can fail.
ONE_DEPARTMENT_NOT_BUILT: Final = (
    "a Laravel connection with one department for each view's rule was not built"
)
A_LIST_WAS_ACCEPTED: Final = "a Laravel view rule naming several departments was accepted"
THE_WRONG_RULE_WAS_NAMED: Final = "a refused Laravel view rule did not name the rule refused"
NO_REASON_WAS_GIVEN: Final = "a refused Laravel view rule was not refused in the index's reason"
NOT_ONE_VALUE: Final = "a record was not stored with the one department its view's rule names"
A_CLASH_WAS_STORED: Final = "a record naming another department was stored under the rule"


@check(
    leaves=("M11.9.16", "M11.9.17"),
    sentence=(
        "The Laravel connect form built for one department of acceptance_a keeps both views "
        "under it, a rule listing two departments is refused naming that rule and saying why, a "
        "record is stored with the one department, and a record naming another is not stored."
    ),
)
async def a_laravel_view_rule_names_one_department_for_every_record(h: Harness) -> None:
    from brain.connectors.declaration import SettingRefusedError
    from brain.connectors.laravel import (
        CLIENT_RULE_SETTING,
        CONSOLE,
        USER_RULE_SETTING,
        built_from_the_console,
    )
    from brain.connectors.projection import ProjectedRecord
    from brain.core.scope import Clause, Op, Scope
    from brain.ops.connectable import key_reference
    from brain.ops.connector_sync import ConnectorSyncError, storable_predicate, stored_fields

    await h.found_departments()
    form = CONSOLE
    if form.example is None:
        raise CheckFailedError(ONE_DEPARTMENT_NOT_BUILT)
    settings = form.example.fresh((A, B))
    reference = key_reference("laravel")
    built = built_from_the_console(settings, reference)
    if not built.projections or not all(
        storable_predicate(one.visibility) for one in built.projections
    ):
        raise CheckFailedError(ONE_DEPARTMENT_NOT_BUILT)
    placed = {one.visibility.clauses[0].value for one in built.projections}
    if placed != {A}:
        raise CheckFailedError(ONE_DEPARTMENT_NOT_BUILT)

    for setting in (CLIENT_RULE_SETTING, USER_RULE_SETTING):
        listed = {**settings, setting: f"department in {A}, {B}"}
        try:
            built_from_the_console(listed, reference)
        except SettingRefusedError as refused:
            if refused.setting != setting:
                raise CheckFailedError(THE_WRONG_RULE_WAS_NAMED) from refused
            # Against the reason's own plain words and not the constant, which would agree with
            # itself whatever it said.
            if "holds one value" not in str(refused):
                raise CheckFailedError(NO_REASON_WAS_GIVEN) from refused
        else:
            raise CheckFailedError(A_LIST_WAS_ACCEPTED)

    rule = Scope(clauses=(Clause(field="department", op=Op.EQ, value=A),))
    now = datetime.now(tz=UTC)

    def record(**fields: str) -> ProjectedRecord:
        return ProjectedRecord(
            source="laravel",
            entity="laravel_client",
            source_id="acceptance-1",
            last_seen_at=now,
            fields={"name": "Acceptance client", **fields},
        )

    if stored_fields(record(), rule).get("department") != A:
        raise CheckFailedError(NOT_ONE_VALUE)
    try:
        stored_fields(record(department=B), rule)
    except ConnectorSyncError:
        return
    raise CheckFailedError(A_CLASH_WAS_STORED)
