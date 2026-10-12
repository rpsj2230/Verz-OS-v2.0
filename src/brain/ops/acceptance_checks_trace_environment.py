"""The install acceptance check for the environment a trace is filed under.

Langfuse fixes the set of environment values a project accepts at the first trace it ingests, so the
set is decided once, in silence, by whichever container starts first (`brain.ops.tracing`). The
tracker asks for it to be "asserted against the database enum", and **this product has no database
enum for it**: no migration creates one, and `brain.tables.config` argues that an environment
column would be a second, editable answer to a question the connection string already answers. What
the install does hold are three spellings of the same three names, and what can drift is one of
them. So this asks all three, in the worker, on the install's own code: the span vocabulary
`brain.ops.tracing.TRACE_ENVIRONMENTS`, the keys of `brain.config.REQUIRED` that refuse a
deployment, and the `Literal` the settings are validated against, and holds the environment this
install runs as to the first.

**What it proves and what it cannot.** That the three agree and that the install's own environment
is a value a span is accepted under, on the code this release shipped. Not that the Langfuse project
holds the same set, which is the ledger's to say and which this install does not run (the trace
ledger is switched on by `INSTALL_SERVICES`, and `brain.ops.acceptance_checks_services` asks it
where it is). The leaf's own words name a database enum, and what is asked here is the narrower
thing the code holds, said in the sentence a person reads beside the result.

Task ids: M32.1.2.3
"""

from __future__ import annotations

from typing import Final, get_args

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 711

#: A value no environment is called, which a span must be refused under.
NOT_AN_ENVIRONMENT: Final = "acceptance-not-an-environment"

THE_THREE_SPELLINGS_DISAGREE: Final = (
    "the trace vocabulary, the configuration's environments and the settings' own do not name the "
    "same set, which Langfuse would fix for good at its first ingest"
)
THIS_INSTALL_RUNS_AS_NO_ENVIRONMENT: Final = (
    "the environment this install runs as is not one a span is filed under"
)
AN_UNSEEN_VALUE_WAS_ACCEPTED: Final = "a span was accepted under an environment nobody declared"


@check(
    leaves=("M32.1.2.3",),
    sentence=(
        "The environment names a trace may carry, the ones the configuration refuses a deployment "
        "by and the ones the settings are validated against are the same three, this install's own "
        "environment is one of them, and a span under any other is refused. The product holds no "
        "database enum for it, so this asks those three spellings."
    ),
)
async def the_trace_environment_is_one_the_install_declares(h: Harness) -> None:
    from brain.config import REQUIRED
    from brain.ops.tracing import (
        TRACE_ENVIRONMENTS,
        TracingError,
        assert_environment,
        assert_environment_vocabulary,
    )
    from brain.settings import Settings

    declared = get_args(Settings.model_fields["env"].annotation)
    if set(declared) != set(REQUIRED) or set(declared) != set(TRACE_ENVIRONMENTS):
        raise CheckFailedError(THE_THREE_SPELLINGS_DISAGREE)
    try:
        assert_environment_vocabulary()
    except TracingError:
        raise CheckFailedError(THE_THREE_SPELLINGS_DISAGREE) from None
    try:
        assert_environment(h.settings.env)
    except TracingError:
        raise CheckFailedError(THIS_INSTALL_RUNS_AS_NO_ENVIRONMENT) from None
    try:
        assert_environment(NOT_AN_ENVIRONMENT)
    except TracingError:
        return
    raise CheckFailedError(AN_UNSEEN_VALUE_WAS_ACCEPTED)
