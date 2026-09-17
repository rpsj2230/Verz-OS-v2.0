/**
 * What the console is allowed to say when a request does not succeed.
 *
 * **A 404 from this API is not "not found".** `brain.app.handle_brain_error` maps both
 * DENIED and ABSENT to 404 with the same body, deliberately, because a 403 on a hidden
 * record confirms that the record exists. The console has to keep that property, and the
 * way a console breaks it is never by writing "access denied": it is by being helpful.
 * "You may not have permission to view this" turns one status code back into two answers,
 * and it does it in the friendliest possible voice.
 *
 * So the rule here is negative and absolute: the console adds no interpretation to a
 * failure. It shows the message the API sent, and when there is none it shows the same
 * sentence the API would have sent, copied from `brain.core.errors`.
 *
 * **The trace id is the one useful thing to add.** Every response carries `x-trace-id`,
 * minted by the application before it knows who is asking, and quoting it is what makes a
 * support conversation short. It identifies a request, not a record, and it is safe to
 * show for the same reason the ledger can hold it and an answer cannot hold a count.
 *
 * **A failure with no message is one the application did not write, and its words say so.**
 * On 2026-09-17 the owner signed in to a staging install and many screens said only "That did
 * not work. Something went wrong.", which was this module's fallback for any status with no
 * readable body. It was true and it was nothing: no reference, no hint whether the fault was
 * the Brain's, the proxy's or the network's. The API now puts a message and a trace id on
 * every failing response it produces, so a failure that arrives without one was answered by
 * something in front of the application, and the fallbacks below describe that observation
 * by status class rather than inventing an outcome. The three the taxonomy owns, 404, 409 and
 * 503, keep the API's own sentences exactly, because a proxy's 404 and the application's must
 * read the same or the difference is a disclosure. Rejected: one generic sentence with the
 * status number appended, which is what "Something went wrong (502)" is, and which asks a
 * person to know what a 502 is.
 *
 * **Two fields describe what was sent rather than what happened, and both are read, never
 * inferred.** `problems` is the API's list of what it refused in a request, by field, for the
 * form to draw beside the inputs; `secondFactorNeeded` is the API saying the session lacks a
 * second factor that this person's own grants would need. Neither is derived from the status
 * or the outcome: see `THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG`.
 *
 * Task ids: M32.5.1.1, M27.9.6
 */

/** Written down because "be helpful about a 404" is the most natural mistake here. */
export const A_404_IS_NOT_AN_EXPLANATION =
  "DENIED and ABSENT are both 404 with the same body. Any wording that distinguishes " +
  "them, including a sympathetic one about permissions, rebuilds the difference the API " +
  "spent a taxonomy removing. Show what the API said and nothing else.";

/**
 * Why the second factor has a flag of its own and the console never works it out.
 *
 * A session without a second factor is refused administration with a 404, the same status and
 * outcome as a record that does not exist, because DENIED and ABSENT stay one answer. The API
 * decides the flag from the session and the person's own grants and never from a record, so
 * branching on it discloses nothing about the company's data. Branching on the 404 instead
 * would turn every absent record into advice to sign in again, and would be the console telling
 * two refusals apart that the API made identical.
 */
export const THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG =
  "Only second_factor_needed === true in the body decides that a failure asks for a sign-in " +
  "with a second factor. The status and the outcome never do, because a 404 is also every " +
  "record this reader may not see.";

/**
 * The fallback for a 404 with no readable body. Copied verbatim from
 * `brain.core.errors.Denied.public_message`, which is identical to `Absent`'s, which is
 * the entire point of that pair.
 */
export const NOT_FOUND_MESSAGE = "I could not find that.";

/** A fault from the server or the proxy in front of it, with nothing written to explain it. */
export const A_FAULT_WITH_NO_EXPLANATION =
  "The server, or the proxy in front of it, answered with a fault and no explanation. Try " +
  "again, and tell an administrator if it keeps happening.";

/** A proxy's answer when the application behind it did not answer at all. */
export const THE_BRAIN_DID_NOT_ANSWER =
  "The Brain did not answer. It may be starting or restarting, so try again in a minute, and " +
  "tell an administrator if it keeps happening.";

/** What a proxy's 413 means, which is about the request and never about the data. */
export const TOO_LARGE_TO_ACCEPT =
  "What was sent was too large to be accepted. Send less at once, or tell an administrator if " +
  "this should have fitted.";

/** A refusal of the request that came with no words, so it was not the application's. */
export const NOT_ACCEPTED_WITHOUT_A_REASON =
  "The request was not accepted, and no explanation came back with the refusal. Try again, and " +
  "tell an administrator if it keeps happening.";

/**
 * Fallbacks by status, for a failure that carried no readable message.
 *
 * 404, 409 and 503 are the taxonomy's statuses and use the API's own sentences, read against
 * `brain.core.errors` in `tests/api-errors.test.tsx`. 500 is the taxonomy's too, and its only
 * sentence is the base class's "Something went wrong.", which is the sentence this table exists
 * to stop being the whole story; the application sends its own words with every 500 it writes.
 */
const FALLBACK_MESSAGES: Readonly<Record<number, string>> = Object.freeze({
  404: NOT_FOUND_MESSAGE,
  409: "I found more than one match and could not tell which you meant.",
  413: TOO_LARGE_TO_ACCEPT,
  502: THE_BRAIN_DID_NOT_ANSWER,
  503: "I could not reach one of the systems needed to answer that.",
  504: THE_BRAIN_DID_NOT_ANSWER,
});

