/**
 * What the Questions and gaps screen asks the API for, and how its answer is read. No React.
 *
 * `brain.console.questions_view` decides the screen. This module reads what it sent and adds
 * nothing, and the split from the page is `skillsQuery.ts`'.
 *
 * **The design draws one card for this screen and an install can fill one row of it.**
 * `docs/screens.html` draws "Questions nobody could answer" on the department console, with the
 * shape of each question, how often it was asked, why it failed and the fix, and names the screen
 * "Questions & gaps" under Report on the company overview. Nothing on an install records a
 * question that went unanswered, and the words people typed are not kept, so the Question shape
 * and Asked columns have no source and are not drawn. What an install can say is the design's
 * "no source" row: whether every question is being answered with nothing connected, and the fix,
 * which is to connect a source. See `A_COLUMN_WITH_NO_SOURCE_IS_A_SENTENCE`.
 *
 * **"I could not find that" is never a gap on this screen.** It is said in the same words when a
 * record does not exist and when the person asking may not see it, which is the design's "no
 * knowledge" row and the reason there is no such row here. The page quotes the sentence the API
 * sends, so it names the words askers actually receive.
 *
 * **Nothing here decides who may see what.** A reader who may not be told is sent the body a
 * connected install sends, and this module has no way to tell the two apart and no reason to.
 *
 * Task ids: M27.7.18
 */

import type { components } from "../api/schema";

/** The whole screen, as `brain.report_routes.QuestionsView` sends it. */
export type QuestionsBody = components["schemas"]["QuestionsView"];

/** Written down because the design's columns are the first thing a reader of this screen asks about. */
export const A_COLUMN_WITH_NO_SOURCE_IS_A_SENTENCE =
  "The design lists each unanswered question's shape, how often it was asked, why it failed and " +
  "the fix. Nothing on an install records an unanswered question and the words people typed are " +
  "not kept, so the shape and the count would be columns drawn empty, which read as every " +
  "question having been answered. The page draws the one row an install can know, and says in " +
  "words why the rest cannot be listed.";

/** Where the API keeps this screen. */
export const QUESTIONS_API_PATH = "/report/questions";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const QUESTIONS_PATH = "/questions";

/** Where the fix for the one gap an install can name is made. */
export const CONNECTORS_PATH = "/connectors";

/** Where how many questions were asked is shown. */
export const USAGE_PATH = "/usage";

/** Read the screen out of a response body, or null for a body that is not one. */
export function readQuestions(payload: unknown): QuestionsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    nothing_connected?: unknown;
    answered_when_nothing_connected?: unknown;
    answered_when_nothing_found?: unknown;
    unanswered_are_recorded?: unknown;
  };
  if (
    typeof body.nothing_connected !== "boolean" ||
    typeof body.answered_when_nothing_connected !== "string" ||
    typeof body.answered_when_nothing_found !== "string" ||
    typeof body.unanswered_are_recorded !== "boolean"
  ) {
    return null;
  }
  return payload as QuestionsBody;
}
