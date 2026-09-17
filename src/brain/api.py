"""Conventions every endpoint follows.

Written once, here, because a convention that each route implements for itself is a
convention that holds until someone is in a hurry. Three things:

**One error shape.** Every failure returns the same body, so a client parses one thing.
It carries the trace id, which is the only field that makes a support conversation short.

**One pagination shape.** Cursor, not offset. Offset pagination re-reads and re-filters on
every page, and under a permission predicate that means the same row can appear twice or
vanish between pages when someone's grants change mid-scroll. A cursor is a position in a
stable order.

**One request deadline**, distinct from the model's. A model call that takes ninety
seconds is slow; a request that takes ninety seconds is a held connection, and behind a
pooler with two hundred client slots, enough of those is an outage.

**And one refusal of a body that never repeats it**, for the routes that take a secret. See
`A_REFUSED_BODY_IS_NOT_ECHOED`.

**Every failing response carries a sentence and a reference, including the ones no route wrote.**
Until 2026-09-17 three ways out of this application skipped `ErrorBody`: an exception nothing
caught left as Starlette's plain-text `Internal Server Error`, a refused body or query as FastAPI's
`{"detail": [...]}` quoting what was sent, and an unmounted path or a wrong method as `{"detail":
"Not Found"}`. The console reads `message`, so on a staging install each reached a person as "That
did not work. Something went wrong." with no reference to quote. See
`A_FAILURE_WITHOUT_A_SENTENCE_IS_A_FAILURE_NOBODY_CAN_REPORT`, `refused_request` and
`unexpected_failure`, which `brain.app` installs for every route.

Task ids: M31.1.2.4, M31.1.4.1, M31.1.4.3, M31.1.4.4, M27.8.7, M27.9.6
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

import structlog
from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from brain.core.errors import Absent

log = structlog.get_logger()

#: Every route lives under this. A version in the path rather than a header, because a
#: version you cannot see in a log line is a version nobody can debug.
API_PREFIX = "/api/v1"


#: Why the error shape carries no outcome, and why removing the field was not a tidy-up.
#:
#: This model used to carry `outcome: str` described as "denied, absent, unresolved,
#: degraded, failed". `brain.app.handle_brain_error` maps DENIED and ABSENT to the same
#: status and the same body on purpose, because a caller who can tell "you may not see this"
#: from "this does not exist" can map what exists by asking, which is the whole leak the
#: taxonomy is built to prevent. Populating that field would have made the two
#: distinguishable in the one place a client actually reads.
#:
#: It never leaked, and the reason is worth stating rather than being relieved about: the
#: handler has never returned this model. A documented error shape that nothing returns was
#: what kept the field harmless, which is a poor kind of safety, and the fix is to return the
#: model and delete the field rather than to keep both apart and hope.
A_REFUSAL_AND_AN_ABSENCE_LOOK_THE_SAME_TO_A_CLIENT = (
    "The status and the body are identical for DENIED and ABSENT. Anything that varies "
    "between them is a side channel, whatever it is called and however useful it would be "
    "in a log: a client that can tell a refusal from an absence can enumerate what exists "
    "by asking for things at random and reading which answer comes back. The trace id is "
    "safe to carry because it is minted per request and says nothing about what was asked "
    "for or who asked; the outcome is not, and is deliberately absent from this model."
)


class RequestProblemView(BaseModel):
    """One thing wrong with what was sent: where, a stable code, and what is wrong, in words.

    The shape the connectors, webhooks, notifications and data transfer refusals already used, so
    a console reading one reads them all. `message` is built from the kind of problem and the
    limit it broke, never from the value that broke it. See `A_REFUSED_BODY_IS_NOT_ECHOED`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(
        description="Where in what was sent, joined with dots, without body, query or path. "
        "Empty for what was sent as a whole."
    )
    code: str = Field(description="A stable code for the kind of problem.")
    message: str = Field(description="What is wrong, in words. Never the value that was sent.")


