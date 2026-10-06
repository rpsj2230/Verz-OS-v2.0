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
 * **A failure carries the request's reference wherever it arrives.** A request refused before
 * the stream started is drawn by `ui/FailureNotice.tsx`, with the question's problems beside the
 * field. A failure carried by a frame has no body of its own to hold a trace id, so the stream's
 * own `x-trace-id` is kept from when it opened and drawn under the frame's sentence, which is the
 * reference the server's log has that failure under.
 *
 * **A person can name the agent that answers, from the agents they may see.** The picker is the
 * roster `GET /api/v1/agents` returns, which the API filters by audience before this page sees it,
 * and it is drawn only when that roster has an entry. The id goes beside the question; the route
 * decides whether this person may use it, and an agent they may not use answers exactly as one
 * that does not exist, so the picker cannot be a way to find out which agents are there (M3.9.8).
 *
 * **Every citation is a link to what it names, with how fresh it is and who vouched for it** (M8.1.1
 * to M8.1.3, M7.4.7). A record opens its entity's rows on the Records screen and a document opens
 * at the passage cited, `pages/CitedDocument.tsx`. Beside each is the API's word for its freshness
 * and the date, and beside a document its verification badge. When the weakest of them is old the
 * answer's own text says so, because the lane puts that sentence in the text frame (M11.4.9), and
 * this page draws it as it draws every text frame. See
 * `askQuery.A_CITATION_IS_DRAWN_AS_A_LINK_TO_WHAT_IT_NAMES`.
 *
 * **A question can be narrowed to one kind of knowledge (M7.6.1).** The picker lists the closed
 * list `KIND_WORDS` holds, the same words the library shows, and its first choice searches every
 * kind, which is what an unnarrowed question has always done.
 *
 * **A question continues a conversation, and a person's conversations are listed and searched
 * here (M9.1.1, M9.1.2, M9.1.3).** The route names the thread an answer was kept in and the next
 * question sends it back; the panel lists this person's conversations wherever each was asked,
 * searches their own questions, and reopens one at the reach they hold now. A person with no
 * conversations sees no panel.
 *
 * Task ids: M42.6.3, M35.2.1.3, M27.8.5, M3.9.8, M8.1.1, M8.1.2, M8.1.3, M7.4.7, M11.4.9, M7.6.1
 * Task ids: M9.1.1, M9.1.2, M9.1.3
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { openStream, request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { Badge } from "../ui/Badge";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  ANSWER_API_PATH,
  askBody,
  citationAddress,
  freshnessWords,
  MARK_API_PATH,
  markBody,
  MAX_QUESTION_CHARS,
  NOTHING_ASKED,
  readMarked,
  withEvent,
  type AnswerView,
  type CitationView,
} from "./askQuery";
import { KIND_WORDS } from "./knowledgeQuery";
import {
  channelWords,
  CORRECTION_WORDS,
  correctionPath,
  exportPath,
  messageWords,
  readConversationTaken,
  readCorrection,
  readThread,
  readThreads,
  speaker,
  threadPath,
  threadSearchPath,
  THREADS_API_PATH,
  type CorrectionKind,
  type ThreadShown,
  type ThreadSummary,
} from "./threadsQuery";
import { FailureNotice, NO_REFERENCE_CAME_BACK } from "../ui/FailureNotice";
import { readRoster, ROSTER_API_PATH, type RosterEntryView } from "./agentsQuery";
import { CANNOT_SAVE, saveDocument } from "./dataTransferQuery";

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

/** The question over the two marks, and the two marks. One action each, and no words. */
export const WAS_IT_HELPFUL = "Was this answer helpful?";
export const HELPFUL = "Helpful";
export const NOT_HELPFUL = "Not helpful";

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

/** The agent picker's label, and its first choice, which leaves the choice to the router. */
export const AGENT_LABEL = "Answer as";
export const ANY_AGENT = "Whichever agent suits the question";

/** The id tying the picker to its label. */
const AGENT_FIELD_ID = "ask-agent";

