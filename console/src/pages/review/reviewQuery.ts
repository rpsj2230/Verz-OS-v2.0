/**
 * What the Access review and Elevation pages ask for beyond `governPeopleQuery.ts`, and the words
 * they use. No React.
 *
 * **One row's page asks the list for it by id.** `brain.govern_people_routes` answers the review and
 * the elevation requests as lists decided row by row (`reviewable`, `requests_shown`) and serves no
 * route for one row, so a holding's and a request's own pages ask the same list with an id filter
 * (`row_id`, `request_id`). A row the reader is not shown is then exactly as absent as one that never
 * existed, because both come back as an empty page from the one decision that draws the list.
 *
 * Task ids: M27.7.8, M27.7.9, M27.16.1
 */

import { listPath, NO_QUESTION } from "../../components/listing";
import {
  ELEVATION_API_PATH,
  ELEVATION_PATH,
  holdingName,
  REVIEW_API_PATH,
  REVIEW_PATH,
  type ReviewRow,
} from "../governPeopleQuery";

/** The module's name, which both tabs' trails begin with. */
export const REVIEW_CRUMB = "Access reviews and elevation";

/** One holding's page. The kind is in the address because a grant and a pack may share an id. */
export function holdingAddress(row: Pick<ReviewRow, "kind" | "row_id">): string {
  return `${REVIEW_PATH}/${encodeURIComponent(row.kind)}/${encodeURIComponent(row.row_id)}`;
}

/** One request's page. */
export function requestAddress(requestId: string): string {
  return `${ELEVATION_PATH}/${encodeURIComponent(requestId)}`;
}

/** The list asked for one holding, by the two filters that name it. */
export function holdingApiPath(kind: string, rowId: string): string {
  return listPath(REVIEW_API_PATH, { ...NO_QUESTION, filters: { kind, row_id: rowId } }, null, 1);
}

/** The list asked for one request, by its id. */
export function requestApiPath(requestId: string): string {
  return listPath(ELEVATION_API_PATH, { ...NO_QUESTION, filters: { request_id: requestId } }, null, 1);
}

/** What a holding is called on its own: the capability, or the pack by name. */
export function holdingTitle(row: ReviewRow): string {
  return row.pack === null ? (row.capabilities[0] ?? "A grant") : `The ${row.pack} pack`;
}

/** The kind of holding in words. */
export function kindWords(kind: string): string {
  return kind === "pack" ? "Pack" : "Single grant";
}

export { holdingName };

/** A last review decision in words, and its tone. */
export function reviewWords(decision: string | null): string {
  return decision === null ? "Never reviewed" : decision === "keep" ? "Kept" : "Removed";
}

/** The hours an elevation runs, in words. */
export function hoursWords(hours: number): string {
  return hours === 1 ? "1 hour" : `${String(hours)} hours`;
}

/** What a scope field takes, said before anything is sent. */
export const SCOPE_HINT = "The scope's short name as the Scopes screen spells it, for example finance or all_clients.";

/** What the explanation is for, said before anything is sent. */
export const EXPLANATION_HINT = "What you need it for, in a sentence or two, so whoever decides can judge it.";

/** What the hours are, said before anything is sent. */
export function hoursHint(longest: number): string {
  return `It lapses on its own after this many hours; at most ${hoursWords(longest)}.`;
}