class ErrorBody(BaseModel):
    """The only error shape. Documented once and returned by everything.

    The trace id is the reason a person can get help: it is what somebody quotes so a run can be
    found in the ledger, and without it in the body a caller has to know to read a response header
    before they can be told anything useful.

    `problems` is filled on a refused request and empty otherwise. `second_factor_needed` is
    decided from the sign-in and the caller's own grants and never from what was asked for, so it
    is the same for every object in one session; see
    `brain.gate.admission.A_REFUSAL_TO_A_WEAK_SIGN_IN_IS_ABOUT_THE_SESSION`.

    There is no `outcome`. See `A_REFUSAL_AND_AN_ABSENCE_LOOK_THE_SAME_TO_A_CLIENT`.
    """

    message: str = Field(description="Safe to show a person. Never explains a refusal.")
    trace_id: str = Field(default="", description="Quote this and the run can be found.")
    #: Both of the fields below are left out of the JSON at their defaults, so a failure that
    #: has neither is the two-field document it always was and every reader of that keeps working.
    problems: list[RequestProblemView] = Field(
        default_factory=list,
        description="What was wrong with a refused request, by field. Absent when nothing was.",
        exclude_if=lambda value: not value,
    )
    second_factor_needed: bool = Field(
        default=False,
        description="True when this sign-in lacks a second factor that administration and "
        "approvals need. Decided from the session, never from what was asked for. Absent when "
        "false.",
        exclude_if=lambda value: value is False,
    )


class Page[T](BaseModel):
    """A page of results.

    `next_cursor` is null when there are no more. It is deliberately opaque: a client that
    can construct one has coupled itself to the ordering, and the ordering is ours to
    change.
    """

    items: list[T] = []
    next_cursor: str | None = None
    #: Absent unless it is cheap. A count behind a permission predicate costs a full scan,
    #: and "about 4,000" is not worth a second of someone's question.
    total: int | None = None


