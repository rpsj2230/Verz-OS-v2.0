/**
 * The rule `tests/screen-states.test.tsx` holds every registered page to, and the pages excused
 * from part of it with their reasons.
 *
 * In a support module rather than in the test file because the pages are read in three files at
 * once. Each page is mounted five times, sixty pages is three hundred mounts, and one file doing
 * all of them took a minute on its own while the rest of the suite waited on it. The allowlists
 * live here, once, so the three files cannot disagree about what is excused.
 *
 * Task ids: M27.8.3
 */

import { fireEvent } from "@testing-library/react";
import { expect } from "vitest";
import { NOT_FOUND_MESSAGE, transportFailure } from "../../src/api/errors";
import { NO_REFERENCE_CAME_BACK } from "../../src/ui/FailureNotice";
import { SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR } from "../../src/ui/SignInAgain";
import { CALLBACK_PATH, SIGNED_OUT_PATH } from "../../src/auth/constants";
import { RETURN_PATH as STAFF_LIST_RETURN_PATH } from "../../src/setup/staffList";
import { FIRST_RUN_PATH } from "../../src/setup/wizard";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./navigation";
import { PAGES } from "./pageCases";
import {
  API_SENTENCE,
  SECOND_FACTOR_SENTENCE,
  TRACE_SENTINEL,
  collapse,
  mountIn,
  type Mounted,
  type Reading,
  type RequestState,
} from "./screenStates";

/**
 * Addresses that send no request when they are opened, and why that leaves them nothing to say.
 *
 * Checked, not trusted: every entry is mounted with an API that fails everything, and a page here
 * that sends a request fails the test that reads this list. A page cannot be excused by adding it.
 */
export const ASKS_NOTHING_ON_ARRIVAL: Readonly<Record<string, string>> = {
  [CALLBACK_PATH]:
    "The sign-in callback exchanges a code with the identity provider and never calls the API; its " +
    "failures are the identity provider's and are held in tests/auth-session.test.ts.",
  [SIGNED_OUT_PATH]: "The signed-out page says that a person signed out and asks nothing.",
  [FIRST_RUN_PATH]:
    "The first-run wizard asks nothing until its last step has been filled in. What it says when " +
    "that write is refused, fails, or cannot reach the API is held in tests/first-run.test.tsx.",
  [STAFF_LIST_RETURN_PATH]:
    "The page a directory returns the staff list sign-in window to posts that answer to the tab " +
    "that opened it and closes, and never calls the API. What it posts is held in " +
    "tests/first-run-staff-list.test.tsx.",
  "/records":
    "The bare address is a form that names a record type and opens /records/:entity, which asks " +
    "and is held here.",
  "/classification":
    "The bare address is a form that names a document and opens /classification/:entity, which " +
    "asks and is held here.",
  "/memory":
    "The bare address is a form that names a person and opens /memory/:subject, which asks and is " +
    "held here.",
  "/*": "The not-found page is drawn by the route table and asks nothing.",
};

/**
 * Pages that ask only once a person has done something, and what that something is.
 *
 * The four states are read after the action rather than on arrival. There is no empty state,
 * because the request is a question a person asked rather than a list the page reads.
 */
export const ACTS: Readonly<Record<string, (mounted: Mounted) => void>> = {
  "/ask": ({ container }) => {
    const field = container.querySelector("textarea");
    if (field === null) {
      throw new Error("The ask page drew no question field.");
    }
    fireEvent.change(field, { target: { value: "Which quotes are waiting?" } });
    const button = [...container.querySelectorAll("button")].find((one) => one.type === "submit");
    if (button === undefined) {
      throw new Error("The ask page drew no submit button.");
    }
    fireEvent.click(button);
  },
};

/**
 * Which of a page's answers the empty state empties, where emptying every list would unmake the
 * page rather than empty it.
 *
 * The agent workspace's strip of tabs is a list, and an agent with no tabs has no Automations tab
 * to be empty on, so only the gallery is emptied there.
 */
export const EMPTIES_ONLY: Readonly<Record<string, readonly string[]>> = {
  "/agents/:agentId/:tab": ["/api/v1/agents/quote-helper/automation-templates"],
};

/**
 * Pages whose answer holds lists and which say nothing when they are empty, and why that is the
 * rule rather than a gap.
 *
 * Checked, not trusted: an entry whose answer holds no list at all is refused by the first test,
 * because it would be excusing nothing.
 */
export const NO_EMPTY_SENTENCE: Readonly<Record<string, string>> = {
  "/agents/:agentId":
    "One agent is not a list. Its connectors, skills and channels are blocks that draw nothing when " +
    "they have no rows, because a heading over an empty block cannot be told from one whose rows the " +
    "reader may not see: brain.console.workspace.A_TAB_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS.",
  "/":
    "The overview's only list is the install card's parts, and /health/ready always names database, " +
    "cache, vault and sign-in (brain.readiness.HEADLINE_PARTS), so an empty list is not an answer " +
    "the API can give. The caller card is one object, not a list.",
};

/** What `api/errors.transportFailure` puts in front of a person, which no page wrote. */
const TRANSPORT_SENTENCE = transportFailure(new TypeError("Failed to fetch")).message;

function emptied(value: unknown): unknown {
  if (Array.isArray(value)) {
    return [];
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, one]) => [key, emptied(one)]));
  }
  return value;
}

/** The page's answers with every list emptied, or null when there is no list in them to empty. */
export function emptyAnswers(pattern: string): Record<string, unknown> | null {
  const answers = PAGES[pattern]?.answers ?? {};
  const only = EMPTIES_ONLY[pattern];
  const result = Object.fromEntries(
    Object.entries(answers).map(([path, body]) => [
      path,
      path !== NAVIGATION_ADDRESS && (only === undefined || only.includes(path)) ? emptied(body) : body,
    ]),
  );
  return JSON.stringify(result) === JSON.stringify(answers) ? null : result;
}

