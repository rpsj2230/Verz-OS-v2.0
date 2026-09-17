/**
 * What the Questions and gaps screen asks the API for, and how its answer is read. No React.
 *
 * `brain.console.questions_view` decides the screen. This module reads what it sent and adds
 * nothing, and the split from the page is `skillsQuery.ts`'.
 *
 * **The design draws one card for this screen and an install can fill part of it.**
 * `docs/screens.html` draws "Questions nobody could answer" on the department console, with the
 * shape of each question, how often it was asked, why it failed and the fix, and names the screen
 * "Questions & gaps" under Report on the company overview. What an install records is narrower:
 * a question whose shape matches a rule for a source nothing on the install reads, by the
 * department it was asked in and the source that would have answered. So the page draws the
 * design's "no source" row when nothing is connected at all, and a line per department and source
 * for the rest, and the Question shape column is not drawn because the words people typed are not
 * kept. See `A_COLUMN_WITH_NO_SOURCE_IS_A_SENTENCE`.
 *
 * **"I could not find that" is never a gap on this screen.** It is said in the same words when a
 * record does not exist and when the person asking may not see it, which is the design's "no
 * knowledge" row and the reason there is no such row here. The page quotes the sentence the API
 * sends, so it names the words askers actually receive.
 *
 * **Nothing here decides who may see what.** A line the reader may not see is not sent, a source
 * the reader may not be told is sent as null, and this module has no way to tell either apart from
 * an install where it never happened and no reason to.
 *
 * Task ids: M27.7.18
 */

import type { components } from "../api/schema";

/** The whole screen, as `brain.report_routes.QuestionsView` sends it. */
export type QuestionsBody = components["schemas"]["QuestionsView"];
/** One gap line. */
export type GapLineBody = components["schemas"]["GapLineView"];

/** Written down because the design's columns are the first thing a reader of this screen asks about. */
export const A_COLUMN_WITH_NO_SOURCE_IS_A_SENTENCE =
  "The design lists each unanswered question's shape, how often it was asked, why it failed and " +
  "the fix. An install records only a question no connected source covers, by department and " +
  "source, and the words people typed are not kept, so the shape would be a column drawn empty. " +
  "The page draws what an install records, and says in words why the rest cannot be listed.";

/** Where the API keeps this screen. */
export const QUESTIONS_API_PATH = "/report/questions";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const QUESTIONS_PATH = "/questions";

/** Where the fix for a gap is made. */
export const CONNECTORS_PATH = "/connectors";

/** Where how many questions were asked is shown. */
export const USAGE_PATH = "/usage";

/** Read one gap line, or null for something that is not one. */
function readGapLine(payload: unknown): GapLineBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const line = payload as { department?: unknown; source?: unknown; asked?: unknown };
  if (
    typeof line.department !== "string" ||
    !(line.source === null || typeof line.source === "string") ||
    typeof line.asked !== "number"
  ) {
    return null;
  }
  return payload as GapLineBody;
}

/** Read the screen out of a response body, or null for a body that is not one. */
export function readQuestions(payload: unknown): QuestionsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    start?: unknown;
    end?: unknown;
    gaps?: unknown;
    nothing_connected?: unknown;
    answered_when_nothing_connected?: unknown;
    answered_when_nothing_found?: unknown;
    unanswered_are_recorded?: unknown;
  };
  if (
    typeof body.start !== "string" ||
    typeof body.end !== "string" ||
    !Array.isArray(body.gaps) ||
    !body.gaps.every((one) => readGapLine(one) !== null) ||
    typeof body.nothing_connected !== "boolean" ||
    typeof body.answered_when_nothing_connected !== "string" ||
    typeof body.answered_when_nothing_found !== "string" ||
    typeof body.unanswered_are_recorded !== "boolean"
  ) {
    return null;
  }
  return payload as QuestionsBody;
}
