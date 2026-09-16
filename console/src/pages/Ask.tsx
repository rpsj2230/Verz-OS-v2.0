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
 * **The answer is reached by one control, because what it stands on is drawn above it.** A
 * sighted reader's eye jumps past the steps and the citations to the paragraph that matters.
 * Somebody on a keyboard or a screen reader reads in document order, so every citation is a
 * stop on the way to the answer, and a question about one client can cite a dozen rows. The
 * control is a native button placed straight after the form, and pressing it puts focus on the
 * answer, which is focusable by script and by nothing else (`tabIndex` of minus one), so the
 * tab order is not lengthened by the thing it exists to shorten. See
 * `THE_ANSWER_IS_ONE_KEYPRESS_FROM_THE_QUESTION`.
 *
 * **The answer is not a live region and the control does not make it one.** Announcing text
 * that arrives a piece at a time reads the answer letter by letter, which is
 * `brain.locale.A_LIVE_REGION_ON_A_STREAM_READS_THE_ANSWER_LETTER_BY_LETTER`; the reader
 * chooses when to hear it, by pressing the control, and hears it once from the start.
 *
 * **A button and not a fragment link.** `href="#ask-answer"` is the usual skip link and it
 * writes the fragment into the address and a history entry, which this page's rule forbids,
 * and a fragment whose target is not focusable moves the scroll position without moving
 * keyboard focus in every browser this console supports.
 *
 * **When asking took the reader's focus away, finishing gives it back, to the control.** The
 * field and the button are disabled while the answer is made, and a disabled element cannot
 * hold focus, so somebody who pressed Ask from the keyboard is left focused on nothing. When
 * the answer is finished, and only if their focus is still nowhere or still on the form they
 * submitted, it goes to the skip control, and a screen reader says the control's name: that
 * is the one announcement a finished answer gets. A reader who moved their focus somewhere
 * else while waiting is left where they went. See `FOCUS_IS_RETURNED_AND_NEVER_TAKEN`.
 *
 * **A refusal gets the same control**, because it arrives as the same frames and is drawn by
 * the same code; a control offered for one and not the other would be the distinction the
 * route spent a taxonomy removing.
 *
 * Task ids: M42.6.3, M35.2.1.3
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
import { FailureNotice } from "../ui/FailureNotice";

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

/**
 * What the progress region says before the first step has arrived.
 *
 * The steps are the lane's own sentences and the first can take a moment to come, so without this
 * the region is an empty list for that moment, and a question still being asked reads the same as
 * one nobody asked. `tests/screen-states.test.tsx` holds the page to a loading sentence of its own.
 */
export const ASKING = "Asking.";

/** The heading over what the answer stands on. Never a count, and never a source list. */
export const BASED_ON = "What this is based on";

/** Before anybody has asked anything. It names no entity and suggests no question. */
export const NOTHING_ASKED_YET = "Nothing has been asked yet.";

/**
 * The control that moves focus past the steps and the citations to the answer. The words are
 * `answer.skip_to` in `brain.locale.MESSAGES`, which already carries its translation, and a
 * test holds the two together.
 */
export const SKIP_TO_ANSWER = "Skip to answer";

/** What the answer is called when focus lands on it, so a screen reader says where it is. */
export const ANSWER_LABEL = "Answer";

/** Why the answer is reached by a control rather than by tabbing past what it stands on. */
export const THE_ANSWER_IS_ONE_KEYPRESS_FROM_THE_QUESTION =
  "The citations are drawn above the answer, so reading in document order passes every one " +
  "of them first. The skip control is the first thing after the form and puts focus on the " +
  "answer, which is focusable by script only, so reaching the answer never costs more than " +
  "one control however much it cites.";

/** Why focus is moved on completion only when the page itself had taken it. */
export const FOCUS_IS_RETURNED_AND_NEVER_TAKEN =
  "Disabling the form while an answer is made leaves a keyboard reader focused on nothing. " +
  "Finishing returns their focus to the skip control, which is also how a screen reader " +
  "learns the answer is ready, and it does so only when their focus is still nowhere or " +
  "still on the form: a reader who went somewhere else while waiting is not moved.";

/** The id tying the label to the field. One field on the page, so one id. */
const QUESTION_FIELD_ID = "ask-question";

/** The id of the region the skip control puts focus on. One answer on the page, so one id. */
const ANSWER_REGION_ID = "ask-answer";

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

  // The form, the skip control and the answer, for moving focus between them. See
  // `FOCUS_IS_RETURNED_AND_NEVER_TAKEN` for when the first hands focus to the second.
  const form = useRef<HTMLFormElement | null>(null);
  const skip = useRef<HTMLButtonElement | null>(null);
  const answerRegion = useRef<HTMLElement | null>(null);
  const focusWasInTheForm = useRef(false);

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
      focusWasInTheForm.current = form.current?.contains(document.activeElement) ?? false;
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
  // What the skip control reaches: an answer, or the sentence a stream that failed carried.
  // Never a request that did not start a stream, which has no steps and no citations to skip.
  const answered = view.answer !== "" || view.failed !== null;

  useEffect(() => {
    if (busy || !answered || !focusWasInTheForm.current) {
      return;
    }
    focusWasInTheForm.current = false;
    const holder = document.activeElement;
    const nowhere = holder === null || holder === document.body;
    if (nowhere || (form.current?.contains(holder) ?? false)) {
      skip.current?.focus();
    }
  }, [busy, answered]);

  return (
    <article className="page">
      <h1>{ASK_HEADING}</h1>
      <p className="lede">{ASK_LEDE}</p>

      <form className="ask__form" onSubmit={ask} ref={form}>
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

      {answered ? (
        <button
          type="button"
          ref={skip}
          className="button ask__skip"
          onClick={() => {
            answerRegion.current?.focus();
          }}
        >
          {SKIP_TO_ANSWER}
        </button>
      ) : null}

      {busy ? (
        <section className="ask__progress" role="status" aria-label={PROGRESS_LABEL}>
          {view.steps.length === 0 ? <p className="note">{ASKING}</p> : null}
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

      {answered ? (
        <section
          id={ANSWER_REGION_ID}
          ref={answerRegion}
          className="ask__result"
          tabIndex={-1}
          aria-label={ANSWER_LABEL}
        >
          {view.answer !== "" ? <p className="ask__answer">{view.answer}</p> : null}

          {view.failed !== null ? (
            <Notice title={SOMETHING_DID_NOT_WORK}>
              <p>{view.failed}</p>
            </Notice>
          ) : null}
        </section>
      ) : null}

      {failure ? (
        <FailureNotice failure={failure} />
      ) : null}

      {!busy && !asked && failure === null ? <p className="note">{NOTHING_ASKED_YET}</p> : null}
    </article>
  );
}
