/**
 * The screen a person asks a question on, which is the one screen that proves an install.
 *
 * **It is the end-to-end proof and that is what it is for.** Everything else in this console
 * reads a list the API already holds. This page sends a question a person typed, at their own
 * reach, through `brain.gate.answer.answer_lane`, and draws what came back, so an installer
 * who has run the wizard and signed in can tell whether the thing works before a single
 * channel is connected. Nothing about it is specific to a channel and nothing about it is
 * specific to a company.
 *
 * **The question goes in the body and the address never changes.** See
 * `pages/askQuery.ts`'s `A_QUESTION_TYPED_HERE_IS_A_QUESTION_TYPED_ONCE`. There is no
 * `useSearchParams` here and no `navigate`, which is the difference between this screen and
 * the records screen: an entity is what a screen is about and belongs in its address, and a
 * question is the most sensitive thing in the request and belongs in nothing that is written
 * down. Asking twice is two requests and no history entry.
 *
 * **A refusal is drawn by the same code that draws an answer, because it arrives as the same
 * frames.** There is no branch on this page for one. The route answers a withheld record, an
 * absent record, a question no rule matched and a question two rules matched with one
 * sentence in a `text` frame, and this page renders `text` frames. See
 * `A_REFUSAL_AND_AN_ANSWER_ARRIVE_AS_THE_SAME_FRAMES`.
 *
 * **The steps are shown while they mean something and then they are gone.** A progress step
 * describes work in progress, so it is on the screen while the answer is being made and not
 * afterwards: a list of steps sitting under a finished answer is decoration, and a reader who
 * learns to skip it has learned to skip the one place the console says what is happening. It
 * is a live region, so somebody using a screen reader hears the same thing a sighted reader
 * watches.
 *
 * **Nothing here is animated, estimated or predicted.** The labels are the ones the API sent,
 * in its order, and when a body arrives in one piece they all arrive at once. See
 * `api/events.ts`'s `A_STEP_NOT_SENT_IS_A_STEP_NOT_SHOWN`.
 *
 * **There is no cost and no timing on this screen**, because the route sends neither. A
 * figure either comes from the API or is made up here, and made up is what a duration
 * measured in the browser would be: it would include the network, the proxy and React.
 *
 * Task ids: M42.6.3
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { openStream } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  ANSWER_API_PATH,
  askBody,
  MAX_QUESTION_CHARS,
  NOTHING_ASKED,
  withEvent,
  type AnswerView,
} from "./askQuery";

/** The console address of this screen. */
export const ASK_ADDRESS = "/ask";

/** The page's heading, and the word it is called by in the navigation. */
export const ASK_HEADING = "Ask";

/** Under the heading. Says what the screen does and promises nothing about the answer. */
export const ASK_LEDE = "Ask a question. The answer is computed for what you are able to see.";

/** The field, its button, and what a live region is called. */
export const QUESTION_LABEL = "Your question";
export const ASK_LABEL = "Ask";
export const PROGRESS_LABEL = "While the answer is being made";

/** The heading over what the answer stands on. Never a count, and never a source list. */
export const BASED_ON = "What this is based on";

/** Before anybody has asked anything. It names no entity and suggests no question. */
export const NOTHING_ASKED_YET = "Nothing has been asked yet.";

/** The id tying the label to the field. One field on the page, so one id. */
const QUESTION_FIELD_ID = "ask-question";

/** What is on the screen apart from the question somebody is typing. */
interface Asking {
  readonly view: AnswerView;
  readonly busy: boolean;
  /** A request that did not start a stream, in the API's own words. */
  readonly failure: ApiFailure | null;
}

const IDLE: Asking = Object.freeze({ view: NOTHING_ASKED, busy: false, failure: null });

export function Ask() {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState<Asking>(IDLE);

  // The stream in flight, so that leaving the page stops reading it. Without this, a page
  // that has gone still holds a reader and still sets state, which React reports as a
  // warning and which in a suite reads as a flake rather than as the leak it is.
  const inFlight = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      inFlight.current?.abort();
      inFlight.current = null;
    },
    [],
  );

  const ask = useCallback(
    (submitted: FormEvent<HTMLFormElement>) => {
      submitted.preventDefault();
      const body = askBody(question);
      if (body === null) {
        // Not a question the route would take. Doing nothing is the answer: a request known
        // to be refused is a round trip spent to be told what this console already knew.
        return;
      }
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      setAsking({ view: NOTHING_ASKED, busy: true, failure: null });

      void (async () => {
        const opened = await openStream(ANSWER_API_PATH, {
          body,
          signal: controller.signal,
        });
        if (controller.signal.aborted) {
          return;
        }
        if (!opened.ok) {
          setAsking({ view: NOTHING_ASKED, busy: false, failure: opened.failure });
          return;
        }
        for await (const event of opened.events) {
          if (controller.signal.aborted) {
            return;
          }
          setAsking((one) => ({ ...one, view: withEvent(one.view, event) }));
        }
        if (!controller.signal.aborted) {
          setAsking((one) => ({ ...one, busy: false }));
        }
      })();
    },
    [question],
  );

  const { view, busy, failure } = asking;
  const asked = view.answer !== "" || view.citations.length > 0 || view.failed !== null;

  return (
    <article className="page">
      <h1>{ASK_HEADING}</h1>
      <p className="lede">{ASK_LEDE}</p>

      <form className="ask__form" onSubmit={ask}>
        <label className="ask__label" htmlFor={QUESTION_FIELD_ID}>
          {QUESTION_LABEL}
        </label>
        <textarea
          id={QUESTION_FIELD_ID}
          className="form-control ask__question"
          rows={3}
          maxLength={MAX_QUESTION_CHARS}
          value={question}
          disabled={busy}
          onChange={(changed) => setQuestion(changed.target.value)}
        />
        <div className="form-actions">
          <button
            type="submit"
            className="button ask__submit"
            disabled={busy || askBody(question) === null}
          >
            {ASK_LABEL}
          </button>
        </div>
      </form>

      {busy ? (
        <section className="ask__progress" role="status" aria-label={PROGRESS_LABEL}>
          <ul className="ask__steps">
            {view.steps.map((step, at) => (
              // Keyed by position because a step is a sentence from a closed vocabulary and
              // the same one can legitimately arrive twice; the list only ever grows at the
              // end, so a position is stable for as long as the row exists.
              <li key={`${at}-${step}`}>{step}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.citations.length > 0 ? (
        <section className="card ask__provenance">
          <h2>{BASED_ON}</h2>
          <ul className="ask__sources">
            {view.citations.map((citation, at) => (
              <li key={`${at}-${citation}`}>{citation}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.answer !== "" ? <p className="ask__answer">{view.answer}</p> : null}

      {view.failed !== null ? (
        <Notice title={SOMETHING_DID_NOT_WORK}>
          <p>{view.failed}</p>
        </Notice>
      ) : null}

      {failure ? (
        <Notice title={SOMETHING_DID_NOT_WORK} traceId={failure.traceId}>
          <p>{failure.message}</p>
        </Notice>
      ) : null}

      {!busy && !asked && failure === null ? <p className="note">{NOTHING_ASKED_YET}</p> : null}
    </article>
  );
}
