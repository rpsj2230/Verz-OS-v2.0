"""Install acceptance check for what a new install is furnished with, as the owner decided it.

**This reads the install as it is, and writes nothing.** `acceptance_operations_console` shows the
install was furnished once and that furnishing again writes nothing. This check asks the other
question the leaf puts: whether a client opening the install finds a furnished system rather than
a blank one, in the shape needs-rupash 168 decided on 2026-10-06 (option A, accept both
narrowings of the leaf's sentence): **the six roles, the standard permission set and the
company-wide scope, and the built-in agent templates signed and on file, with the four defaults
being how the product already behaves and no agent installed before somebody chooses one.**

**The four defaults are checked against the code that makes them true, not against themselves.**
`starter.DEFAULTS` is a declaration nothing reads (that is the decision), so a test holding the
declared 30 minutes against the declared 30 minutes would compare a constant with itself. The two
session limits are held against `identity.sessions`' own limits, which the sign-in code enforces;
the other two have no code to compare with and are declared in words, so the check shows the
decision holds instead: **the product declares no setting under any of the four names**, because
a setting nothing reads changes nothing when somebody changes it (the reason item 168 gives for
writing none). It asks the installation's declaration and not the settings table, whose key
grammar refuses these names already, so a table query could never fail.

**Furniture an administrator retired is theirs, so the check says it was not run.** Furnishing
never puts back a scope or a pack that was taken away, and a person who retired one decided that.
Such an install is told so, rather than failed for a decision somebody made.

Task ids: M38.5.1, M41.2.7
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import FURNISHING_WRITES_ONLY, setting_entries
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 610

# ------------------------------------------------------------------ written-down reasons
#: Said when nothing has furnished the database, which the application does on every start. Held
#: in this module rather than imported, because a reason is held to a literal in the file that
#: raises it (`tests/unit/test_acceptance.py`).
NOTHING_HAS_FURNISHED_THIS_INSTALL: Final = (
    "this database has no record of being furnished, which the application writes the first "
    "time it starts against it, so it has not been started by the application yet"
)

#: Said when no built-in template is on file, which an install without a signing key does not sign.
NO_BUILT_IN_TEMPLATE_IS_ON_FILE: Final = (
    "no built-in template is on file, which an install whose template signing key has not been "
    "kept in its vault yet does not sign; the application signs them on its next start after it"
)

#: Said when the furnished scope or pack is not on this install any more.
FURNITURE_WAS_RETIRED_BY_SOMEBODY: Final = (
    "the starter pack or the company-wide scope has been retired on this install, which "
    "furnishing never puts back because whoever retired it decided that, so there is no "
    "furnished set here to read"
)

# ------------------------------------------------------------------------ the figures
#: The six platform roles, restated as words rather than read off the enum the product builds its
#: own list from, so a seventh or a rename fails this check instead of moving with the product.
THE_SIX_ROLES: Final = frozenset(
    {"super_admin", "department_admin", "member", "auditor", "connector_admin", "approver"}
)

#: The four defaults item 168 decided are how the product already behaves and are written nowhere.
THE_FOUR_DEFAULTS: Final = (
    "session_idle_minutes",
    "session_absolute_hours",
    "approval_required_above",
    "knowledge_visibility",
)


@check(
    leaves=("M41.2.7",),
    sentence=(
        "A new install holds the six roles, the starter permission set and the company-wide "
        "scope, every built-in agent template signed and on file, and no agent the furnishing "
        "installed; the session limits its defaults name are the ones the sign-in code enforces "
        "and none of the four defaults is a setting row, as decided."
    ),
)
async def a_new_install_is_furnished_as_decided_and_not_blank(h: Harness) -> None:
    from brain.agents.catalogue import CATALOGUE
    from brain.identity.sessions import SESSION_ABSOLUTE_MAX, SESSION_IDLE
    from brain.ops.starter import DEFAULTS, PACKS, SCOPES, agents, roles
    from brain.ops.starter_store import FURNISHED_KEY

    if {one.value for one in roles()} != THE_SIX_ROLES or len(roles()) != len(THE_SIX_ROLES):
        raise CheckFailedError("the platform does not furnish exactly the six roles")
    if not await setting_entries(h, FURNISHED_KEY):
        raise CheckNotRunError(NOTHING_HAS_FURNISHED_THIS_INSTALL)

    packs = {
        str(name): list(capabilities)
        for name, capabilities in (
            await h.execute(
                text(
                    "SELECT name, capabilities FROM gate.capability_pack"
                    " WHERE deleted_at IS NULL AND name = ANY(:names)"
                ).bindparams(names=[one.slug for one in PACKS])
            )
        ).all()
    }
    scopes = {
        str(slug): bool(is_department)
        for slug, is_department in (
            await h.execute(
                text(
                    "SELECT slug, is_department FROM gate.scope"
                    " WHERE deleted_at IS NULL AND slug = ANY(:slugs)"
                ).bindparams(slugs=[one.slug for one in SCOPES])
            )
        ).all()
    }
    if set(packs) != {one.slug for one in PACKS} or set(scopes) != {one.slug for one in SCOPES}:
        raise CheckNotRunError(FURNITURE_WAS_RETIRED_BY_SOMEBODY)
    if not all(packs.values()):
        raise CheckFailedError("a furnished permission set holds no capability")
    if any(scopes.values()):
        raise CheckFailedError("the furnished company-wide scope is a department")

    on_file = {
        (str(template), str(version)): bool(signature)
        for template, version, signature in (
            await h.execute(
                text("SELECT template_id, version, signature FROM agent.template_version")
            )
        ).all()
    }
    found = [
        on_file.get((one.identity.template_id, str(one.identity.version))) for one in CATALOGUE
    ]
    if not any(held is not None for held in found):
        raise CheckNotRunError(NO_BUILT_IN_TEMPLATE_IS_ON_FILE)
    if not all(found) or len(agents()) != len(CATALOGUE):
        raise CheckFailedError("a built-in agent template is not on file signed")

    traced_by = (
        (
            await h.execute(
                text(
                    "SELECT DISTINCT split_part(subject, ':', 1) FROM obs.audit_entry"
                    " WHERE trace_id = (SELECT trace_id FROM obs.audit_entry"
                    " WHERE subject = :subject ORDER BY seq LIMIT 1)"
                ).bindparams(subject=f"setting:{FURNISHED_KEY}")
            )
        )
        .scalars()
        .all()
    )
    if set(traced_by) - FURNISHING_WRITES_ONLY:
        raise CheckFailedError("the furnishing wrote something besides its setting, scope and pack")

    declared = {one.name: one.value for one in DEFAULTS}
    if set(declared) != set(THE_FOUR_DEFAULTS):
        raise CheckFailedError("the starter defaults are not the four the owner decided on")
    if declared["session_idle_minutes"] != str(int(SESSION_IDLE.total_seconds() // 60)):
        raise CheckFailedError("the idle limit the defaults name is not the one sign-in enforces")
    if declared["session_absolute_hours"] != str(int(SESSION_ABSOLUTE_MAX.total_seconds() // 3600)):
        raise CheckFailedError(
            "the absolute limit the defaults name is not the one sign-in enforces"
        )
    # A setting nothing reads is a setting that changes nothing when somebody changes it, which is
    # item 168's reason for writing none: the product reads no setting by any of these names, and
    # the settings table would refuse a row under them if it were asked (they are not keys).
    from brain.install import BY_NAME

    if any(name in BY_NAME or f"INSTALL_{name.upper()}" in BY_NAME for name in THE_FOUR_DEFAULTS):
        raise CheckFailedError(
            "a default that is decided to be how the product behaves is a setting"
        )
