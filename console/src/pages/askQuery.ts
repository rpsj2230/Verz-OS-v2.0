/**
 * What the ask screen sends, and how the frames that come back become the one thing on the
 * screen.
 *
 * **The question travels in a body and there is no function here that could put it anywhere
 * else.** `ANSWER_API_PATH` is a constant with nothing interpolated into it and `askBody` is
 * the only thing that touches the question, so the address this console asks is the same
 * string for every question anybody types. That is not tidiness: a URL is written to the
 * proxy access log, kept in browser history, sent as a referer by anything the page later
 * links to and shown in full by every screen-sharing tool, and a question here names the
 * client, the invoice or the person somebody is asking about. See
 * `A_QUESTION_TYPED_HERE_IS_A_QUESTION_TYPED_ONCE`, and
 * `brain.api_routes.A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG` for the same argument
 * where the route makes it.
 *
 * **Nothing here reads what the answer says.** `withEvent` moves a frame's data into the
 * field its name belongs to and has no branch on the text. It cannot, because there is
 * nothing to branch on: `brain.gate.answer` sends an abstention as a `text` frame and a
 * `done`, which is exactly what it sends for an answer, so a refusal and an answer are the
 * same shape on the wire and the same markup on the screen. That property is worth more than
 * any care taken here would be, and the way to keep it is to have no code that could notice.
 * See `A_REFUSAL_AND_AN_ANSWER_ARRIVE_AS_THE_SAME_FRAMES`.
 *
 * **Nothing counted, at any point.** There is no field on `AnswerView` holding a number and
 * no derived one for a screen to render: not how many citations came back, not how many steps
 * ran, not how many records were read. Every one of those is a count taken behind a
 * permission predicate, which is "showing 3 of 47" with a different label on it. See
 * `THE_ANSWER_SCREEN_COUNTS_NOTHING`.
 *
 * **Neither cost nor timing, because the route sends neither.** The answer route returns
 * frames and a status, and there is no spend figure, no duration and no token count anywhere
 * in them. A screen that showed one would be showing a number this console made up.
 *
 * **The agent a person picks travels beside the question and decides nothing here.** `askBody`
 * adds the id when one was chosen, and `brain.gate.select.select_agent` decides whether this
 * person may use it; the picker lists the roster `GET /api/v1/agents` sent (M3.9.8).
 *
 * Task ids: M42.6.3, M3.9.8
 */

import type { AnswerEvent } from "../api/events";

/** Written down because a question is the one value on this screen that must not travel. */
export const A_QUESTION_TYPED_HERE_IS_A_QUESTION_TYPED_ONCE =
  "A question names the client, the invoice or the person somebody is asking about, before " +
  "any entitlement has been applied to it. Put in a URL it reaches the proxy log, browser " +
  "history, a referer header and every screen-sharing tool, none of which is governed by the " +
  "reach the answer was computed at. So it goes in the body of a POST, the address is a " +
  "constant, and this console keeps no copy of it anywhere a later page could read.";

/** Written down because telling the two apart is the most natural feature to add here. */
export const A_REFUSAL_AND_AN_ANSWER_ARRIVE_AS_THE_SAME_FRAMES =
  "A withheld record, a record that does not exist, a question no rule matched and a " +
  "question two rules matched all arrive as one text frame and a done, which is what an " +
  "answer arrives as. There is no field that says which happened and there must never be a " +
  "console that guesses: an empty citation list, a short answer or a sentence this file " +
  "recognised would each rebuild the difference the API spends a taxonomy removing.";

/** Written down because a figure beside an answer reads as helpful and is a disclosure. */
export const THE_ANSWER_SCREEN_COUNTS_NOTHING =
  "Every number available on this screen is a count taken behind a permission predicate: " +
  "how many records stood behind the answer, how many sources were searched, how many steps " +
  "ran. Each one tells the reader something about what they were not shown, by subtraction " +
  "from what they were. So no view here holds a number and no element renders one.";