def encode_cursor(position: dict[str, Any]) -> str:
    """Opaque, not encrypted. It hides the shape, not a secret, never put a row a caller
    cannot see into one, because a cursor travels back and forth through the client."""
    return base64.urlsafe_b64encode(json.dumps(position, sort_keys=True).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """A malformed cursor is a client error, not a server one, and must not leak a
    traceback describing the ordering."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        value = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        msg = "malformed cursor"
        raise ValueError(msg) from exc
    if not isinstance(value, dict):
        msg = "malformed cursor"
        raise ValueError(msg)
    return value


class TimeoutMiddleware:
    """A deadline on the whole request, separate from any model or connector timeout.

    Returns 503 DEGRADED rather than 504: the caller's request did not time out, one of
    our dependencies did, and the taxonomy already has a word for that.

    **This existed, was tested, and was mounted by nothing until today.** `create_app`
    installed CORS, tracing and security headers and never this, so every request the
    deployed application has ever served ran without a deadline, while `M31.1.2.4` was
    closed and `Settings.request_timeout_seconds` sat at 30.0 read by nobody. The test that
    covered it constructed an application and attached the middleware itself, which is the
    shape that makes an unmounted mechanism look tested. `brain.app.create_app` now attaches
    it from the setting, and a test asserts the deployed stack contains it rather than
    asserting that it works when somebody adds it.

    It is attached innermost, inside the trace middleware, for two reasons. The trace id is
    bound by then, so a timed-out response carries the same id as the log line that recorded
    it; and the deadline covers the route rather than the response headers being written
    after it, which would count our own work against the caller's budget.
    """

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def __call__(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.seconds)
        except TimeoutError:
            elapsed = time.perf_counter() - started
            log.warning("request deadline exceeded", path=request.url.path, seconds=elapsed)
            return JSONResponse(
                status_code=503,
                # The bound id first, the caller's header as a fallback. Attached inside
                # the trace middleware, so a minted id is available here and the body
                # matches the `x-trace-id` header the caller gets back. Reading only the
                # request header would have answered "" for every caller who did not send
                # one, which is most of them.
                content=ErrorBody(
                    message="That took too long to answer. Nothing was changed.",
                    trace_id=str(
                        structlog.contextvars.get_contextvars().get("trace_id")
                        or request.headers.get("x-trace-id", "")
                    ),
                ).model_dump(),
            )


#: What every route under `API_PREFIX` must declare, so the generated schema documents one
#: shape rather than FastAPI's default per-route guess.
#:
#: **Attached to nothing today, and the previous comment said "attached to every route".**
#: There are no routes under `API_PREFIX` at all, so the sentence was true only in the
#: vacuous sense and read as a description of the deployed application. It is stated as an
#: obligation on routes rather than a claim about them until there are some.
#:
#: The health endpoints deliberately do not use it: they answer with `Health` and a 503 from
#: `/health/ready` means "a dependency is unreachable", which is a different thing from the
#: 503 here and would be a worse schema for saying so in the same words.
#:
#: `test_a_route_under_the_api_prefix_declares_the_common_error_shape` fails the day the
#: first route appears without it, rather than passing quietly over an empty list.
#:
#: **401 is here and it is not a hole in the taxonomy.** Every other entry describes an
#: answer to a question that was asked; a 401 says the credential was not acceptable, so no
#: question was ever put. It therefore cannot distinguish a refusal from an absence, because
#: it is decided before anything has been looked up and says nothing about what exists. What
#: it must not do is explain itself, and it does not: the body is the one sentence
#: `brain.identity.oidc.SIGN_IN_PROMPT` holds, whether the token was forged, expired,
#: minted for another audience, or belongs to somebody nobody has onboarded.
COMMON_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorBody,
        "description": "No acceptable credential. The reason is never given.",
    },
    404: {
        "model": ErrorBody,
        "description": "Absent, or present and not yours. Deliberately the same.",
    },
    409: {"model": ErrorBody, "description": "The name matched more than one thing."},
    503: {
        "model": ErrorBody,
        "description": "A source was unreachable. No stale value was substituted.",
    },
}


#: Why a refused request body is never repeated back to whoever sent it.
A_REFUSED_BODY_IS_NOT_ECHOED: Final = (
    "FastAPI answers a body its model refuses with a 422 whose every error carries the input it "
    "refused, so a setup code one character too long, or a credential posted in the wrong "
    "shape, comes straight back in the response and into whatever logs responses. Every refused "
    "request is answered by refused_request, which keeps each problem's location and kind and "
    "words it from the kind and the limit broken, and drops the input, the context and pydantic's "
    "own message, which quotes a list's length and can quote a validator's value. The location "
    "names a field the sender already knows; the input is the one thing the sender may not have "
    "meant to send. A validator's own sentence is kept only when no part of the input is in it."
)

#: The keys one problem carries. Nothing a later FastAPI or pydantic adds can join them, because
#: `RequestProblemView` forbids extra fields, which is the direction to fail in.
KEPT_ERROR_KEYS: Final = ("field", "code", "message")


class NoEchoRoute(APIRoute):
    """A route whose 422 names what was wrong and never repeats what was sent.

    **Kept, although every route now answers a refused request this way.** It was a route class
    rather than an exception handler because changing the body every other route's clients read
    was a different decision with a different owner; on 2026-09-17 that decision was made, and
    `brain.app` installs `refused_request` for the whole application. The class stays because the
    routers that take a secret are the ones where an echo matters most, and a route that catches
    its own refusal does not depend on the application having installed the handler: a router
    mounted on a bare `FastAPI` in a test, or on a second application, still never repeats a key.
    See `A_REFUSED_BODY_IS_NOT_ECHOED`.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def without_echo(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as refused:
                return refused_request(refused.errors(), bound_trace_id(request))

        return without_echo


# ------------------------------------------------------------ failures nothing else shaped
#: Why every failing response carries a sentence and a reference, whoever produced it.
A_FAILURE_WITHOUT_A_SENTENCE_IS_A_FAILURE_NOBODY_CAN_REPORT: Final = (
    "The console shows the message a failure carries and, when there is none, a fallback that "
    "says only that something went wrong. An exception no handler caught, a refused request, an "
    "unmounted path and a wrong method each left this application without ErrorBody, so each "
    "reached a person as the fallback with no reference, and the owner of a staging install saw "
    "that sentence on screen after screen with nothing to quote. Every one is shaped here: a "
    "sentence that explains nothing about data, the trace id the log line carries, and for a "
    "refused request the fields in words. The exception's own text goes to the log and never to "
    "the body, because it quotes values: a database refusal names the key it collided on."
)

#: What a person is told when the server failed in a way nothing expected.
UNEXPECTED_FAILURE: Final = (
    "Something failed on the server while answering this. Quote the reference and the failure "
    "can be found in the server's log."
)

#: What a refused request is told as a whole. `problems` says which parts.
NOT_ACCEPTED: Final = "Some of what was sent was not accepted, and nothing was changed."

#: What a request the application does not serve that way is told, by status. A 404 is not here:
#: `brain.app` answers it with `brain.core.errors.Absent`'s own sentence, so an address that does
#: not exist and a record that is refused are one answer.
STATUS_SENTENCES: Final[Mapping[int, str]] = MappingProxyType(
    {
        400: "That request could not be read.",
        405: "That address does not take that kind of request.",
        406: "That address cannot answer in the form that was asked for.",
        413: "That was too large to send.",
        415: "That was sent in a form this address does not read.",
        422: NOT_ACCEPTED,
        429: "Too many requests arrived too quickly. Wait a moment and try again.",
    }
)

#: The sentence for a 4xx `STATUS_SENTENCES` does not name.
NOT_ACCEPTED_STATUS: Final = "That request was not accepted."

#: Where a problem was found, as FastAPI names it, which the field leaves out.
_SOURCES: Final = frozenset({"body", "query", "path", "header", "cookie"})

#: A problem's words by its kind, where the kind alone says what to do.
_WORDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "missing": "This is required.",
        "extra_forbidden": "This is not something this address takes.",
        "json_invalid": "What was sent is not valid JSON.",
        "json_type": "This should be JSON.",
        "model_type": "This should be an object with named fields.",
        "model_attributes_type": "This should be an object with named fields.",
        "dict_type": "This should be an object with named fields.",
        "list_type": "This should be a list.",
        "tuple_type": "This should be a list.",
        "set_type": "This should be a list without repeats.",
        "string_type": "This should be text.",
        "string_unicode": "This should be text.",
        "string_pattern_mismatch": "This is not in the form this address expects.",
        "int_type": "This should be a whole number.",
        "int_parsing": "This should be a whole number.",
        "int_from_float": "This should be a whole number.",
        "float_type": "This should be a number.",
        "float_parsing": "This should be a number.",
        "decimal_type": "This should be a number.",
        "decimal_parsing": "This should be a number.",
        "finite_number": "This should be a finite number.",
        "bool_type": "This should be true or false.",
        "bool_parsing": "This should be true or false.",
        "uuid_type": "This should be an identifier in UUID form.",
        "uuid_parsing": "This should be an identifier in UUID form.",
        "datetime_type": "This should be a date and time.",
        "datetime_parsing": "This should be a date and time.",
        "datetime_from_date_parsing": "This should be a date and time.",
        "timezone_aware": "This should be a date and time with its time zone.",
        "date_type": "This should be a date.",
        "date_parsing": "This should be a date.",
        "date_from_datetime_parsing": "This should be a date.",
        "url_type": "This should be a web address.",
        "url_parsing": "This should be a web address.",
        "url_scheme": "This web address uses a scheme this address does not accept.",
        "enum": "This is not one of the choices this address accepts.",
        "literal_error": "This is not one of the choices this address accepts.",
        "union_tag_invalid": "This is not one of the kinds this address accepts.",
        "none_required": "This should be left empty.",
    }
)

