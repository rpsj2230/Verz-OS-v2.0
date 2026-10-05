/**
 * Where the Knowledge module asks the API about a stored document's life, and how a picked day
 * becomes the instant the API takes. No React.
 *
 * The routes are `brain.knowledge_lifecycle_routes`: the documents this person looks after, one
 * document's record and history, one version's text, the four acts on a document (verify, a newer
 * version, hand over, ask for the whole company), this person's tasks, and captured solutions. The
 * API decides who may see and do each of them; this module builds the addresses and turns a date a
 * person picked into the instant the API takes, and nothing here decides who may do what.
 *
 * **An address carries identifiers and closed-list words, never a name or a sentence.** A new
 * version's file name travels in its header, as K1's upload's does, and a reason, a problem and an
 * answer travel in a body. `brain.api_routes.A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG` is
 * the rule.
 *
 * **A date a person picks is a day, and the API takes an instant.** The day is sent as noon UTC on
 * that day, so it is the same day wherever the browser is, and a day that is not after today is
 * said before anything is sent, because the API would refuse it for the same reason.
 *
 * Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2, M10.7.2
 */

/** Where each read and write lives, under the API's versioned base. */
const ITEMS_API_PATH = "/knowledge/items";
export const TASKS_API_PATH = "/knowledge/tasks";
export const SOLUTIONS_API_PATH = "/knowledge/solutions";

function one(id: string): string {
  return `${ITEMS_API_PATH}/${encodeURIComponent(id)}`;
}

export function itemPath(id: string): string {
  return one(id);
}

export function passagesPath(id: string): string {
  return `${one(id)}/passages`;
}

export function verificationPath(id: string): string {
  return `${one(id)}/verification`;
}

export function stewardPath(id: string): string {
  return `${one(id)}/steward`;
}

export function promotionPath(id: string): string {
  return `${one(id)}/promotion`;
}

/** Whether the document is public for the website widget, read and changed (M10.7.2). */
export function publicPath(id: string): string {
  return `${one(id)}/public`;
}

/** A newer version's address: the review date as an instant, and nothing about the file. */
export function newVersionPath(id: string, reviewBy: string): string {
  const query = new URLSearchParams({ review_by: reviewBy });
  return `${one(id)}/versions?${query.toString()}`;
}

export function taskDonePath(id: string): string {
  return `${TASKS_API_PATH}/${encodeURIComponent(id)}/done`;
}

export function solutionDecisionPath(id: string): string {
  return `${SOLUTIONS_API_PATH}/${encodeURIComponent(id)}/decision`;
}

/**
 * The instant a picked day stands for: noon UTC on that day, so the day does not move with the
 * browser's timezone. Null for anything that is not a day.
 */
export function instantOf(day: string): string | null {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? `${day}T12:00:00+00:00` : null;
}

/** Whether a picked day is after today, which every review date must be. */
export function isAfterToday(day: string, today: Date = new Date()): boolean {
  const instant = instantOf(day);
  if (instant === null) {
    return false;
  }
  const todayDay = today.toISOString().slice(0, 10);
  return day > todayDay;
}

/** The day a date input starts on: half a year ahead, which a person can change. */
export function defaultReviewDay(today: Date = new Date()): string {
  const ahead = new Date(today.getTime() + 182 * 24 * 60 * 60 * 1000);
  return ahead.toISOString().slice(0, 10);
}

/** The fields a request may name a problem against on this page, so none is listed twice. */
export const LIFECYCLE_FIELDS = ["review_by", "steward_id", "reason", "file", "problem", "answer", "department"];