/** The sentence for a status with no message of its own, by class when not by number. */
export function fallbackMessage(status: number): string {
  return FALLBACK_MESSAGES[status] ?? (status >= 500 ? A_FAULT_WITH_NO_EXPLANATION : NOT_ACCEPTED_WITHOUT_A_REASON);
}

/** One thing the API refused in what was sent, named by where it was in the request. */
export interface FieldProblem {
  /**
   * Where in what was sent, joined with ".", without `body`, `query`, `path` or `header` in
   * front: `attempts`, `rungs.0.attempts`, `hours`. Empty when the problem is with the request
   * as a whole, such as a body that does not parse.
   */
  readonly field: string;
  /** A stable machine code, for code that must branch. Never rendered. */
  readonly code: string;
  /** Words for a person, which never repeat the refused input. */
  readonly message: string;
}

/** A request that did not succeed. A value, not an exception: see `client.ts`. */
export interface ApiFailure {
  /** The HTTP status, for code that must branch. Never rendered on its own. */
  readonly status: number;
  /** Safe to show a person, and already safe when it came from the API. */
  readonly message: string;
  /** From the `x-trace-id` response header, or the error body. May be empty. */
  readonly traceId: string;
  /**
   * The API's own vocabulary: denied, absent, unresolved, degraded, failed.
   *
   * For code that must branch, such as deciding whether retrying could help. **Never
   * rendered, and never used to choose wording.** The whole point of the taxonomy is that
   * a person cannot tell denied from absent, and a console that showed the word, or picked
   * a different sentence or a different colour from it, would hand back the distinction
   * the API removed. Today the application's own handler does not send this field at all;
   * the parsing is here because a middleware response does.
   */
  readonly outcome: string;
  /**
   * What the API refused in the request, by field. Empty unless the API listed problems, which
   * it does for a 422 and for the routes whose refusals were always documents.
   */
  readonly problems: readonly FieldProblem[];
  /**
   * The API said this sign-in has no second factor and this person's own grants need one. True
   * only when the body said exactly that: see `THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG`.
   */
  readonly secondFactorNeeded: boolean;
}

/** The shape `brain.api.ErrorBody` returns. Every failing response uses it. */
interface ErrorBody {
  message?: unknown;
  trace_id?: unknown;
  outcome?: unknown;
  problems?: unknown;
  second_factor_needed?: unknown;
}

/**
 * The problems in a failing body, keeping every entry that is one and passing over any that is
 * not.
 *
 * **Lenient per entry, where the Webhooks screen's first reader refused the whole list.** Some
 * routes' refusal documents carry problems of their own shape beside these, the setup
 * appointment's `{step, field, key}` among them, and a list that mixed the two would otherwise
 * lose every problem a form could have drawn. An entry that is not a field problem is left to the
 * screen that reads its own document, and dropping it here is not dropping it from the screen.
 */
export function readFieldProblems(body: unknown): FieldProblem[] {
  if (typeof body !== "object" || body === null) {
    return [];
  }
  const listed = (body as { problems?: unknown }).problems;
  if (!Array.isArray(listed)) {
    return [];
  }
  const read: FieldProblem[] = [];
  for (const one of listed) {
    if (typeof one !== "object" || one === null) {
      continue;
    }
    const { field, code, message } = one as Record<string, unknown>;
    if (typeof field === "string" && typeof code === "string" && typeof message === "string") {
      read.push({ field, code, message });
    }
  }
  return read;
}

/**
 * Turn a failed response into something renderable, preferring what the API said.
 *
 * The API's message has already been through `to_public`, so it is the one string that is
 * known to be safe. The fallbacks exist only for a response that carried no body at all,
 * which is what a proxy returns when it never reached the application.
 */
export function failureFrom(response: Response, body: unknown): ApiFailure {
  // A cast at the boundary, where proving a structural match buys nothing: every field is
  // read back through a `typeof` check below, so the cast widens nothing that the reading
  // does not then narrow.
  const fields = (typeof body === "object" && body !== null ? body : {}) as ErrorBody;
  const message =
    typeof fields.message === "string" && fields.message.length > 0
      ? fields.message
      : fallbackMessage(response.status);
  const headerTrace = response.headers.get("x-trace-id") ?? "";
  return {
    status: response.status,
    message,
    traceId: headerTrace || (typeof fields.trace_id === "string" ? fields.trace_id : ""),
    outcome: typeof fields.outcome === "string" ? fields.outcome : "failed",
    problems: readFieldProblems(body),
    // Exactly true, and nothing truthy: a string "false" from a hand-built document must not
    // send a person to sign in again. See `THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG`.
    secondFactorNeeded: fields.second_factor_needed === true,
  };
}

/** A failure that never reached the API: no network, DNS, or a blocked request. */
export function transportFailure(error: unknown): ApiFailure {
  return {
    status: 0,
    message:
      error instanceof Error && error.name === "AbortError"
        ? "That request was cancelled."
        : "The console could not reach the Brain. Check your connection and try again.",
    traceId: "",
    outcome: "degraded",
    problems: [],
    secondFactorNeeded: false,
  };
}