/** Where a question is asked, under the API base. One constant, nothing interpolated. */
export const ANSWER_API_PATH = "/answer";

/**
 * The longest question the route accepts.
 *
 * A copy of `brain.gate.caches.MAX_QUESTION_CHARS`, which the route declares on its request
 * body, and it is held against the API's own document by a test rather than against itself.
 * It is here so that a question too long to be answered is refused by the field a person is
 * typing into rather than by a round trip whose failure they have to read.
 */
export const MAX_QUESTION_CHARS = 4000;

/**
 * The body one question is sent as, or null for a question the route would refuse.
 *
 * Null rather than a trimmed-and-sent guess, for the reason `decisionBody` returns null: a
 * request the route is known to refuse is a round trip spent to be told what this console
 * already knew. The bounds are the route's own, declared on `Question`, and the trimming is
 * the route's too: `StringConstraints(strip_whitespace=True)` means a question with spaces
 * round it is the same question, so this console sends the same string the cache would key.
 */
export function askBody(
  question: string,
  agent = "",
): { readonly question: string; readonly agent?: string } | null {
  const asked = question.trim();
  if (asked === "" || asked.length > MAX_QUESTION_CHARS) {
    return null;
  }
  // The picker's id, sent only when somebody chose one. The route judges it like any name, so
  // an agent the person may not use answers exactly as one that does not exist.
  const named = agent.trim();
  return named === "" ? { question: asked } : { question: asked, agent: named };
}

/**
 * What has arrived so far, and nothing about what has not.
 *
 * Four fields and not one of them is a number or a reason. `steps` and `citations` are the
 * frames' own strings, kept in the order they arrived, because the order is the API's
 * decision: citations go out before the prose they support, which is a state machine on the
 * Python side rather than a convention, and a console that sorted or grouped them would be
 * choosing a different order for a screen the API already ordered.
 */
export interface AnswerView {
  /** Progress labels, from the API's closed vocabulary. Never composed here. */
  readonly steps: readonly string[];
  /** One record and field standing behind the answer, rendered as the API rendered it. */
  readonly citations: readonly string[];
  /** The answer, or the one sentence a refusal is. This console cannot tell which. */
  readonly answer: string;
  /** The stream ended properly. */
  readonly finished: boolean;
  /** The sentence an `error` frame carried, which is the API's own and never a diagnostic. */
  readonly failed: string | null;
}

/**
 * Before anything has been asked.
 *
 * Frozen and shared, so the state a page starts in and the state it returns to when somebody
 * asks again are the same object rather than two literals that could drift apart.
 */
export const NOTHING_ASKED: AnswerView = Object.freeze({
  steps: Object.freeze([]) as readonly string[],
  citations: Object.freeze([]) as readonly string[],
  answer: "",
  finished: false,
  failed: null,
});

/**
 * One frame folded into what is on the screen.
 *
 * **A frame after the stream has closed changes nothing.** `AnswerStream` on the Python side
 * refuses to emit one, and this is the same rule read from the other end: a `done` means the
 * answer is complete, so anything after it is either a bug upstream or something that got
 * between the two, and neither is a reason to change what a person has already read.
 *
 * Text is appended rather than replaced, because a chunk is a chunk. Replacing would render
 * the last chunk of an answer as the whole of it, which is a wrong answer that looks like a
 * short one.
 */
export function withEvent(view: AnswerView, event: AnswerEvent): AnswerView {
  if (view.finished || view.failed !== null) {
    return view;
  }
  switch (event.name) {
    case "step":
      return { ...view, steps: [...view.steps, event.data] };
    case "citation":
      return { ...view, citations: [...view.citations, event.data] };
    case "text":
      return { ...view, answer: view.answer + event.data };
    case "done":
      return { ...view, finished: true };
    case "error":
      return { ...view, failed: event.data };
  }
}