/** The conversations panel: its heading, its search, and the control starting a new one (M9.1). */
export const CONVERSATIONS_HEADING = "Your conversations";
export const SEARCH_CONVERSATIONS = "Search your questions";
export const SEARCH_LABEL = "Search";
export const NEW_CONVERSATION = "Start a new conversation";
export const CONTINUING = "Your next question continues this conversation.";
export const NOTHING_FOUND_IN_CONVERSATIONS = "None of your questions holds those words.";

/** The id tying the search to its label. */
const SEARCH_FIELD_ID = "ask-search";

/**
 * The control under an answer kept in a conversation, marking it wrong (M9.2.4), and saying what
 * is right if the person knows (M16.6.5). The kind is the note; the words, when given, are a
 * proposal its document's steward decides: see `threadsQuery.ts`.
 */
export const WAS_IT_WRONG = "Was this answer wrong?";
export const WHAT_IS_RIGHT = "What is right? (optional)";
export const WHAT_IS_RIGHT_HINT =
  "Sent to whoever looks after the document this answer used. It changes nothing until they approve it.";
/** The most a person may say is right, which is what the route takes. */
export const RIGHT_ANSWER_CHARS = 2000;
export const MARK_WRONG = "Mark it wrong";
export const MARKED_WRONG = "Marked. Your conversation now notes that this answer was wrong.";
export const NOT_MARKED = "That could not be marked. Nothing was changed.";

/**
 * The control exporting the conversation the answer was kept in as a file (M33.3.1.3). The file is
 * the conversation as the page shows it now, and the export is recorded in the person's own name
 * before it is handed over, which the page says rather than leaving it to be discovered.
 */
export const EXPORT_CONVERSATION = "Export this conversation";
export const NOT_EXPORTED = "That conversation could not be exported. Nothing was saved.";

/** The id tying the correction's kind to its label. */
const CORRECTION_FIELD_ID = "ask-correction";

/** The id tying what is right to its label. */
const RIGHT_FIELD_ID = "ask-right-answer";

/** The first kind offered. */
const FIRST_CORRECTION: CorrectionKind = "wrong_fact";

/** The kind picker's label, and its first choice, which searches every kind (M7.6.1). */
export const KIND_LABEL = "Search only";
export const ANY_KIND = "Every kind of knowledge";

/** The id tying the kind picker to its label. */
const KIND_FIELD_ID = "ask-kind";

/** The id tying the label to the field. One field on the page, so one id. */
const QUESTION_FIELD_ID = "ask-question";

/** The id of the region the skip control puts focus on. One answer on the page, so one id. */
const ANSWER_REGION_ID = "ask-answer";

/**
 * One citation: a link to what it names, then how fresh it is and, for a document, its badge.
 *
 * The label is the link's text, so a screen reader reads where it goes. A citation that names
 * neither a record nor a document is its label alone, which is what a frame carrying a sentence
 * rather than fields draws. The badge is neutral whatever it says: its words carry the state, and
 * a colour chosen from them would be this console holding an opinion about the item.
 */
function Cited({ citation, retrievalId }: { readonly citation: CitationView; readonly retrievalId: string }) {
  const address = citationAddress(citation, retrievalId);
  const fresh = freshnessWords(citation);
  return (
    <>
      {address === null ? citation.label : <Link to={address}>{citation.label}</Link>}
      {fresh !== "" || citation.badge !== "" ? (
        <span className="ask__evidence">
          {fresh}
          {fresh !== "" && citation.badge !== "" ? " " : null}
          {citation.badge !== "" ? <Badge label={citation.badge} /> : null}
        </span>
      ) : null}
    </>
  );
}

/**
 * Helpful or not helpful on the answer just given, one press each (M16.6.4). The mark is the
 * answer's reference and one bit; once counted, the API's sentence replaces the two buttons, and a
 * refusal is drawn as any failure is. Keyed by the reference, so a new answer starts unmarked.
 */
