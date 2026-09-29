"""The providers this install may use, switched on and off from the console, with measured health.

M27.8.8 asks for "AI providers, models and the routing between them, managed from the console".
The routing between them was already editable (`brain.routing_routes`) and changed nothing,
because nothing called a model; the providers had no registry at all; and the Models and health
screen drew "Not recorded" beside every provider because `brain.console.model_matrix` would have
drawn a closed breaker nobody had tested. This module is the three routes that close those gaps
over `brain.models.calls.ModelCalls`, which the lifespan builds as `app.state.models`.

**One read, and it is the plan the next call makes.** `GET /models/providers` asks the executor
for `planned()`, the same assembly and replayed health `complete` walks, so what the screen says
will answer is what answers, each rung left out says why in `brain.models.assembly.TOLD`'s words,
and each rung's breaker is the one its attempts produced, marked measured or not. A screen that
recomputed any of that would be a second copy of the router's decision, and the copy a person
trusts would be the one that drifted. See `THE_SCREEN_DRAWS_THE_PLAN_THE_NEXT_CALL_MAKES`.

**A switch is a confirmed administrator write, held over everything.** `admin:routing_matrix`,
the routing matrix's own write capability, and only with an unrestricted scope, for the reason
`brain.credential_routes.A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION`
gives about a key: switching a provider changes where every department's questions go, so a grant
scoped to one department is not a grant here. The capability is asked before the provider's name
is looked at and before the database is, which is `brain.routing_routes`' order and its argument.
The console confirms the write before sending it; this module refuses it without the capability
whatever the console did.

**The switch takes effect on the next call in every process**, because every call reads the
switches (`brain.ops.model_service`), and the answer to the write is the plan read after it, so
the person who switched a provider off sees its rungs leave the chain in the same response.

**Whether a key is held is said two ways, and neither is a key.** `key_held` is whether this
server process's environment names the provider's variable, from
`brain.ops.provider_keys.names_in_environment`, which is what decides whether its rungs answer
here. `credential` is the vault's own answer from `brain.credential_routes.listing`, and it is
served only to a reader who may manage credentials, because that route serves it to nobody else.
A reader of this screen without that authority is told which rungs answer and why, including that
a rung has no key, which is the operational fact the screen exists to show; they are not told what
the vault holds. See `A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS`.

**A check is a real call, metered like any other, and a request rather than a probe.** `POST
/models/providers/{provider}/check` sends one fixed sentence through that provider's first
answering rung, as the administrator who pressed it, on the answer lane's budget because a person
is waiting. Its attempts are rows the breaker is replayed from, and its tokens are on its ledger
row. It is not the prober `brain.models.health` keeps out of the live ring: a person pressing a
button once is live traffic through the whole path, and three failed presses opening a breaker is
the breaker being right. The reply is not returned, because nothing a model says about a fixed
sentence is a fact an administrator needs; that it answered, which deployment and model served it,
and what it cost, are. It is recorded on the metadata ledger and in spend, at the price the
administrator set for the model, and not as a question, because it is not one. See
`A_CHECK_IS_A_REQUEST_AND_NOT_A_PROBE`.

**A provider no step names is checked through its default model, not refused** (found on the
owner's install on 2026-09-28: Test on OpenAI, whose key he had just saved, answered that nothing
named it and told him to add a step). The question a Test answers is whether the key works, and a
key is worth knowing about before anybody builds a step on it. So the check plans from a copy of
the ladder with one step added, the provider's own default model at the first default level
(`brain.models.default_ladder.default_rung`, the numbers a default step carries), through
`ModelCalls.trying`: the switch, the profile, the key and the breaker are asked exactly as for a
step, the meter and the ledger row are the caller's as for any check, and only the attempt row is
not written, because it would name a step that does not exist. The answer says which model was
used and that it was the default. See `A_KEY_IS_CHECKED_BEFORE_ANY_STEP_USES_IT`.

**A refused key is said, and is never drawn as a working provider.** A 401 or 403 stops the chain
and is not ill health (`brain.models.evidence.ONLY_THE_PROVIDERS_OWN_FAILURE_IS_ILL_HEALTH`), so
the breaker stays closed and, measured, drew "working" beside a provider that had just refused the
key. The check names it (`key_refused`), and the read marks each step whose latest attempt in the
evidence window was refused that way, so the screen says so instead of calling it healthy. See
`A_REFUSED_KEY_IS_NOT_A_HEALTHY_PROVIDER`.

**Everything a person can be shown here is in plain words**: the owner's (step, level, provider,
model), never rung, ladder, tier, lane or slot, and a test reads every sentence for them.

**Each provider is shown with its registry row and what it has been sent** (M5.6.4): the
processing region, the retention and training terms, the agreement link and the lane overrides
from `ops.model_provider`, and per category of data the number of attempts that carried it, from
`ops.model_attempt`. A provider added from the console (M5.7.2) is listed, switched and checked
like a built-in one. The rows are written by `brain.provider_registry_routes`.

**The screen also shows what routes a question and what the routing has noticed** (M5.2.2,
M5.4.3, M5.4.8, M5.5.1): each tier's window and escalation headroom as the router reads them from
`ops.routing_tier`, marked configured or the product's default; each rung's probes beside its live
calls, from `ops.provider_health`; the residency constraints attached to scopes; and the chain-depth
alerts of the last day. They are edited through `brain.model_health_routes`, under the same write
capability as a switch, and each answer is this view.

**Where answers are made is chosen here too, by the super administrator** (M5.7.1). The install's
model profile (`INSTALL_MODEL_PROFILE`: `local`, this server only, or `hosted`, online providers)
is the consent for a question's text to leave the server at all, and until 2026-09-28 only the
setup wizard could set it: an owner who chose nothing got `local`, saved keys, and every hosted
step skipped, while `TOLD[LOCAL_PROFILE]` told him to change a setting no screen offered.
`PUT /models/profile` writes it through `brain.ops.install_settings.save`, the wizard's own writer,
attributed so `0059`'s trigger ledgers who changed it, and holds the saved values in this process
at once. Only a holder of `admin:install_setting` over everything may, which is what a super
administrator holds (a role implies no capability here: `brain.identity.roles.
NO_ROLE_IMPLIES_A_CAPABILITY`). The process that saved it plans with it from the answer to the
write; another process reads it when it next loads the saved values, which is
`brain.ops.install_settings.A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER` and is not
closed here. See `WHERE_ANSWERS_ARE_MADE_IS_AN_INSTALLATION_SETTING_AND_NOT_A_SWITCH`.

**Not written, and said.** A provider switch is an `ops.setting` row, so it keeps its last change
on the row and `0059`'s trigger appends a `setting` entry for it:
`brain.ops.setting_store.A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE`. A rung is
added through the matrix gate (`brain.routing_routes`), never here.

**What a model costs is set here, per provider and model, in the install's currency (M27.12.5).**
`GET /models/prices` lists every model on the ladder and every model priced, each with its price
and whether a call to it is costed; `PUT /models/prices` sets one, for the holder of the switch's
capability, attributed so `0059`'s trigger ledgers who changed which provider's prices. A price is
refused while the install has no currency: a figure set in none is the plausibly wrong unit
`brain.locale` refuses to draw. See `brain.models.pricing` and `brain.ops.price_store`.

**The providers are a list the console pages, searches and filters** (M27.16.1, 2026-09-28): the
read's `items` and `next_cursor` are `brain.api.Page`'s convention over `brain.listing`'s contract,
ordered as the product lists them. `providers` stays every provider, unnarrowed, because the matrix
and the forms beside it name providers the question may have left off the page, and every other
field is the whole plan, because a step is not a provider and the matrix is one answer.

**Each provider carries its last test**, kept as the `provider_check.<slug>` setting by `check`:
how it ended and the model it used, with the row's own writer and instant, so the list says
"Answered, 3 Sep" without a second table, and `0059`'s trigger puts each test on the ledger. See
`A_TEST_IS_REMEMBERED_WHERE_ITS_SWITCH_IS`.

**One provider's figures are `GET /models/providers/{provider}/stats`**, over thirty days.
**Answered is counted from the metadata ledger**, `obs.request_telemetry`: the requests whose model
calls all went to this provider, which is the one provider the row names (`brain.models.metering.
_agreed`). The same ledger the Models screen's own figures read, under the same screen's
everybody basis, and no row, person or question leaves the count. **Failures and cost are named
and left out, never nought.** A failed call is kept only in `ops.model_attempt`, the executor's own
store, which no screen reads (`tests/unit/test_operate_routes.py` holds it), and a request that
failed over to another provider names the one that answered; cost is kept per request, whose calls
can span providers, and read through the spend grant, which a reader of this screen need not hold,
so the Spend report shows it by model. See `A_PROVIDERS_FIGURES_ARE_READ_FROM_THE_LEDGER`.

**The routing configuration exports without keys** (M27.15.38): `GET /routing/export` is the
plan's steps, the providers' switches and registry rows and the levels' numbers, as one JSON
document named for saving. It is built from the same read the screen draws and carries no
credential field at all, not even whether a key is held, so a copy handed to a supplier says how
the install routes and nothing about how it authenticates. See `AN_EXPORT_CARRIES_NO_KEY`.

Task ids: M27.8.8, M27.2.3, M5.6.4, M5.7.1, M5.7.2, M5.2.2, M5.4.3, M5.4.8, M5.5.1, M27.15.38
Task ids: M27.12.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, refused_request
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.console.model_matrix import exhausted_tiers, matrix
from brain.console.operate import figure_basis, panel
from brain.console.workspace import Basis
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.lane import Lane
from brain.credential_routes import SlotView, credentials_of, listing, may_manage
from brain.gate.finish import Finished, ModelCallOutcome, Origin, RequestRecorder, finish
from brain.install import hold_saved
from brain.listing import Column, ListAsked, Listing
from brain.locale import currency as install_currency
from brain.models.assembly import (
    HOSTED_PROFILE,
    LOCAL_PROFILE,
    TOLD,
    LadderRung,
    RungSkip,
    local_only,
)
from brain.models.calls import ModelCalls, Planned, chain_of
from brain.models.default_ladder import DEFAULT_TIERS, default_model, default_rung
from brain.models.disclosure import TOLD as CATEGORY_TOLD
from brain.models.disclosure import DataCategory
from brain.models.driver import DriverFailure, DriverMessage, ProviderUnavailable, Role
from brain.models.evidence import EVIDENCE_WINDOW
from brain.models.metering import Meter
from brain.models.pricing import NO_CURRENCY, Price, PricingError, decimal_of
from brain.models.registry import MODEL_NAME_PATTERN, SLUG_PATTERN, ProviderKind, ProviderRecord
from brain.models.routing import TIER_LADDER, BreakerState, FallbackTrigger, NoCompliantRoute, Tier
from brain.models.tier_rules import TierTable
from brain.models.wire import LOCAL_PROVIDER
from brain.operate_routes import MODELS_SCREEN
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.credentials import VaultState
from brain.ops.install_settings import load, save
from brain.ops.model_service import (
    KNOWN_PROVIDERS,
    ModelService,
    NoAttempts,
    disclosure_counts,
    disclosures,
    recent_statuses,
    switch_provider,
    switch_states,
)
from brain.ops.price_store import read_prices, set_price
from brain.ops.provider_health_store import live_constraints, recent_alerts
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.ops.telemetry_store import TelemetryRecorder
from brain.ops.usage_store import UsageRecorder
from brain.routing_routes import MATRIX_WRITE
from brain.settings_routes import may_configure
from brain.tables.config import SettingType
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why this route serves the executor's own plan rather than computing a view of its own.
THE_SCREEN_DRAWS_THE_PLAN_THE_NEXT_CALL_MAKES: Final = (
    "The executor reads the ladder, the switches, the keys and the attempts on every call and "
    "decides which rungs can answer. This route asks it for exactly that, so the screen shows the "
    "chain the next question will walk. A view computed here would be a second copy of the "
    "router's decision, and the one a person reads during an incident would be the copy that "
    "drifted."
)

#: Why the vault's answer and this process's key are served separately.
A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS: Final = (
    "A key in this process's environment is what lets its rungs answer, and a key in the vault is "
    "what every process loads at its next start. They differ after a rotation until a restart, "
    "and when the environment file sets the variable. The first decides what this screen draws "
    "as answering and is shown to its readers; the second is the credentials screen's to serve "
    "and is shown only to a reader who may manage credentials."
)

#: Why a check writes a ledger row and attempt rows and is not a probe.
A_CHECK_IS_A_REQUEST_AND_NOT_A_PROBE: Final = (
    "A probe is a synthetic request a scheduler sends on its own, and letting its outcomes move "
    "the live ring lets the prober vote on its own verdict. A check is a person asking, through "
    "the same chain, breaker admission, attempt rows and meter as any call, once per press. Its "
    "outcome is live evidence, its tokens are on the ledger under the person who pressed it, and "
    "it is not a question, so the question count never sees it."
)

#: Why a provider with a key and no step is still checked.
A_KEY_IS_CHECKED_BEFORE_ANY_STEP_USES_IT: Final = (
    "Test answers whether a provider takes this install's key and answers, and that is worth "
    "knowing before a step is built on it. A provider no step names is sent the same one "
    "sentence through its default model, planned as a step would be, so the switch, the "
    "profile, the key and the breaker still decide, and the answer names the model it used."
)

#: Why a 401 or 403 is shown as a refused key rather than as health.
A_REFUSED_KEY_IS_NOT_A_HEALTHY_PROVIDER: Final = (
    "A provider that refuses the key has answered, so the breaker, which counts only the "
    "provider's own failures, stays closed and the step reads as measured. Drawn from the "
    "breaker alone that is a working provider, and it is one no question can reach. So the "
    "check says the key was refused, and a step whose latest attempt was refused that way is "
    "marked, whatever its breaker says."
)

#: Why a provider's last test is an `ops.setting` row.
A_TEST_IS_REMEMBERED_WHERE_ITS_SWITCH_IS: Final = (
    "A test is a request, and its attempts and its ledger row say what it did; neither says which "
    "test was the last one for a provider, and a provider no step names writes no attempt at all. "
    "So the outcome is kept as the provider_check setting beside the provider's switch: one row, "
    "overwritten by the next test, carrying who pressed it and when, and appended to the ledger "
    "by the setting trigger like every other row of that table. It keeps how the test ended and "
    "the model it used, never the reply."
)

#: Why the export carries nothing about keys.
AN_EXPORT_CARRIES_NO_KEY: Final = (
    "The export is how the install routes: its steps, its providers' switches and terms, and its "
    "levels' numbers. A key is how it authenticates, and whether one is held is a fact about the "
    "vault, which the credentials screen serves to the few who may manage it. So the export has "
    "no credential field, no vault state and no key flag, and a copy handed to anybody says "
    "nothing about either."
)

#: Why the profile is saved as an installation setting from this screen rather than switched.
WHERE_ANSWERS_ARE_MADE_IS_AN_INSTALLATION_SETTING_AND_NOT_A_SWITCH: Final = (
    "The profile decides whether a question's text may leave the server at all, for every "
    "provider at once, so it is the installation value INSTALL_MODEL_PROFILE and not a provider "
    "switch. It is saved by the wizard's own writer, read by the one reader value_of, ledgered as "
    "a setting, and changed only by whoever holds admin:install_setting over everything. A "
    "second store for it here would be a second answer to where text may go, and the one the "
    "worker read would be the one nobody changed."
)

# ----------------------------------------------------------------- the figures

#: The installation value a profile change saves.
PROFILE_SETTING: Final = "INSTALL_MODEL_PROFILE"

#: What a check sends. Fixed, so nothing about the install or a person reaches the provider, and
#: short, so the call costs a handful of tokens.
CHECK_PROMPT: Final = "Reply with the single word: ready"

#: The output ceiling on a check. A one-word reply needs far fewer; the margin is for a model that
#: says a sentence anyway, and the ceiling is what stops it saying a page.
CHECK_MAX_OUTPUT_TOKENS: Final = 16

#: How far back the screen lists chain-depth alerts. A day: an alert older than that has either
#: been acted on or is a pattern the provider health figures already show.
ALERT_WINDOW: Final = timedelta(hours=24)

#: The provider statuses that mean it refused the key rather than the request: 401, the key is not
#: one it knows, and 403, the key is not allowed what was asked. See
#: `A_REFUSED_KEY_IS_NOT_A_HEALTHY_PROVIDER`.
KEY_REFUSED_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: The level a provider no step names is checked at: the first level a default ladder fills.
CHECK_LEVEL: Final[Tier] = DEFAULT_TIERS[0]

#: The id the check's one added step carries. It names no row, and its attempt row is not written.
UNLADDERED_RUNG_ID: Final = "provider-check"

#: The `ops.setting` namespace a provider's last test is kept under, as `provider_check.<slug>`.
#: Its own namespace, so `model_service.switch_states`, which reads `provider.<slug>`, never sees
#: it. See `A_TEST_IS_REMEMBERED_WHERE_ITS_SWITCH_IS`.
CHECK_NAMESPACE: Final = "provider_check"

#: How many days a provider's figures cover, as the other console figures read thirty days.
STATS_DAYS: Final = 30

#: Why a provider's figures come from the metadata ledger and not from its attempts.
A_PROVIDERS_FIGURES_ARE_READ_FROM_THE_LEDGER: Final = (
    "A call in flight and a call that failed are written by the executor to its own store, which "
    "decides whether a provider is resting and which no screen reads. The metadata ledger records "
    "each finished request with the one provider that answered it, so that is what a provider's "
    "page counts, and a failure, which the ledger does not attribute to a provider, is named as "
    "not recorded rather than counted from a table the screen may not read."
)

#: Why a provider's failures are not shown.
FAILURES_ARE_NOT_ATTRIBUTED: Final = (
    "A failed call is kept only where the routing decides whether a provider is resting, and a "
    "request that failed over is recorded under the provider that answered it. A provider resting "
    "after failures is marked on the failover matrix."
)

#: Why a provider's cost is not recorded.
NO_COST_RECORDED: Final = (
    "Nothing on this install records what a model call costs yet, so no cost is shown rather "
    "than a cost of nought."
)

#: Why a provider's cost is not shown once cost is recorded. See the module docstring.
COST_IS_NOT_SPLIT_BY_PROVIDER: Final = (
    "Cost is kept per request, and one request's calls can reach more than one provider, so it is "
    "not split by provider here. The Spend report shows it by model."
)

#: The name the routing export is saved under.
EXPORT_FILENAME: Final = "routing-configuration.json"

#: What an administrator is told about a check, by how it ended. Plain words: see the module
#: docstring. An answer is told with its model by `answered_told`; this entry is its fallback.
CHECK_TOLD: Final[Mapping[str, str]] = MappingProxyType(
    {
        "answered": "The provider answered.",
        "no_model": (
            "No step on the failover matrix uses this provider, and this product has no default "
            "model for it to test with. Add a step for one of its models on the Routing screen, "
            "then test again."
        ),
        "out_of_rotation": (
            "Every step that uses this provider is paused on the Routing screen, so nothing "
            "would be sent to it. Turn one of its steps back on, then test again."
        ),
        "key_refused": (
            "The provider refused the key. Replace the key for this provider with a current one "
            "that may use this model, then test again."
        ),
        "stopped": (
            "The provider turned the request down. Check that the model tested is available on "
            "the provider's account."
        ),
        "refused": "The model declined the test sentence on content grounds.",
        FallbackTrigger.CONNECTION_ERROR.value: (
            "The provider could not be reached from this server."
        ),
        FallbackTrigger.TIMEOUT.value: "The provider did not answer in time.",
        FallbackTrigger.RATE_LIMITED.value: (
            "The provider asked for fewer requests. Wait a minute and test again."
        ),
        FallbackTrigger.PROVIDER_ERROR.value: "The provider reported a fault on its side.",
        FallbackTrigger.CIRCUIT_OPEN.value: (
            "Recent calls to this provider failed, so it is resting. Test again in a few "
            "minutes, once its rest has passed."
        ),
        FallbackTrigger.CONTEXT_EXCEEDED.value: "The test did not fit the model's limit.",
    }
)


def answered_told(model: str, *, default_model: bool) -> str:
    """What a check that answered says: which model answered, and whether it was the default."""
    if default_model:
        return (
            f"The provider answered, using {model}. No step on the failover matrix uses this "
            "provider yet, so the test used its default model."
        )
    return f"The provider answered, using {model}."


def default_model_told(told: str, model: str) -> str:
    """A check's sentence, with the default model it was sent to named after it."""
    return (
        f"{told} The test used {model}, this provider's default model, because no step on the "
        "failover matrix uses it yet."
    )


