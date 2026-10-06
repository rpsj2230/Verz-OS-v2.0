/**
 * What the Write step asks the API when the author asks the co-author for changes, and what it sends
 * back when they take some. No React.
 *
 * `brain.agent_coauthor_routes` serves both and this file names the same addresses. **A suggestion
 * is data until its author takes it.** Asking sends the draft's revision and a request and writes
 * nothing; the answer is a list of changes, each a manifest path with its value before and after as
 * JSON text, and the page sends the same list back with the paths the author took. The API judges it
 * again against the draft as it now is, so this file holds no rule about what the co-author may
 * change: a path it may not write never arrives, and a change the draft has moved past is refused in
 * the API's own sentence.
 *
 * Task ids: M20.1.3
 */

export { readNotChanged } from "../agentAutomationsQuery";

function under(draftId: string, rest: string): string {
  return `/agent-drafts/${encodeURIComponent(draftId)}/${rest}`;
}

/** `brain.agent_coauthor_routes.SUGGEST_PATH`. */
export function suggestApiPath(draftId: string): string {
  return under(draftId, "suggestions");
}

/** `TAKE_PATH`. */
export function takeApiPath(draftId: string): string {
  return under(draftId, "suggestions/take");
}

/** One proposed change, as the API sent it. `before` is null when the draft held nothing there. */
export interface Suggested {
  readonly path: string;
  readonly where: string;
  readonly before: string | null;
  readonly after: string;
}

/** A change the co-author named that is not proposed, and what to do about it. */
export interface NotSuggested {
  readonly path: string;
  readonly message: string;
}

/** What the co-author proposes for one revision: `SuggestionView`. */
export interface Suggestion {
  readonly revision: number;
  readonly baseDigest: string;
  readonly changes: readonly Suggested[];
  readonly dropped: readonly NotSuggested[];
  readonly note: string;
}

function fieldsOf(payload: unknown): Readonly<Record<string, unknown>> | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field read from
  // the result is checked below.
  return typeof payload === "object" && payload !== null && !Array.isArray(payload)
    ? (payload as Readonly<Record<string, unknown>>)
    : null;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** The suggestion out of a response body, or null when the body is not one. */
export function readSuggestion(payload: unknown): Suggestion | null {
  const fields = fieldsOf(payload);
  const revision = fields?.["revision"];
  const baseDigest = said(fields?.["base_digest"]);
  if (fields === null || typeof revision !== "number" || baseDigest === undefined) {
    return null;
  }
  const changes: Suggested[] = [];
  for (const row of Array.isArray(fields["hunks"]) ? (fields["hunks"] as readonly unknown[]) : []) {
    const one = fieldsOf(row);
    const path = said(one?.["path"]);
    const after = typeof one?.["after"] === "string" ? one["after"] : undefined;
    if (one === null || path === undefined || after === undefined) {
      continue;
    }
    changes.push({
      path,
      where: said(one["where"]) ?? path,
      before: typeof one["before"] === "string" ? one["before"] : null,
      after,
    });
  }
  const dropped: NotSuggested[] = [];
  for (const row of Array.isArray(fields["dropped"]) ? (fields["dropped"] as readonly unknown[]) : []) {
    const one = fieldsOf(row);
    const message = said(one?.["message"]);
    if (one !== null && message !== undefined) {
      dropped.push({ path: said(one["path"]) ?? "", message });
    }
  }
  return { revision, baseDigest, changes, dropped, note: said(fields["note"]) ?? "" };
}

/** The body asking: the revision the page drew and the request. */
export function askBody(revision: number, ask: string): Record<string, unknown> {
  return { revision, ask: ask.trim() };
}

/** The body taking: the proposal as it was drawn, and the paths the author chose. */
export function takeBody(suggestion: Suggestion, take: readonly string[]): Record<string, unknown> {
  return {
    revision: suggestion.revision,
    base_digest: suggestion.baseDigest,
    hunks: suggestion.changes.map((one) => ({ path: one.path, before: one.before, after: one.after })),
    take: [...take],
  };
}

/** A proposed value as a person reads it: a word as it is, a list joined, anything else spelled out. */
export function suggestedWords(json: string | null): string {
  if (json === null) {
    return "nothing";
  }
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    return json;
  }
  if (value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
    return "nothing";
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return (value as readonly unknown[]).map((one) => (typeof one === "string" ? one : JSON.stringify(one))).join(", ");
  }
  return JSON.stringify(value);
}

export const COAUTHOR_HEADING = "Ask the co-author";
export const COAUTHOR_LEDE =
  "Describe what you would like changed and a model proposes edits to the words of this draft. Nothing changes until you take a change.";
export const ASK_LABEL = "What should change?";
export const ASK_BUTTON = "Ask";
export const ASK_NEEDED = "Say what you would like changed before asking.";
export const ASK_QUESTION = "Ask the co-author?";
export const ASK_CONSEQUENCE =
  "The text of this draft and your request are sent to the model provider this install uses. Nothing in the draft changes.";
export const TAKE_BUTTON = "Take the chosen changes";
export const TAKE_QUESTION = "Take these changes into the draft?";
export const TAKE_CONSEQUENCE =
  "They are saved as a new version of this draft. Nothing is live, the changes you did not choose are dropped, and earlier versions are kept.";
export const DROP_BUTTON = "Drop these suggestions";
export const NOTHING_SUGGESTED = "The co-author had nothing to change for that.";
export const KEEP_LABEL = "Not now";
export const NOT_CHANGED = "Nothing was changed";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const TAKEN = "Taken into the draft";