#: Words that name the limit a value broke, filled from the limit and never from the value.
_LIMITS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "string_too_short": ("min_length", "This should be at least {} characters."),
        "string_too_long": ("max_length", "This should be at most {} characters."),
        "too_short": ("min_length", "This should have at least {} entries."),
        "too_long": ("max_length", "This should have at most {} entries."),
        "greater_than": ("gt", "This should be greater than {}."),
        "greater_than_equal": ("ge", "This should be at least {}."),
        "less_than": ("lt", "This should be less than {}."),
        "less_than_equal": ("le", "This should be at most {}."),
        "multiple_of": ("multiple_of", "This should be a multiple of {}."),
    }
)

#: What a problem of a kind nothing above names is told.
NOT_THIS_VALUE: Final = "This value was not accepted."

#: The kinds whose own message a validator wrote, and so may be shown if it does not quote.
_WRITTEN_BY_A_VALIDATOR: Final = frozenset({"value_error", "assertion_error"})


def problem_field(loc: Sequence[object], kind: str) -> str:
    """Where a problem is, as a person filling a form would name it.

    The source FastAPI puts first is dropped, because a form does not know whether a value
    travelled in the body or the query. A JSON document that does not parse is reported at the
    character it failed on, which is no field at all, so it is the request as a whole. A key the
    model does not declare is named as its field, which is the location `NoEchoRoute` always kept:
    it is a name the sender chose and already knows, and a console that sent a column the API does
    not take is told which one. Its value is never in the answer.
    """
    if kind == "json_invalid":
        return ""
    parts = [str(one) for one in loc]
    if parts and parts[0] in _SOURCES:
        parts = parts[1:]
    return ".".join(parts)