# ------------------------------------------------------------------------ the shapes


class LaneOverrideView(BaseModel):
    """One lane's override of a provider's rung numbers (M5.1.3). Null leaves the rung's own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane: str
    timeout_seconds: float | None
    attempts: int | None


class RegisteredView(BaseModel):
    """A provider's registry row: where it processes and what the company agreed with it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    kind: ProviderKind
    #: Only for an added provider. Never editable: see `brain.models.registry`.
    base_url: str | None
    models: list[str]
    processing_region: str
    residency_class: str
    storage_location: str
    retention_terms: str
    training_terms: str
    agreement_url: str | None
    lane_overrides: list[LaneOverrideView]


class DisclosedView(BaseModel):
    """One category of data a provider has been sent, and how many attempts carried it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: DataCategory
    told: str
    attempts: int


class LastCheckView(BaseModel):
    """How a provider's last test ended, the model it used, and when. Never the reply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answered: bool
    #: The check's own vocabulary: `answered`, a fallback trigger, `key_refused` and the rest.
    outcome: str
    model: str | None
    at: datetime


class ProviderStateView(BaseModel):
    """One provider: what it is, whether it is switched on, and whether a key is held here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Where the product lists it: built in, then added, then this server's own. The list's order.
    listed: int = 0
    provider: str
    description: str
    #: Outside the client's own hardware. Every provider but the local inference server.
    hosted: bool
    switched_on: bool
    #: Who last switched it and when, or null for a provider nobody has switched.
    switched_by: str | None
    switched_at: datetime | None
    #: Whether this server process holds a key for it, or null for a provider needing none.
    key_held: bool | None
    #: The vault's own answer for the provider's slot, only for a reader who may manage
    #: credentials. See `A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS`.
    credential: SlotView | None
    #: The registry row, or null for a provider nobody has recorded terms for.
    registered: RegisteredView | None = None
    #: What this provider has been sent, by category, with counts. Empty when nothing was.
    disclosed: list[DisclosedView] = []
    #: Its last test from the console, or null for a provider nobody has tested.
    last_check: LastCheckView | None = None


class RungStateView(BaseModel):
    """One live rung: where it sits, whether it answers now, and its measured health."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rung_id: str
    tier: str
    position: int
    role: str
    deployment_id: str
    provider: str
    model: str
    enabled: bool
    answers: bool
    skipped_because: RungSkip | None
    told: str | None
    state: BreakerState
    #: Whether any attempt stands behind `state`.
    measured: bool
    unhealthy_because: str | None
    live_seen: int
    live_failed: int
    #: The probe ring `ops.provider_health` keeps for this deployment (M5.4.3, M5.4.7).
    probes_seen: int = 0
    probes_failed: int = 0
    #: When the prober last claimed a probe of it, and when live traffic last reached it.
    last_probe_at: datetime | None = None
    last_live_at: datetime | None = None
    #: Its latest attempt in the evidence window was refused as a key (401 or 403). See
    #: `A_REFUSED_KEY_IS_NOT_A_HEALTHY_PROVIDER`.
    key_refused: bool = False