function Marking({ traceId }: { readonly traceId: string }) {
  const [told, setTold] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const mark = useCallback(
    (helpful: boolean) => {
      const body = markBody(traceId, helpful);
      if (body === null) {
        return;
      }
      setBusy(true);
      setFailure(null);
      void (async () => {
        const result = await request<unknown>(MARK_API_PATH, { method: "POST", body });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setTold(readMarked(result.data));
      })();
    },
    [traceId],
  );

  if (told !== "") {
    return (
      <p className="note" role="status">
        {told}
      </p>
    );
  }
  return (
    <section className="ask__marks" aria-label={WAS_IT_HELPFUL}>
      <p className="note">{WAS_IT_HELPFUL}</p>
      <div className="form-actions">
        <button type="button" className="button" disabled={busy} onClick={() => mark(true)}>
          {HELPFUL}
        </button>
        <button type="button" className="button" disabled={busy} onClick={() => mark(false)}>
          {NOT_HELPFUL}
        </button>
      </div>
      {failure ? <FailureNotice failure={failure} /> : null}
    </section>
  );
}

/** What is on the screen apart from the question somebody is typing. */
interface Asking {
  readonly view: AnswerView;
  readonly busy: boolean;
  /** A request that did not start a stream, in the API's own words. */
  readonly failure: ApiFailure | null;
  /** The reference of the stream that was opened, for a failure one of its frames carries. */
  readonly traceId: string;
}

const IDLE: Asking = Object.freeze({ view: NOTHING_ASKED, busy: false, failure: null, traceId: "" });

/** The name the question is sent under, and the prefix of the list drawn beside it. */
const QUESTION_NAME = "question";