def _leaves(value: object) -> Iterator[str]:
    """Every scalar inside a refused value, as text, for asking whether a message quotes it."""
    if isinstance(value, Mapping):
        for key, one in value.items():
            yield str(key)
            yield from _leaves(one)
    elif isinstance(value, list | tuple | set | frozenset):
        for one in value:
            yield from _leaves(one)
    elif value is not None and not isinstance(value, bool):
        yield str(value)


def problem_words(error: Mapping[str, Any]) -> str:
    """One problem in words, from its kind and its limit, and never containing what was sent.

    A validator's own sentence is kept only when no scalar of the refused input appears in it. A
    single character of input appears in almost every sentence, so a short value usually costs the
    validator's wording and falls back to `NOT_THIS_VALUE`, which is the direction to fail in.
    """
    kind = str(error.get("type", ""))
    context = error.get("ctx") or {}
    if kind in _LIMITS:
        key, sentence = _LIMITS[kind]
        if key in context:
            return sentence.format(context[key])
    if kind in _WORDS:
        return _WORDS[kind]
    if kind in _WRITTEN_BY_A_VALIDATOR:
        written = str(error.get("msg", ""))
        for prefix in ("Value error, ", "Assertion failed, "):
            written = written.removeprefix(prefix)
        quoted = any(leaf and leaf in written for leaf in _leaves(error.get("input")))
        if written.strip() and not quoted:
            return written
    return NOT_THIS_VALUE


