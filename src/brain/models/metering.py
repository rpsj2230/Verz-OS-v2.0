"""What one request's model calls consumed, counted as they happen and summed once.

`brain.ops.telemetry.RequestTelemetry` has declared `model`, `provider`, `tokens_in`,
`tokens_out`, `fallback_count`, `retry_count` and `agent_version` since M27.1.5, and every row
held None in each because nothing called a model. `brain.models.calls.ModelCalls` calls one now,
and this is where a call's cost lands on its way to that row. **There is one copy of the tokens
and it is the request's ledger row**: no second usage table, no counter on a provider, no figure
on a spend row that could disagree with it. A report that wants tokens by department joins that
row to the question row the same request left, on the trace and the person, which is
`brain.console.usage_screen`'s read.

**A meter belongs to one request and is handed to every call that request makes.** Nothing here
is global and nothing reads a context variable: a meter found by looking it up is a meter a call
can find the wrong one of, and a token count filed under a request that did not spend it is a
figure about somebody else's question. `ModelCalls.complete` takes the meter as a required
argument, so a call cannot be made without saying whose it is.

**Tokens are what the provider reported, summed over the calls that answered.** A call that
failed reported nothing and is counted as an attempt, a retry or a fallback, never as tokens:
a provider may bill a request that timed out on our side, and a figure built from our guess at
that would be a number nobody can reconcile against the invoice. See
`TOKENS_ARE_THE_PROVIDERS_COUNT_AND_A_FAILED_CALL_REPORTED_NONE`.

**A request that two models answered names neither.** The ledger row has one `model` column and
a request can make several calls. Summing the tokens is right whichever models served them;
naming one model beside the sum files the other model's tokens under it. So the row names a
model, a provider or an agent only when every call that answered agrees, and None otherwise,
which is `brain.ops.telemetry.A_TRACE_THAT_NAMES_TWO_SHAPES_NAMES_NONE` applied to a request's
own calls. See `A_REQUEST_ANSWERED_BY_TWO_MODELS_NAMES_NONE`.

**A retry and a fallback are counted where they are decided**, by the executor, rather than
derived here from a list of outcomes: a second attempt on one rung and a first attempt on the
next rung are both "the second call", and only the code that chose between them knows which it
was.

Scope: pure. Nothing here performs I/O or reads a clock.

Task ids: M27.7.14, M27.1.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brain.models.driver import DriverResponse

# ------------------------------------------------------------------- written-down reasons

#: Why a failed call contributes no tokens.
TOKENS_ARE_THE_PROVIDERS_COUNT_AND_A_FAILED_CALL_REPORTED_NONE: Final = (
    "A token count on the ledger is the provider's own figure from a response that came back. A "
    "call that failed came back with none, so it adds nothing to the sum and is counted as an "
    "attempt instead. Estimating what a timed-out call might have been billed would put a number "
    "on a five-year row that no invoice will ever match."
)

#: Why a request whose calls disagree about the model names none.
A_REQUEST_ANSWERED_BY_TWO_MODELS_NAMES_NONE: Final = (
    "The ledger row has one model column and a request may make several calls. The tokens are "
    "summed whichever model served them, and naming one model beside that sum files the other "
    "model's tokens under it, which a report by model then shows as fact. So a model, a "
    "provider or an agent is named only when every call that answered agrees, and None otherwise."
)


class MeteringError(ValueError):
    """Raised when a call is recorded in a way no ledger row should be built from."""


@dataclass(frozen=True)
class ModelUsage:
    """One request's model calls, as its ledger row holds them.

    `calls` is how many calls were attempted, answered or not, and is what says a model was
    reached for at all: a request that attempted three calls and got no answer has `calls=3` and
    zero tokens, which is a different fact from a request that called no model, which has no
    `ModelUsage` at all.
    """

    calls: int
    tokens_in: int
    tokens_out: int
    model: str | None
    provider: str | None
    agent_version: str | None
    fallback_count: int
    retry_count: int

    def __post_init__(self) -> None:
        counts = (self.calls, self.tokens_in, self.tokens_out, self.fallback_count)
        if any(one < 0 for one in (*counts, self.retry_count)):
            msg = f"a model usage with a negative count is a subtraction that went wrong: {self}"
            raise MeteringError(msg)
        if self.calls < 1:
            msg = "a usage with no call is a request that called no model, which carries none"
            raise MeteringError(msg)
        if self.fallback_count + self.retry_count > self.calls - 1:
            msg = (
                f"{self.fallback_count} fallbacks and {self.retry_count} retries cannot come out "
                f"of {self.calls} calls: every one of them is a call after the first"
            )
            raise MeteringError(msg)


def _agreed(values: list[str | None]) -> str | None:
    """The one value every answered call names, or None when they differ or name nothing."""
    distinct = set(values)
    if len(distinct) != 1:
        return None
    return next(iter(distinct))


class Meter:
    """The calls one request made. Handed to every call, read once when the request finishes."""

    def __init__(self) -> None:
        self._attempts = 0
        self._retries = 0
        self._fallbacks = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._models: list[str | None] = []
        self._providers: list[str | None] = []
        self._agents: list[str | None] = []

    def attempted(self) -> None:
        """A call was sent. Counted before it returns, so a call that raised still counts."""
        self._attempts += 1

    def retried(self) -> None:
        """This attempt is on the rung whose previous attempt just failed. Called with it."""
        self._retries += 1

    def fell_back(self) -> None:
        """This attempt is on a later rung than the one that failed. Called with it."""
        self._fallbacks += 1

    def answered(
        self, response: DriverResponse, *, provider: str, agent_version: str | None
    ) -> None:
        """A call came back. Its tokens are the provider's count; see the reason constants."""
        if self._attempts < 1:
            msg = "an answer was recorded before any attempt was, so a call went uncounted"
            raise MeteringError(msg)
        self._tokens_in += response.usage.input_tokens
        self._tokens_out += response.usage.output_tokens
        self._models.append(response.model)
        self._providers.append(provider)
        self._agents.append(agent_version)

    def usage(self) -> ModelUsage | None:
        """What the ledger row records, or None when this request called no model."""
        if self._attempts == 0:
            return None
        return ModelUsage(
            calls=self._attempts,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            model=_agreed(self._models),
            provider=_agreed(self._providers),
            agent_version=_agreed(self._agents),
            fallback_count=self._fallbacks,
            retry_count=self._retries,
        )