export function Ask() {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState<Asking>(IDLE);
  const [agents, setAgents] = useState<readonly RosterEntryView[]>([]);
  const [agent, setAgent] = useState("");
  const [kind, setKind] = useState("");
  // The conversation the next question continues, and this person's conversations (M9.1).
  const [thread, setThread] = useState("");
  // The retrieval the answer on the screen was drawn from, which a followed citation names (M15.3.4).
  const [retrievalId, setRetrievalId] = useState("");
  const [threads, setThreads] = useState<readonly ThreadSummary[] | null>(null);
  const [searching, setSearching] = useState("");
  const [found, setFound] = useState<readonly ThreadSummary[] | null>(null);
  const [reopened, setReopened] = useState<ThreadShown | null>(null);
  // Marking the answer on the page wrong: the kind chosen, and what the route said (M9.2.4).
  const [wrong, setWrong] = useState<CorrectionKind>(FIRST_CORRECTION);
  const [marked, setMarked] = useState<"" | "marked" | "failed">("");
  const [right, setRight] = useState("");
  const [exported, setExported] = useState("");

  // This person's conversations. A list that did not come back is no panel rather than an error:
  // the question can still be asked, and it starts a conversation of its own.
  const listThreads = useCallback(async () => {
    const listed = await request<unknown>(THREADS_API_PATH);
    const read = listed.ok ? readThreads(listed.data) : null;
    setThreads(read);
  }, []);
  useEffect(() => {
    void listThreads();
  }, [listThreads]);

  // The agents this person may see, for the picker. A roster that did not come back is no
  // picker rather than an error: the question can still be asked, and the router chooses.
  useEffect(() => {
    let live = true;
    void (async () => {
      const listed = await request<unknown>(ROSTER_API_PATH);
      const roster = listed.ok ? readRoster(listed.data) : null;
      if (live && roster !== null) {
        setAgents(roster.entries);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

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
      const body = askBody(question, agent, kind, thread);
      if (body === null) {
        // Not a question the route would take. Doing nothing is the answer: a request known
        // to be refused is a round trip spent to be told what this console already knew.
        return;
      }
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      focusWasInTheForm.current = form.current?.contains(document.activeElement) ?? false;
      setMarked("");
      setRight("");
      setExported("");
      setAsking({ view: NOTHING_ASKED, busy: true, failure: null, traceId: "" });

      void (async () => {
        const opened = await openStream(ANSWER_API_PATH, {
          body,
          signal: controller.signal,
        });
        if (controller.signal.aborted) {
          return;
        }
        if (!opened.ok) {
          setAsking({ view: NOTHING_ASKED, busy: false, failure: opened.failure, traceId: "" });
          return;
        }
        setAsking((one) => ({ ...one, traceId: opened.traceId }));
        if (opened.threadId !== "") {
          setThread(opened.threadId);
        }
        setRetrievalId(opened.retrievalId);
        for await (const event of opened.events) {
          if (controller.signal.aborted) {
            return;
          }
          setAsking((one) => ({ ...one, view: withEvent(one.view, event) }));
        }
        if (!controller.signal.aborted) {
          setAsking((one) => ({ ...one, busy: false }));
          void listThreads();
        }
      })();
    },
    [question, agent, kind, thread, listThreads],
  );

  const { view, busy, failure, traceId } = asking;
  const problems = failure?.problems ?? [];
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
          name={QUESTION_NAME}
          value={question}
          disabled={busy}
          {...problemAttributes(problems, QUESTION_FIELD_ID, QUESTION_NAME)}
          onChange={(changed) => setQuestion(changed.target.value)}
        />
        <FieldProblems problems={problems} form={QUESTION_FIELD_ID} names={QUESTION_NAME} />
        {agents.length > 0 ? (
          <>
            <label className="ask__label" htmlFor={AGENT_FIELD_ID}>
              {AGENT_LABEL}
            </label>
            <select
              id={AGENT_FIELD_ID}
              className="form-control"
              value={agent}
              disabled={busy}
              onChange={(changed) => setAgent(changed.target.value)}
            >
              <option value="">{ANY_AGENT}</option>
              {agents.map((one) => (
                <option key={one.agentId} value={one.agentId}>
                  {one.displayName}
                </option>
              ))}
            </select>
          </>
        ) : null}
        <label className="ask__label" htmlFor={KIND_FIELD_ID}>
          {KIND_LABEL}
        </label>
        <select
          id={KIND_FIELD_ID}
          className="form-control"
          value={kind}
          disabled={busy}
          onChange={(changed) => setKind(changed.target.value)}
        >
          <option value="">{ANY_KIND}</option>
          {Object.entries(KIND_WORDS).map(([value, words]) => (
            <option key={value} value={value}>
              {words}
            </option>
          ))}
        </select>
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
              <li key={`${at}-${citation.label}`}>
                <Cited citation={citation} retrievalId={retrievalId} />
              </li>
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

          {thread !== "" && !busy && view.answer !== "" ? (
            <form
              className="ask__correction"
              onSubmit={(submitted) => {
                submitted.preventDefault();
                void (async () => {
                  const sent = await request<unknown>(correctionPath(thread), {
                    method: "POST",
                    body: right.trim() === "" ? { kind: wrong } : { kind: wrong, right_answer: right.trim() },
                  });
                  setMarked(sent.ok && readCorrection(sent.data) !== null ? "marked" : "failed");
                })();
              }}
            >
              <label className="ask__label" htmlFor={CORRECTION_FIELD_ID}>
                {WAS_IT_WRONG}
              </label>
              <select
                id={CORRECTION_FIELD_ID}
                className="form-control"
                value={wrong}
                onChange={(changed) => setWrong(changed.target.value as CorrectionKind)}
              >
                {(Object.keys(CORRECTION_WORDS) as CorrectionKind[]).map((one) => (
                  <option key={one} value={one}>
                    {CORRECTION_WORDS[one]}
                  </option>
                ))}
              </select>
              <label className="ask__label" htmlFor={RIGHT_FIELD_ID}>
                {WHAT_IS_RIGHT}
              </label>
              <textarea
                id={RIGHT_FIELD_ID}
                className="form-control"
                maxLength={RIGHT_ANSWER_CHARS}
                value={right}
                aria-describedby={`${RIGHT_FIELD_ID}-hint`}
                onChange={(changed) => setRight(changed.target.value)}
              />
              <p className="note" id={`${RIGHT_FIELD_ID}-hint`}>
                {WHAT_IS_RIGHT_HINT}
              </p>
              <button type="submit" className="button" disabled={marked === "marked"}>
                {MARK_WRONG}
              </button>
              {marked !== "" ? (
                <p className="note" role="status">
                  {marked === "marked" ? MARKED_WRONG : NOT_MARKED}
                </p>
              ) : null}
            </form>
          ) : null}

          {thread !== "" && !busy && view.answer !== "" ? (
            <div className="ask__export">
              <button
                type="button"
                className="button"
                onClick={() => {
                  void (async () => {
                    const sent = await request<unknown>(exportPath(thread), { method: "POST" });
                    const taken = sent.ok ? readConversationTaken(sent.data) : null;
                    if (taken === null) {
                      setExported(NOT_EXPORTED);
                      return;
                    }
                    const saved = saveDocument(taken.filename, taken.document, document, "application/json");
                    setExported(saved ? taken.told : CANNOT_SAVE);
                  })();
                }}
              >
                {EXPORT_CONVERSATION}
              </button>
              {exported !== "" ? (
                <p className="note" role="status">
                  {exported}
                </p>
              ) : null}
            </div>
          ) : null}

          {view.failed !== null ? (
            <Notice title={SOMETHING_DID_NOT_WORK} traceId={traceId} withoutTrace={NO_REFERENCE_CAME_BACK}>
              <p>{view.failed}</p>
            </Notice>
          ) : null}
        </section>
      ) : null}

      {!busy && view.answer !== "" && markBody(traceId, true) !== null ? (
        <Marking traceId={traceId} key={traceId} />
      ) : null}

      {failure ? <FailureNotice failure={failure} fields={[QUESTION_NAME]} /> : null}

      {!busy && !asked && failure === null ? <p className="note">{NOTHING_ASKED_YET}</p> : null}

      {thread !== "" ? (
        <div className="ask__thread">
          <p className="note">{CONTINUING}</p>
          <button
            type="button"
            className="button"
            onClick={() => {
              setThread("");
              setReopened(null);
            }}
          >
            {NEW_CONVERSATION}
          </button>
        </div>
      ) : null}

      {reopened !== null ? (
        <section className="card ask__reopened" aria-label={reopened.title}>
          <h2>{reopened.title}</h2>
          <ol className="ask__messages">
            {reopened.messages.map((one, at) => (
              <li key={`${at}-${one.at}`}>
                <strong>{speaker(one.role)}</strong> {channelWords(one.channel)}: {messageWords(one.body)}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {threads !== null && threads.length > 0 ? (
        <section className="card ask__conversations">
          <h2>{CONVERSATIONS_HEADING}</h2>
          <form
            className="ask__search"
            role="search"
            onSubmit={(submitted) => {
              submitted.preventDefault();
              const path = threadSearchPath(searching);
              if (path === null) {
                setFound(null);
                return;
              }
              void (async () => {
                const asked = await request<unknown>(path);
                setFound(asked.ok ? readThreads(asked.data) : null);
              })();
            }}
          >
            <label className="ask__label" htmlFor={SEARCH_FIELD_ID}>
              {SEARCH_CONVERSATIONS}
            </label>
            <input
              id={SEARCH_FIELD_ID}
              className="form-control"
              type="search"
              value={searching}
              onChange={(changed) => setSearching(changed.target.value)}
            />
            <button type="submit" className="button">
              {SEARCH_LABEL}
            </button>
          </form>
          {found !== null && found.length === 0 ? (
            <p className="note">{NOTHING_FOUND_IN_CONVERSATIONS}</p>
          ) : null}
          <ul className="ask__threads">
            {(found ?? threads).map((one) => (
              <li key={one.threadId}>
                <button
                  type="button"
                  className="button button--link"
                  onClick={() => {
                    void (async () => {
                      const opened = await request<unknown>(threadPath(one.threadId));
                      const read = opened.ok ? readThread(opened.data) : null;
                      if (read !== null) {
                        setReopened(read);
                        setThread(read.threadId);
                      }
                    })();
                  }}
                >
                  {one.title}
                </button>{" "}
                <span className="note">{channelWords(one.lastChannel)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