def refused_request(errors: Sequence[Mapping[str, Any]], trace_id: str) -> JSONResponse:
    """A refused body, query or path, as `ErrorBody` with its problems in words. Status 422.

    Nothing of the input, the context or the url pydantic attaches leaves here, which is what
    `NoEchoRoute` did for the routes that take a secret and what every route now does.
    """
    body = ErrorBody(
        message=NOT_ACCEPTED,
        trace_id=trace_id,
        problems=[
            RequestProblemView(
                field=problem_field(error.get("loc", ()), str(error.get("type", ""))),
                code=str(error.get("type", "")),
                message=problem_words(error),
            )
            for error in errors
        ],
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


def status_sentence(status: int) -> str:
    """The sentence a failure the application did not word itself carries, by its status."""
    if status in STATUS_SENTENCES:
        return STATUS_SENTENCES[status]
    return UNEXPECTED_FAILURE if status >= 500 else NOT_ACCEPTED_STATUS


def bound_trace_id(request: Request | None = None) -> str:
    """The trace id the `brain.app` trace middleware bound, or the caller's header, or empty."""
    bound = structlog.contextvars.get_contextvars().get("trace_id")
    if bound:
        return str(bound)
    return "" if request is None else request.headers.get("x-trace-id", "")


def unexpected_failure(trace_id: str) -> JSONResponse:
    """The answer to an exception nothing handled: one sentence, the reference, status 500."""
    body = ErrorBody(message=UNEXPECTED_FAILURE, trace_id=trace_id)
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


#: Why a failing document a route wrote for itself is given a sentence and a reference on its way.
A_DOCUMENT_A_ROUTE_WROTE_STILL_CARRIES_THE_TWO_FIELDS_EVERY_FAILURE_DOES: Final = (
    "Nine routes answer a refusal with a document of their own rather than ErrorBody: the "
    "problems a connector, webhook, notification, data transfer or credential write found, the "
    "setup wizard's problems and unkept settings, the staff list's directory problem, an unlink "
    "that would leave no administrator, a sign-in binding that did not bind and an automation "
    "that was not installed. Each carries what its own screen reads and none carried message or "
    "trace_id, so any other reader of the failure, and the console's shared notice, had nothing "
    "to show and no reference to quote. FailureBodyMiddleware adds the two to a failing JSON "
    "object that lacks them, and changes nothing else in it: a field a route wrote is never "
    "rewritten. The sentence is the document's own `sentence` when it has one, which is the field "
    "those routes write for a person, and the status's otherwise. Rejected: editing each route, "
    "which fixes nine and leaves the tenth to whoever writes it next."
)

#: The sentence for a 409 whose document names none of its own.
NOT_DONE_AS_THINGS_STAND: Final = "That was not done, because of how things stand now."


def completed_failure(status: int, body: bytes, trace_id: str) -> bytes | None:
    """A failing JSON document with `message` and `trace_id` added where missing, or None.

    None when nothing needs to change, including a body that is not a JSON object: an array or a
    bare string from a route is replaced by `ErrorBody` rather than wrapped, because it is not
    known what it holds.
    """
    try:
        document = json.loads(body) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if not isinstance(document, dict):
        replaced = ErrorBody(message=_status_words(status), trace_id=trace_id)
        return json.dumps(replaced.model_dump(mode="json")).encode()
    changed = False
    message = document.get("message")
    if not isinstance(message, str) or not message.strip():
        sentence = document.get("sentence")
        document["message"] = (
            sentence if isinstance(sentence, str) and sentence.strip() else _status_words(status)
        )
        changed = True
    if not isinstance(document.get("trace_id"), str) or not document["trace_id"]:
        document["trace_id"] = trace_id
        changed = True
    return json.dumps(document).encode() if changed else None


def _status_words(status: int) -> str:
    if status == 404:
        return NOT_FOUND
    if status == 409:
        return NOT_DONE_AS_THINGS_STAND
    return status_sentence(status)


#: `brain.core.errors.Absent`'s sentence, which an unworded 404 carries so it reads as one.
NOT_FOUND: Final = Absent.public_message


class FailureBodyMiddleware:
    """A failing JSON answer without a sentence or a reference is given both on its way out.

    Pure ASGI rather than `BaseHTTPMiddleware`, so a streamed answer passes straight through: only
    a response that starts with a status of 400 or more and a JSON content type is held, and only
    until its last body chunk. Mounted outside the trace middleware in `brain.app`, so the
    reference is the `x-trace-id` that middleware already set on the response. See
    `A_DOCUMENT_A_ROUTE_WROTE_STILL_CARRIES_THE_TWO_FIELDS_EVERY_FAILURE_DOES`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        held: dict[str, Any] = {}
        chunks: list[bytes] = []

        async def shaping(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = Headers(raw=message["headers"])
                failing = int(message["status"]) >= 400
                if failing and headers.get("content-type", "").startswith("application/json"):
                    held["start"] = message
                    return
            elif message["type"] == "http.response.body" and "start" in held:
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                start = held.pop("start")
                body = b"".join(chunks)
                headers = MutableHeaders(raw=list(start["headers"]))
                shaped = completed_failure(
                    int(start["status"]), body, headers.get("x-trace-id", "")
                )
                if shaped is not None:
                    body = shaped
                    headers["content-length"] = str(len(body))
                await send({**start, "headers": headers.raw})
                await send({"type": "http.response.body", "body": body})
                return
            await send(message)

        await self.app(scope, receive, shaping)