class RoutingTierView(BaseModel):
    """One tier's numbers as the router reads them (M5.2.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    context_window: int
    escalation_headroom: float
    #: True when an `ops.routing_tier` row governs it; false when it runs at the product default.
    configured: bool


class ResidencyConstraintView(BaseModel):
    """One residency constraint and the scope it is attached to (M5.5.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    scope: dict[str, Any]
    allowed_regions: list[str] | None
    on_prem_only: bool
    note: str
    created_by: str
    created_at: datetime


class ChainDepthAlertView(BaseModel):
    """One chain-depth alert the live path raised (M5.4.8). Names a mechanism, never a question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raised_at: datetime
    level: str
    tier: str
    depth: int
    served_by: str | None
    reason: str
    trace_id: str


class ProvidersView(BaseModel):
    """The providers and the ladder as the next call will see them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `local` or `hosted`, as the executor read it. Anything else is read as `local`.
    profile: str
    providers: list[ProviderStateView]
    rungs: list[RungStateView]
    #: Tiers with at least one rung and every rung open: a tier that cannot answer at all.
    exhausted_tiers: list[str]
    #: Whether this reader may switch a provider or check one. Presentation only.
    editable: bool
    #: The vault's state and sentence, only beside `credential`, for the same reader.
    vault: VaultState | None
    vault_told: str | None
    #: Each ladder tier's window and headroom as the router reads them.
    tiers: list[RoutingTierView] = []
    #: The live residency constraints, oldest first.
    residency: list[ResidencyConstraintView] = []
    #: The chain-depth alerts of the last `ALERT_WINDOW`, newest first.
    depth_alerts: list[ChainDepthAlertView] = []
    #: Whether this reader may change where answers are made. Presentation only.
    profile_editable: bool = False
    #: The page of providers matching the list's question, in the product's order: the
    #: `brain.api.Page` convention's `items`. A write's answer carries every provider here.
    items: list[ProviderStateView] = []
    #: Present exactly when a further provider matches the list's question. See `brain.listing`.
    next_cursor: str | None = None


class UnrecordedView(BaseModel):
    """A figure the page asks for that nothing on this install records, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


class ProviderStatsView(BaseModel):
    """One provider's figures over `days`. A figure nothing records is null and named in
    `unrecorded` with its reason, never nought."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    days: int
    #: Requests whose model calls all went to this provider, or null without a ledger.
    answered: int | None
    failures: int | None
    cost_minor: int | None
    unrecorded: list[UnrecordedView]


class ExportedStep(BaseModel):
    """One step of the failover matrix as the export writes it: its level, number and numbers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The level by the key every request names it with: `small`, `main` or `heavy`.
    tier: str
    step: int
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int
    enabled: bool


class ExportedProvider(BaseModel):
    """One provider as the export writes it: switched on or off, and its registry row. No key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    switched_on: bool
    registered: RegisteredView | None


class RoutingExportView(BaseModel):
    """The routing configuration as one document named for saving.

    See `AN_EXPORT_CARRIES_NO_KEY` for what it leaves out.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    generated_at: datetime
    profile: str
    steps: list[ExportedStep]
    providers: list[ExportedProvider]
    tiers: list[RoutingTierView]


class ProviderSwitchAsked(BaseModel):
    """The one field a switch carries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool


class ProfileAsked(BaseModel):
    """Where answers are made: `local`, this server only, or `hosted`, online providers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: Literal["local", "hosted"]


class CheckView(BaseModel):
    """How one check ended. Never the reply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    answered: bool
    #: `answered`, a `RungSkip`, a fallback trigger, `key_refused`, `stopped`, `refused`,
    #: `out_of_rotation` or `no_model`.
    outcome: str
    told: str
    served_by: str | None
    #: The model that answered, or on the default path the model the check was sent to.
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    #: The provider's HTTP status on a failure that had one.
    status: int | None
    trace_id: str
    #: No step names the provider, so the check was planned through its default model. See
    #: `A_KEY_IS_CHECKED_BEFORE_ANY_STEP_USES_IT`.
    default_model: bool = False


# ------------------------------------------------------------------------ the decisions


def may_read(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader's basis for the models screen is everybody's."""
    return figure_basis(panel(MODELS_SCREEN), reach, now) is Basis.EVERYONE


def may_switch(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader holds the matrix's write capability over everything."""
    scope = reach.scope_for(MATRIX_WRITE, now)
    return scope is not None and scope.is_unrestricted()


def normalised_profile(profile: str) -> str:
    """The profile as the executor acts on it: `hosted`, or `local` for anything else."""
    return LOCAL_PROFILE if local_only(profile) else HOSTED_PROFILE


def registered_view(record: ProviderRecord) -> RegisteredView:
    """One registry record as the screen shows it."""
    return RegisteredView(
        label=record.label,
        kind=record.kind,
        base_url=record.base_url,
        models=list(record.models),
        processing_region=record.processing_region,
        residency_class=record.residency_class.value,
        storage_location=record.storage_location,
        retention_terms=record.retention_terms,
        training_terms=record.training_terms,
        agreement_url=record.agreement_url,
        lane_overrides=[
            LaneOverrideView(
                lane=lane.value,
                timeout_seconds=override.timeout_seconds,
                attempts=override.attempts,
            )
            for lane, override in sorted(record.lane_overrides.items())
        ],
    )


def listed_providers(plan: Planned) -> tuple[str, ...]:
    """The built-in providers, then those added from the console, then the local server."""
    added = tuple(
        one.slug for one in plan.state.providers if one.kind is ProviderKind.OPENAI_COMPATIBLE
    )
    builtin = tuple(one for one in KNOWN_PROVIDERS if one != LOCAL_PROVIDER)
    return (*builtin, *added, LOCAL_PROVIDER)


def tier_views(table: TierTable) -> list[RoutingTierView]:
    """Each ladder tier's numbers, cheapest first, as the plan's table holds them."""
    return [
        RoutingTierView(
            tier=tier.value,
            context_window=table.windows[tier],
            escalation_headroom=table.headroom[tier],
            configured=tier in table.configured,
        )
        for tier in TIER_LADDER
    ]


def providers_view(
    plan: Planned,
    *,
    switches: dict[str, tuple[bool, str, datetime]],
    reach: EntitlementSet,
    now: datetime,
    vault: tuple[VaultState, dict[str, SlotView]] | None,
    disclosed: dict[str, dict[DataCategory, int]] | None = None,
    residency: list[ResidencyConstraintView] | None = None,
    alerts: list[ChainDepthAlertView] | None = None,
    profile_editable: bool = False,
    refused: frozenset[str] = frozenset(),
    checks: Mapping[str, LastCheckView] | None = None,
) -> ProvidersView:
    """The plan and the switch rows, as one reader may be shown them.

    `vault` is None unless the reader may manage credentials; see the module docstring.
    `disclosed` is the attempts per provider and category of data (M5.6.4). `residency` and
    `alerts` are read beside the plan, because the plan carries constraints without their ids.
    `refused` is the deployments whose latest attempt the provider refused as a key. `checks` is
    each provider's last test, by slug.
    """
    rings = {one.deployment_id: one for one in plan.state.rings}
    described = {one.slug: one.description for one in PROVIDER_SLOTS}
    records = {one.slug: one for one in plan.state.providers}
    sent = disclosed or {}
    tested = checks or {}
    providers = []
    for listed, slug in enumerate(listed_providers(plan)):
        switched = switches.get(slug)
        record = records.get(slug)
        providers.append(
            ProviderStateView(
                listed=listed,
                last_check=tested.get(slug),
                provider=slug,
                description=(
                    record.label
                    if record is not None and record.kind is ProviderKind.OPENAI_COMPATIBLE
                    else described.get(slug, "This install's own inference server")
                ),
                hosted=slug != LOCAL_PROVIDER,
                switched_on=True if switched is None else switched[0],
                switched_by=None if switched is None else switched[1],
                switched_at=None if switched is None else switched[2],
                key_held=None if slug == LOCAL_PROVIDER else slug in plan.held,
                credential=None if vault is None else vault[1].get(slug),
                registered=None if record is None else registered_view(record),
                disclosed=[
                    DisclosedView(category=category, told=CATEGORY_TOLD[category], attempts=count)
                    for category, count in sorted(sent.get(slug, {}).items())
                ],
            )
        )
    skipped = {(one.rung.tier, one.rung.position): one for one in plan.assembly.skipped}
    ladder = {(one.tier, one.position): one for one in plan.state.rungs}
    rows = matrix(chain_of(plan.state.rungs), plan.health, reach, now=now)
    rungs = []
    for row in rows:
        rung = ladder[(row.tier, row.position)]
        left_out = skipped.get((row.tier, row.position))
        stored = rings.get(row.deployment_id)
        rungs.append(
            RungStateView(
                rung_id=rung.rung_id,
                tier=row.tier.value,
                position=row.position,
                role=row.role.value,
                deployment_id=row.deployment_id,
                provider=row.provider,
                model=row.model,
                enabled=rung.enabled,
                answers=left_out is None and rung.enabled,
                skipped_because=None if left_out is None else left_out.reason,
                told=None if left_out is None else left_out.told,
                state=row.state,
                measured=row.measured,
                unhealthy_because=(
                    None if row.unhealthy_because is None else row.unhealthy_because.value
                ),
                live_seen=row.live_seen,
                live_failed=row.live_failed,
                probes_seen=0 if stored is None else len(stored.probe),
                probes_failed=0 if stored is None else sum(1 for p in stored.probe if not p.ok),
                last_probe_at=None if stored is None else stored.last_probe_at,
                last_live_at=None if stored is None else stored.last_live_at,
                key_refused=row.deployment_id in refused,
            )
        )
    return ProvidersView(
        profile=normalised_profile(plan.profile),
        providers=providers,
        items=providers,
        rungs=rungs,
        exhausted_tiers=[one.value for one in exhausted_tiers(rows)],
        editable=may_switch(reach, now),
        vault=None if vault is None else vault[0],
        vault_told=None if vault is None else VAULT_TOLD[vault[0]],
        tiers=tier_views(plan.tiers),
        residency=residency or [],
        depth_alerts=alerts or [],
        profile_editable=profile_editable,
    )


def check_value(view: CheckView) -> dict[str, Any]:
    """What a test leaves in its setting row: how it ended and the model. Never the reply or the
    sentence, which is product text a later release may reword."""
    return {"answered": view.answered, "outcome": view.outcome, "model": view.model}


def checks_from(states: Mapping[str, SettingState]) -> dict[str, LastCheckView]:
    """Each provider's last test, from its `provider_check` row. A row this release cannot read
    is no test rather than a guessed one."""
    found: dict[str, LastCheckView] = {}
    for slug, state in states.items():
        value = state.value
        if not isinstance(value, dict):
            continue
        answered, outcome, model = value.get("answered"), value.get("outcome"), value.get("model")
        if not isinstance(answered, bool) or not isinstance(outcome, str):
            continue
        found[slug] = LastCheckView(
            answered=answered,
            outcome=outcome,
            model=model if isinstance(model, str) else None,
            at=state.updated_at,
        )
    return found


def answered_by(provider: str, since: datetime) -> Select[tuple[int]]:
    """How many requests since `since` the metadata ledger records as answered by `provider`.

    The row's `provider` is the one provider every answered call of the request named, so a count
    over it is the requests this provider answered. Bounded below by `received_at`, the ledger's
    partition key, so the window reads the partitions it covers.
    """
    return select(func.count()).where(
        RequestTelemetryRow.provider == provider, RequestTelemetryRow.received_at >= since
    )


def stats_view(provider: str, *, answered: int, cost_recorded: bool) -> ProviderStatsView:
    """One provider's figures: what it answered, and failures and cost named as not recorded.

    See `A_PROVIDERS_FIGURES_ARE_READ_FROM_THE_LEDGER` for why failures are not a number here.
    """
    return ProviderStatsView(
        provider=provider,
        days=STATS_DAYS,
        answered=answered,
        failures=None,
        cost_minor=None,
        unrecorded=[
            UnrecordedView(figure="failures", why=FAILURES_ARE_NOT_ATTRIBUTED),
            UnrecordedView(
                figure="model_cost",
                why=COST_IS_NOT_SPLIT_BY_PROVIDER if cost_recorded else NO_COST_RECORDED,
            ),
        ],
    )


def _level(rungs: Iterable[LadderRung], tier: Tier) -> list[LadderRung]:
    """One level's live rungs in the order a question tries them."""
    return sorted((one for one in rungs if one.tier is tier), key=lambda one: one.position)


def routing_export(
    plan: Planned, switches: Mapping[str, tuple[bool, str, datetime]], *, at: datetime
) -> RoutingExportView:
    """The routing configuration as one document: steps numbered from 1 in each level, providers
    as the product lists them, and the levels' numbers. See `AN_EXPORT_CARRIES_NO_KEY`."""
    records = {one.slug: one for one in plan.state.providers}
    steps = [
        ExportedStep(
            tier=tier.value,
            step=number,
            provider=rung.provider,
            model=rung.model,
            attempts=rung.attempts,
            timeout_seconds=rung.timeout_seconds,
            max_concurrency=rung.max_concurrency,
            enabled=rung.enabled,
        )
        for tier in TIER_LADDER
        for number, rung in enumerate(_level(plan.state.rungs, tier), start=1)
    ]
    providers = [
        ExportedProvider(
            provider=slug,
            switched_on=True if slug not in switches else switches[slug][0],
            registered=None if slug not in records else registered_view(records[slug]),
        )
        for slug in listed_providers(plan)
    ]
    return RoutingExportView(
        filename=EXPORT_FILENAME,
        generated_at=at,
        profile=normalised_profile(plan.profile),
        steps=steps,
        providers=providers,
        tiers=tier_views(plan.tiers),
    )


def check_tier(plan: Planned, provider: str) -> Tier | None:
    """The cheapest tier holding an answering rung for this provider that is in rotation, or None.

    A rung taken out of rotation on the Routing screen stays in the answering chain so the chain
    skips it as disabled, and a check sent to a tier holding only such rungs would be refused by
    the chain and read as a resting breaker. So it is not a tier to check.
    """
    chain = plan.assembly.for_provider(provider)
    for tier in TIER_LADDER:
        if any(one.deployment.enabled for one in chain.rungs_for(tier)):
            return tier
    return None


def refused_keys(rows: Iterable[tuple[str, datetime | None, int | None]]) -> frozenset[str]:
    """The deployments whose latest finished attempt was refused as a key, from rows in order.

    The latest word per deployment and not any word, so a key replaced and answered since is not
    still marked refused. Rows arrive in finishing order (`model_service.recent_statuses`).
    """
    latest: dict[str, int | None] = {}
    for deployment, finished_at, status in rows:
        if finished_at is not None:
            latest[deployment] = status
    return frozenset(one for one, status in latest.items() if status in KEY_REFUSED_STATUSES)


def names_the_provider(plan: Planned, provider: str) -> bool:
    """Whether any live step names this provider, answering or left out."""
    return any(one.provider == provider for one in plan.state.rungs)


def unladdered_rung(plan: Planned, provider: str) -> LadderRung | None:
    """The one step a check adds for a provider no step names: its default model, or None.

    At `CHECK_LEVEL` with the numbers a default step carries (`default_ladder.default_rung`), so
    the call is the one a default step would make. None when the product names no default model
    and the provider's registry row lists none. See `A_KEY_IS_CHECKED_BEFORE_ANY_STEP_USES_IT`.
    """
    record = next((one for one in plan.state.providers if one.slug == provider), None)
    model = default_model(provider, () if record is None else record.models)
    if model is None:
        return None
    step = default_rung(provider, CHECK_LEVEL, model)
    return LadderRung(
        rung_id=UNLADDERED_RUNG_ID,
        tier=step.tier,
        position=step.position,
        deployment_id=step.deployment_id,
        provider=step.provider,
        model=step.model,
        attempts=step.attempts,
        timeout_seconds=step.timeout_seconds,
        max_concurrency=step.max_concurrency,
        enabled=True,
    )


# ------------------------------------------------------------------------- the wiring


def models_of(request: Request) -> ModelService:
    """The executor this process built, or a process-level fault identical for every caller."""
    found = getattr(request.app.state, "models", None)
    if not isinstance(found, ModelService):
        raise Failed("no model service on this process")
    return found


def _sessions(request: Request) -> async_sessionmaker[AsyncSession] | None:
    found = getattr(request.app.state, "db_sessions", None)
    return found if isinstance(found, async_sessionmaker) else None


async def _switches(request: Request) -> dict[str, tuple[bool, str, datetime]]:
    """Each switched provider's state, who switched it and when. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return {}
    async with factory() as session:
        states = await switch_states(session)
    return {
        name: (state.value is True, state.updated_by, state.updated_at)
        for name, state in states.items()
        if isinstance(state.value, bool)
    }


async def _disclosed(request: Request) -> dict[str, dict[DataCategory, int]]:
    """Attempts per provider and category of data sent. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return {}
    try:
        async with factory() as session:
            rows = (await session.execute(disclosures())).all()
    except Exception as exc:
        # A count that cannot be read is not a count of zero; the screen shows no counts.
        log.warning("models.disclosures_unreadable", error=type(exc).__name__)
        return {}
    return disclosure_counts([(str(p), str(c), int(n)) for p, c, n in rows])


async def _residency(request: Request) -> list[ResidencyConstraintView]:
    """The live residency constraints with their ids. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return []
    try:
        async with factory() as session:
            rows = (await session.execute(live_constraints())).scalars().all()
    except Exception as exc:
        log.warning("models.residency_unreadable", error=type(exc).__name__)
        return []
    return [
        ResidencyConstraintView(
            id=str(row.id),
            scope=dict(row.scope),
            allowed_regions=None if row.allowed_regions is None else list(row.allowed_regions),
            on_prem_only=row.on_prem_only,
            note=row.note,
            created_by=row.created_by,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def _alerts(request: Request, now: datetime) -> list[ChainDepthAlertView]:
    """The chain-depth alerts of the last `ALERT_WINDOW`. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return []
    try:
        async with factory() as session:
            rows = (await session.execute(recent_alerts(now - ALERT_WINDOW))).scalars().all()
    except Exception as exc:
        log.warning("models.depth_alerts_unreadable", error=type(exc).__name__)
        return []
    return [
        ChainDepthAlertView(
            raised_at=row.raised_at,
            level=row.level,
            tier=row.tier,
            depth=row.depth,
            served_by=row.served_by,
            reason=row.reason,
            trace_id=row.trace_id,
        )
        for row in rows
    ]


async def _refused(request: Request, now: datetime) -> frozenset[str]:
    """The deployments whose latest attempt was refused as a key. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return frozenset()
    try:
        async with factory() as session:
            rows = (await session.execute(recent_statuses(now - EVIDENCE_WINDOW))).all()
    except Exception as exc:
        # Statuses that cannot be read are not a refusal; the screen marks nothing.
        log.warning("models.statuses_unreadable", error=type(exc).__name__)
        return frozenset()
    return refused_keys(
        (str(deployment), finished, None if status is None else int(status))
        for deployment, finished, status in rows
    )


async def _checks(request: Request) -> dict[str, LastCheckView]:
    """Each provider's last test. Empty without a database, and empty when unreadable."""
    factory = _sessions(request)
    if factory is None:
        return {}
    try:
        async with factory() as session:
            states = await read_namespace(session, CHECK_NAMESPACE)
    except Exception as exc:
        # A test that cannot be read is no test; the list says "not tested" rather than failing.
        log.warning("models.checks_unreadable", error=type(exc).__name__)
        return {}
    return checks_from(values_under(states, CHECK_NAMESPACE))


async def _remember(request: Request, asked: Asked, provider: str, view: CheckView) -> None:
    """Keep this test as the provider's last, attributed for the ledger entry its row writes.

    A test whose row cannot be written is still answered: the person was sent the outcome, and
    the list goes on showing the test before it. See `A_TEST_IS_REMEMBERED_WHERE_ITS_SWITCH_IS`.
    """
    factory = _sessions(request)
    if factory is None:
        return
    try:
        async with factory() as session:
            await attribute(session, asked)
            await put(
                session,
                f"{CHECK_NAMESPACE}.{provider}",
                value_type=SettingType.JSON,
                value=check_value(view),
                description=f"The last test of {provider} from the console",
                updated_by=asked.caller.principal.id,
            )
            await session.commit()
    except Exception as exc:
        log.warning("models.check_not_remembered", error=type(exc).__name__)


async def _vault_for(
    request: Request, reach: EntitlementSet, now: datetime
) -> tuple[VaultState, dict[str, SlotView]] | None:
    """The vault's listing by provider, for a reader who may manage credentials, else None."""
    if not may_manage(reach, now):
        return None
    listed = await asyncio.to_thread(listing, credentials_of(request))
    by_provider = {slot.slot.rsplit("/", 1)[-1]: slot for slot in listed.slots}
    return listed.vault, by_provider


def _not_answerable() -> Absent:
    """The one refusal this router makes. Names the screen, never the caller or the grant."""
    return Absent(f"the {MODELS_SCREEN} screen's providers are not answerable for this caller")


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.credential_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _view(request: Request, asked: Asked, calls: ModelCalls) -> ProvidersView:
    plan = await calls.planned()
    return providers_view(
        plan,
        switches=await _switches(request),
        reach=asked.reach,
        now=asked.now,
        vault=await _vault_for(request, asked.reach, asked.now),
        disclosed=await _disclosed(request),
        residency=await _residency(request),
        alerts=await _alerts(request, asked.now),
        profile_editable=may_configure(asked.reach, asked.now),
        refused=await _refused(request, asked.now),
        checks=await _checks(request),
    )


def switchable(plan: Planned) -> tuple[str, ...]:
    """Every provider a switch or a check may name: built in, added, and the local server."""
    return listed_providers(plan)


#: What the providers list may be searched, filtered and ordered by: the product's order, or name.
PROVIDERS: Final[Listing[ProviderStateView]] = Listing(
    name="model-providers",
    columns=(
        Column("listed", lambda row: row.listed, sort=True),
        Column("provider", lambda row: row.provider, search=True, filter=True, sort=True),
        Column("description", lambda row: row.description, search=True),
        Column("switched_on", lambda row: row.switched_on, filter=True),
        Column("key_held", lambda row: row.key_held, filter=True),
    ),
    key=lambda row: row.provider,
    order="listed",
)
ProvidersQuery = Annotated[ListAsked, Depends(PROVIDERS.query())]


router = APIRouter(prefix=API_PREFIX, tags=["models"])


@router.get("/models/providers", response_model=ProvidersView, responses=COMMON_RESPONSES)
async def providers(request: Request, asked: Asked, listed: ProvidersQuery) -> ProvidersView:
    """Every provider, the page of them matching the list's question as `items`, and every live
    rung, as the next call will see them. The question narrows `items` alone: `providers` and the
    steps are the whole of the plan."""
    if not may_read(asked.reach, asked.now):
        log.info("providers not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = PROVIDERS.plan(listed, reader=asked.caller.principal.id)
    view = await _view(request, asked, models_of(request).calls)
    page = plan.page(view.providers)
    return view.model_copy(update={"items": list(page.items), "next_cursor": page.next_cursor})


@router.get(
    "/models/providers/{provider}/stats",
    response_model=ProviderStatsView,
    responses=COMMON_RESPONSES,
)
async def provider_stats(request: Request, provider: str, asked: Asked) -> ProviderStatsView:
    """One provider's answered requests over `STATS_DAYS`, with failures and cost named as not
    recorded. A provider that does not exist is refused as one the reader may not see."""
    if not may_read(asked.reach, asked.now):
        log.info("provider stats not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = await models_of(request).calls.planned()
    if provider not in listed_providers(plan):
        raise _not_answerable()
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    since = asked.now - timedelta(days=STATS_DAYS)
    async with factory() as session:
        answered = (await session.execute(answered_by(provider, since))).scalar_one()
    return stats_view(provider, answered=int(answered), cost_recorded=RUN_SPEND_IS_RECORDED)


@router.get("/routing/export", response_model=RoutingExportView, responses=COMMON_RESPONSES)
async def export_routing(request: Request, asked: Asked) -> RoutingExportView:
    """The routing configuration as one document, without keys (M27.15.38).

    Answered to a reader of the providers, who is already shown every step and every provider's
    terms; see `AN_EXPORT_CARRIES_NO_KEY` for what it leaves out.
    """
    if not may_read(asked.reach, asked.now):
        log.info("routing export not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = await models_of(request).calls.planned()
    return routing_export(plan, await _switches(request), at=datetime.now(UTC))


@router.put(
    "/models/providers/{provider}", response_model=ProvidersView, responses=COMMON_RESPONSES
)
async def switch(
    request: Request, provider: str, body: ProviderSwitchAsked, asked: Asked
) -> ProvidersView:
    """Switch one provider on or off, and answer with the plan the next call will make."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider switch refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    known = switchable(await models_of(request).calls.planned())
    if provider not in known:
        log.info("provider switch names no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        # Who, at what reach, in which request, for the ledger entry the setting's trigger writes.
        await attribute(session, asked)
        await switch_provider(
            session, provider, on=body.on, by=asked.caller.principal.id, known=known
        )
        await session.commit()
    log.info(
        "provider switched", provider=provider, on=body.on, principal=asked.caller.principal.id
    )
    return await _view(request, asked, models_of(request).calls)


@router.put("/models/profile", response_model=ProvidersView, responses=COMMON_RESPONSES)
async def choose_profile(request: Request, body: ProfileAsked, asked: Asked) -> ProvidersView:
    """Choose where answers are made, and answer with the plan the next call will make.

    The authority first and the database second, as a switch does. The saved values are read back
    in the same transaction and held for this process, so the plan this answers with is already
    the new one. See `WHERE_ANSWERS_ARE_MADE_IS_AN_INSTALLATION_SETTING_AND_NOT_A_SWITCH`.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("model profile change refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        # Who, at what reach, in which request, for the ledger entry the setting's trigger writes.
        await attribute(session, asked)
        await save(session, {PROFILE_SETTING: body.profile}, updated_by=asked.caller.principal.id)
        saved = await load(session)
        await session.commit()
    hold_saved(saved)
    log.info("model profile chosen", profile=body.profile, principal=asked.caller.principal.id)
    return await _view(request, asked, models_of(request).calls)


@router.post(
    "/models/providers/{provider}/check", response_model=CheckView, responses=COMMON_RESPONSES
)
async def check(request: Request, provider: str, asked: Asked) -> CheckView:
    """Send one fixed sentence through this provider, metered: its first answering step, or its
    default model when no step names it. See `A_KEY_IS_CHECKED_BEFORE_ANY_STEP_USES_IT`."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider check refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    calls = models_of(request).calls
    plan = await calls.planned()
    if provider not in switchable(plan):
        log.info("provider check names no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    view = await checked_through(
        calls,
        plan,
        provider,
        origin=Origin(
            trace_id=_trace_id(), principal=asked.caller.principal, channel=asked.channel
        ),
        at=asked.now,
        entitlement_hash=asked.reach.ent_hash(),
        recorders=getattr(request.app.state, "request_recorders", ()),
    )
    await _remember(request, asked, provider, view)
    log.info(
        "provider checked",
        provider=provider,
        outcome=view.outcome,
        default_model=view.default_model,
        principal=asked.caller.principal.id,
    )
    return view


async def checked_through(
    calls: ModelCalls,
    plan: Planned,
    provider: str,
    *,
    origin: Origin,
    at: datetime,
    entitlement_hash: str,
    recorders: Iterable[RequestRecorder],
) -> CheckView:
    """One provider checked as the Test button checks it: the call, and its row and its cost.

    The route's body after the authority and before the test is remembered, taken out so the
    install's acceptance check sends exactly the call an administrator's press sends (M5.7.1),
    as `brain.api_routes.answered_for` is taken out of `/answer` for a chat channel. `plan` is
    the one the provider was found in; `recorders` are the process's, of which the ledger's row
    and the cost are kept (M27.12.5), because a check is a billed call and not a question.
    """
    meter = Meter()
    added = None if names_the_provider(plan, provider) else unladdered_rung(plan, provider)
    if added is not None:
        # A copy of the ladder with the one step added, planned as a step would be. Its attempt
        # row would name no step, so none is written; the meter and the ledger row still are.
        calls = calls.trying(lambda rungs: (*rungs, added), attempts=NoAttempts())
        plan = await calls.planned()
    tier = check_tier(plan, provider)
    view = await _checked(
        calls,
        plan,
        provider,
        tier,
        meter=meter,
        trace_id=origin.trace_id,
        default=None if added is None else added.model,
    )
    kept: tuple[RequestRecorder, ...] = tuple(
        one for one in recorders if isinstance(one, TelemetryRecorder | UsageRecorder)
    )
    await finish(
        kept,
        Finished(
            origin=origin,
            at=at,
            outcome=ModelCallOutcome(answered=view.answered),
            completed_at=datetime.now(UTC),
            entitlement_hash=entitlement_hash,
            lane=Lane.ANSWER,
            tool_calls=0,
            model_usage=meter.usage(),
        ),
    )
    return view


def failure_outcome(failure: DriverFailure) -> str:
    """How a check that failed ended, in the check's vocabulary.

    A content refusal first, because it carries no trigger and is the model's word rather than
    the provider's; then a refused key, by the provider's status; then the fallback trigger, or
    `stopped` for a failure that stopped the chain with none.
    """
    if failure.refused:
        return "refused"
    if failure.status in KEY_REFUSED_STATUSES:
        return "key_refused"
    trigger = failure.trigger
    return "stopped" if trigger is None else trigger.value


async def _checked(
    calls: ModelCalls,
    plan: Planned,
    provider: str,
    tier: Tier | None,
    *,
    meter: Meter,
    trace_id: str,
    default: str | None = None,
) -> CheckView:
    """The call and how it ended, in the check's vocabulary. Never raises a provider failure.

    `default` is the default model when no step names the provider, and every sentence then
    names it.
    """
    if tier is None:
        reasons = [one.reason for one in plan.assembly.skipped if one.rung.provider == provider]
        if reasons:
            return _unanswered(
                provider,
                reasons[0].value,
                TOLD[reasons[0]],
                status=None,
                trace_id=trace_id,
                default=default,
            )
        named = any(one.provider == provider for one in plan.assembly.answering)
        outcome = "out_of_rotation" if named else "no_model"
        return _unanswered(
            provider, outcome, CHECK_TOLD[outcome], status=None, trace_id=trace_id, default=default
        )
    try:
        response = await calls.complete(
            (DriverMessage(role=Role.USER, content=CHECK_PROMPT),),
            tier=tier,
            lane=Lane.ANSWER,
            meter=meter,
            trace_id=trace_id,
            max_output_tokens=CHECK_MAX_OUTPUT_TOKENS,
            provider=provider,
            categories=(DataCategory.CHECK_SENTENCE,),
        )
    except ProviderUnavailable as failed:
        outcome = failure_outcome(failed.failure)
        return _unanswered(
            provider,
            outcome,
            CHECK_TOLD[outcome],
            status=failed.failure.status,
            trace_id=trace_id,
            default=default,
        )
    except NoCompliantRoute:
        # Every step of this provider was resting behind an open breaker when the call planned.
        outcome = FallbackTrigger.CIRCUIT_OPEN.value
        return _unanswered(
            provider, outcome, CHECK_TOLD[outcome], status=None, trace_id=trace_id, default=default
        )
    return CheckView(
        provider=provider,
        answered=True,
        outcome="answered",
        told=answered_told(response.model, default_model=default is not None),
        served_by=response.deployment_id,
        model=response.model,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        status=None,
        trace_id=trace_id,
        default_model=default is not None,
    )


def _unanswered(
    provider: str,
    outcome: str,
    told: str,
    *,
    status: int | None,
    trace_id: str,
    default: str | None = None,
) -> CheckView:
    return CheckView(
        provider=provider,
        answered=False,
        outcome=outcome,
        told=told if default is None else default_model_told(told, default),
        served_by=None,
        model=default,
        tokens_in=None,
        tokens_out=None,
        status=status,
        trace_id=trace_id,
        default_model=default is not None,
    )


# ------------------------------------------------------------------------------ the prices
#: Said when a price is set before the install has a currency to set it in.
A_PRICE_NEEDS_THE_INSTALLS_CURRENCY: Final = (
    "Choose the install's currency on Install, Settings first. A price is kept in that currency, "
    "and one set in none would be counted in whichever currency is chosen later."
)


class ModelPriceView(BaseModel):
    """One model: whether the ladder uses it, its price, and whether a call to it is costed.

    `costed` is true only for a price in the install's currency; a model with no price, or one
    priced in another currency, is not costed, and its calls leave no cost row.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str
    on_ladder: bool
    input_minor_per_million: str | None
    output_minor_per_million: str | None
    currency: str | None
    costed: bool


class PricesView(BaseModel):
    """Every model the ladder names or a price names, in provider then model order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str
    models: list[ModelPriceView]


class PriceAsked(BaseModel):
    """One model's price: minor units of the install's currency per million tokens, as text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Annotated[str, Field(pattern=SLUG_PATTERN)]
    model: Annotated[str, Field(pattern=MODEL_NAME_PATTERN)]
    input_minor_per_million: Annotated[str, Field(min_length=1, max_length=24)]
    output_minor_per_million: Annotated[str, Field(min_length=1, max_length=24)]

    @field_validator("input_minor_per_million", "output_minor_per_million")
    @classmethod
    def _a_price(cls, value: str) -> str:
        try:
            decimal_of(value)
        except PricingError as refused:
            raise ValueError(str(refused)) from None
        return value.strip()


def price_views(
    plan: Planned, prices: Mapping[tuple[str, str], Price], *, currency: str
) -> list[ModelPriceView]:
    """Each model on the ladder or priced, with its price and whether its calls are costed."""
    ladder = {(one.provider, one.model) for one in plan.state.rungs}
    views = []
    for provider, model in sorted(ladder | set(prices)):
        price = prices.get((provider, model))
        views.append(
            ModelPriceView(
                provider=provider,
                model=model,
                on_ladder=(provider, model) in ladder,
                input_minor_per_million=None if price is None else str(price.input_minor),
                output_minor_per_million=None if price is None else str(price.output_minor),
                currency=None if price is None else price.currency,
                costed=price is not None and price.currency == currency,
            )
        )
    return views


async def _prices_view(request: Request) -> PricesView:
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    plan = await models_of(request).calls.planned()
    async with factory() as session:
        prices = await read_prices(session)
    code = install_currency()
    return PricesView(currency=code, models=price_views(plan, prices, currency=code))


@router.get("/models/prices", response_model=PricesView, responses=COMMON_RESPONSES)
async def model_prices(request: Request, asked: Asked) -> PricesView:
    """Every model on the ladder or priced, with what a million tokens cost on it."""
    if not may_read(asked.reach, asked.now):
        log.info("model prices not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return await _prices_view(request)


@router.put("/models/prices", response_model=PricesView, responses=COMMON_RESPONSES)
async def set_model_price(request: Request, body: PriceAsked, asked: Asked) -> Response:
    """Set one model's price in the install's currency, and answer with every model's.

    The authority first, then the provider's name, then the currency, then the database, which is
    the switch's own order. See `A_PRICE_NEEDS_THE_INSTALLS_CURRENCY`.
    """
    if not may_switch(asked.reach, asked.now):
        log.info("model price refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    if body.provider not in switchable(await models_of(request).calls.planned()):
        log.info("model price names no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    code = install_currency()
    if code == NO_CURRENCY:
        return refused_request(
            [
                {
                    "loc": ("body", "currency"),
                    "type": "value_error",
                    "msg": A_PRICE_NEEDS_THE_INSTALLS_CURRENCY,
                }
            ],
            _trace_id(),
        )
    price = Price(
        input_minor=decimal_of(body.input_minor_per_million),
        output_minor=decimal_of(body.output_minor_per_million),
        currency=code,
    )
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        # Who, at what reach, in which request, for the ledger entry the setting's trigger writes.
        await attribute(session, asked)
        await set_price(session, body.provider, body.model, price, by=asked.caller.principal.id)
        await session.commit()
    log.info(
        "model priced",
        provider=body.provider,
        model=body.model,
        principal=asked.caller.principal.id,
    )
    return JSONResponse((await _prices_view(request)).model_dump(mode="json"))