/** The sentences a page wrote itself: the API's message, the transport's and the reference removed. */
function ownWords(sentences: ReadonlySet<string>): Set<string> {
  return new Set(
    [...sentences].filter(
      (one) =>
        !one.includes(API_SENTENCE) && !one.includes(TRACE_SENTINEL) && !one.includes(TRANSPORT_SENTENCE),
    ),
  );
}

/** The sentences in `mine` that none of `others` has. */
function onlyIn(mine: ReadonlySet<string>, others: readonly ReadonlySet<string>[]): string[] {
  return [...mine].filter((one) => others.every((other) => !other.has(one)));
}

/** Mount `pattern` in `state`, do what the page needs doing before it asks, and read it. */
async function readingOf(pattern: string, state: RequestState): Promise<Reading> {
  const page = PAGES[pattern];
  if (page === undefined) {
    throw new Error(`${pattern} has no page case.`);
  }
  const act = ACTS[pattern];
  const navigation = page.answers[NAVIGATION_ADDRESS] ?? COMPANY_CONSOLE;
  const mounted = await mountIn(pattern, page.address, state, state.kind === "pending" && act === undefined, navigation);
  if (state.kind === "answered") {
    expect(mounted.unanswered, `${pattern} asked for something its case does not answer`).toEqual([]);
  }
  if (act === undefined) {
    return mounted;
  }
  act(mounted);
  return await mounted.reread();
}

async function reading(pattern: string, state: RequestState): Promise<Set<string>> {
  return ownWords((await readingOf(pattern, state)).sentences);
}

/** The whole text of a reading, with its white space collapsed. */
function textOf(read: Reading): string {
  return collapse(read.root.textContent ?? "");
}

/** Whether a reading draws the control that sends a person to sign in again with a second factor. */
function offersToSignInAgain(read: Reading): boolean {
  return [...read.root.querySelectorAll("button")].some(
    (one) => collapse(one.textContent ?? "") === SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR,
  );
}

export const ASKING = Object.keys(PAGES).filter((pattern) => !(pattern in ASKS_NOTHING_ON_ARRIVAL));

/** The patterns that ask on arrival, dealt into `of` shards so each test file reads a third. */
export function shard(index: number, of: number): string[] {
  return ASKING.filter((_, at) => at % of === index);
}

/**
 * Mount `pattern` loading, unreachable, failed, answered and emptied, and hold it to four
 * different sentences.
 */
export async function holdsFourSentences(pattern: string): Promise<void> {
  const pending = await reading(pattern, { kind: "pending" });
  const unreachable = await reading(pattern, { kind: "unreachable" });
  const failedReading = await readingOf(pattern, { kind: "failed" });
  // The reference is checked here, on the mount the rule already makes, rather than on a sixth.
  // See `ui/FailureNotice.A_FAILURE_WITHOUT_ITS_REFERENCE_IS_A_DEAD_END`.
  expect(textOf(failedReading), `${pattern} drew a failure without its reference`).toContain(TRACE_SENTINEL);
  expect(offersToSignInAgain(failedReading), `${pattern} offered a second factor nobody asked for`).toBe(false);
  const failed = ownWords(failedReading.sentences);
  const page = PAGES[pattern];
  const answers = page?.answers ?? {};
  const hasList = ACTS[pattern] === undefined && emptyAnswers(pattern) !== null && !(pattern in NO_EMPTY_SENTENCE);
  const full = ACTS[pattern] === undefined ? await reading(pattern, { kind: "answered", answers }) : new Set<string>();
  const empty = hasList
    ? await reading(pattern, { kind: "answered", answers: emptyAnswers(pattern) ?? {} })
    : new Set<string>();

  expect(onlyIn(pending, [unreachable, failed, full, empty]), "loading").not.toEqual([]);
  expect(onlyIn(unreachable, [pending, failed, full, empty]), "unreachable").not.toEqual([]);
  expect(onlyIn(failed, [pending, unreachable, full, empty]), "failed").not.toEqual([]);
  if (hasList) {
    const said = onlyIn(empty, [pending, unreachable, failed, full]).filter((one) => one.split(" ").length >= 3);
    expect(said, "empty").not.toEqual([]);
  }
}

/**
 * Mount `pattern` with every request answered by a proxy that never reached the application, and
 * hold it to saying that no reference came back, and to more than the old fallback.
 */
export async function saysNoReferenceCameBack(pattern: string): Promise<void> {
  const read = await readingOf(pattern, { kind: "bodiless" });
  const text = textOf(read);
  expect(text, `${pattern} drew a failure with no reference and did not say so`).toContain(NO_REFERENCE_CAME_BACK);
  expect(text, `${pattern} fell back to the sentence that told the staging install nothing`).not.toContain(
    "Something went wrong.",
  );
}

/**
 * Mount `pattern` with every request refused with a 404 saying a second factor is needed, and hold
 * it to the API's sentence and the control that signs in again, and never to "I could not find that".
 */
export async function asksForASecondFactor(pattern: string): Promise<void> {
  const read = await readingOf(pattern, { kind: "refused", secondFactorNeeded: true });
  const text = textOf(read);
  expect(text, `${pattern} did not show the API's sentence about a second factor`).toContain(SECOND_FACTOR_SENTENCE);
  expect(text, `${pattern} called a refusal for a weak sign-in an absence`).not.toContain(NOT_FOUND_MESSAGE);
  expect(offersToSignInAgain(read), `${pattern} gave no way to sign in again`).toBe(true);
}
